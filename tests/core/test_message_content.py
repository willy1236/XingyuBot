import json
from datetime import UTC, datetime
from types import SimpleNamespace

import discord
import pytest

from starlib.message_content import (
    AUTHOR_NAME_MAX,
    CONTENT_MAX,
    DESCRIPTION_MAX,
    EMBED_TOTAL_MAX,
    FIELD_NAME_MAX,
    FIELD_VALUE_MAX,
    FIELDS_MAX,
    FOOTER_TEXT_MAX,
    TITLE_MAX,
    EmbedAuthor,
    EmbedContent,
    EmbedField,
    EmbedFooter,
    MessageContent,
    from_json,
    from_message,
    to_json,
    to_send_kwargs,
    validate,
)
from starServer.dashboard.errors import DashboardError
from starServer.dashboard.message_input import ensure_valid_message


def paths(c: MessageContent) -> list[str]:
    return [e.path for e in validate(c)]


def with_embed(**kw) -> MessageContent:
    return MessageContent(embed=EmbedContent(**kw))


def test_empty_needs_something():
    assert paths(MessageContent()) == ["content"]
    assert paths(MessageContent(content="   ")) == ["content"]
    assert paths(MessageContent(content="hi")) == []
    assert paths(with_embed(title="t")) == []


def test_only_color_or_timestamp_counts_as_empty():
    assert paths(with_embed(color=5, extra={"timestamp": "now"})) == ["content"]
    assert paths(MessageContent(content="hi", embed=EmbedContent(color=5))) == []


@pytest.mark.parametrize(
    ("make", "path", "limit"),
    [
        (lambda s: MessageContent(content=s), "content", CONTENT_MAX),
        (lambda s: with_embed(title=s), "embed.title", TITLE_MAX),
        (lambda s: with_embed(description=s), "embed.description", DESCRIPTION_MAX),
        (lambda s: with_embed(author=EmbedAuthor(name=s)), "embed.author.name", AUTHOR_NAME_MAX),
        (lambda s: with_embed(footer=EmbedFooter(text=s)), "embed.footer.text", FOOTER_TEXT_MAX),
        (lambda s: with_embed(fields=[EmbedField(name=s, value="v")]), "embed.fields.0.name", FIELD_NAME_MAX),
        (lambda s: with_embed(fields=[EmbedField(name="n", value=s)]), "embed.fields.0.value", FIELD_VALUE_MAX),
    ],
)
def test_length_limits(make, path, limit):
    assert path not in paths(make("x" * limit))
    assert path in paths(make("x" * (limit + 1)))


def test_field_count_and_blank_field():
    ok = [EmbedField(name="n", value="v")] * FIELDS_MAX
    assert paths(with_embed(fields=ok)) == []
    assert paths(with_embed(fields=[*ok, EmbedField(name="n", value="v")])) == ["embed.fields"]
    assert paths(with_embed(fields=[EmbedField(name="", value=" ")])) == ["embed.fields.0.name", "embed.fields.0.value"]


def test_total_limit():
    # 兩個欄位各自合法，加總超過 6000
    c = with_embed(title="t" * 256, description="d" * 4096, footer=EmbedFooter(text="f" * 1700))
    assert 256 + 4096 + 1700 > EMBED_TOTAL_MAX
    assert paths(c) == ["embed"]
    assert paths(with_embed(title="t" * 256, description="d" * 4096, footer=EmbedFooter(text="f" * 1648))) == []


def test_urls_and_color_and_extra():
    c = with_embed(
        title="t",
        url="javascript:alert(1)",
        image_url="ftp://x/y.png",
        thumbnail_url="https://ok/y.png",
        color=0x1000000,
        extra={"timestamp": "bad", "other": 1},
    )
    assert sorted(paths(c)) == sorted(
        ["embed.url", "embed.image_url", "embed.color", "embed.extra.timestamp", "embed.extra.other"]
    )
    assert paths(with_embed(title="t", color=0xFFFFFF, extra={"timestamp": "2026-01-01T00:00:00+00:00"})) == []


def test_to_send_kwargs_drops_empty_embed():
    assert to_send_kwargs(MessageContent(content="hi", embed=EmbedContent(color=5))) == {"content": "hi", "embeds": []}
    assert to_send_kwargs(with_embed(title="t"))["content"] is None


def test_to_send_kwargs_builds_embed():
    c = with_embed(
        title="t",
        url="https://a.b",
        color=0x123456,
        fields=[EmbedField(name="n", value="v", inline=True)],
        image_url="https://a.b/i.png",
        footer=EmbedFooter(text="f"),
    )
    d = to_send_kwargs(c)["embeds"][0].to_dict()
    assert d["title"] == "t" and d["url"] == "https://a.b" and d["color"] == 0x123456
    assert d["fields"] == [{"name": "n", "value": "v", "inline": True}]
    assert d["image"]["url"] == "https://a.b/i.png" and d["footer"]["text"] == "f"
    assert "timestamp" not in d


def test_timestamp_now_and_fixed():
    before = datetime.now(UTC)
    now_embed = to_send_kwargs(with_embed(title="t", extra={"timestamp": "now"}))["embeds"][0]
    assert now_embed.timestamp is not None and now_embed.timestamp >= before
    fixed = to_send_kwargs(with_embed(title="t", extra={"timestamp": "2026-01-01T00:00:00+00:00"}))["embeds"][0]
    assert fixed.timestamp == datetime(2026, 1, 1, tzinfo=UTC)


def fake_message(content="", embeds=(), attachments=()):
    return SimpleNamespace(content=content, embeds=list(embeds), attachments=list(attachments))


def test_from_message_roundtrip_keeps_timestamp():
    ts = datetime(2026, 5, 6, 7, 8, 9, tzinfo=UTC)
    embed = discord.Embed(title="t", description="d", color=0xABCDEF, timestamp=ts, url="https://a.b")
    embed.set_author(name="a", url="https://a.b", icon_url="https://a.b/a.png")
    embed.add_field(name="n", value="v", inline=False)
    embed.set_image(url="https://a.b/i.png")
    embed.set_thumbnail(url="https://a.b/t.png")
    embed.set_footer(text="f", icon_url="https://a.b/f.png")
    content, reason = from_message(fake_message("hello", [embed]))
    assert reason is None and content is not None
    assert content.content == "hello"
    assert content.embed.extra == {"timestamp": ts.isoformat()}
    assert content.embed.fields == [EmbedField(name="n", value="v", inline=False)]
    assert validate(content) == []
    again = from_json(to_json(content))
    assert again == content
    sent = to_send_kwargs(again)["embeds"][0]
    assert sent.timestamp == ts
    assert sent.to_dict()["author"]["icon_url"] == "https://a.b/a.png"
    assert sent.to_dict()["color"] == 0xABCDEF


def test_from_message_whitelists_extra_and_ignores_unfurl():
    unfurl = discord.Embed.from_dict({"type": "link", "url": "https://x.y", "title": "page"})
    rich = discord.Embed.from_dict(
        {"type": "rich", "title": "t", "video": {"url": "https://v"}, "provider": {"name": "p"}}
    )
    content, reason = from_message(fake_message("", [unfurl, rich]))
    assert reason is None and content.embed.title == "t" and content.embed.extra == {}
    assert content.content is None


def test_from_message_rejects_multiple_embeds_and_attachments():
    e = discord.Embed(title="t")
    assert from_message(fake_message("", [e, discord.Embed(title="u")])) == (None, "multiple_embeds")
    assert from_message(fake_message("hi", [], [object()])) == (None, "has_attachments")


def test_json_roundtrip():
    c = MessageContent(content="x", embed=EmbedContent(title="t", extra={"timestamp": "now"}))
    assert from_json(to_json(c)) == c
    assert json.loads(to_json(c))["embed"]["extra"] == {"timestamp": "now"}


def test_ensure_valid_message_raises_with_fields():
    with pytest.raises(DashboardError) as ei:
        ensure_valid_message(with_embed(fields=[EmbedField(name="n", value="v" * 1025)]))
    assert ei.value.status == 400 and ei.value.code == "invalid_request"
    assert ei.value.extra["fields"] == [{"path": "embed.fields.0.value", "reason": "field 內容不能超過 1024 字"}]
    ensure_valid_message(MessageContent(content="ok"))
