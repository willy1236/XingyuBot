"""訊息內容（文字加一個 embed）的資料形狀、Discord 上限驗證，以及與 Discord 訊息互相轉換。

後台的訊息編輯器與 bot 指令共用。前端 `lib/dashboard-message.ts` 的型別與上限常數須與這裡一致。
"""

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import discord
from pydantic import BaseModel, Field

# Discord 上限（以官方文件為準）
CONTENT_MAX = 2000
TITLE_MAX = 256
DESCRIPTION_MAX = 4096
FIELDS_MAX = 25
FIELD_NAME_MAX = 256
FIELD_VALUE_MAX = 1024
FOOTER_TEXT_MAX = 2048
AUTHOR_NAME_MAX = 256
EMBED_TOTAL_MAX = 6000
COLOR_MAX = 0xFFFFFF

#: extra["timestamp"] 的特殊值：送出時帶當下時間
TIMESTAMP_NOW = "now"
#: from_message 唯一保留進 extra 的欄位
EXTRA_KEYS = frozenset({"timestamp"})

#: from_message 無法讀回的原因代碼
REASON_MULTIPLE_EMBEDS = "multiple_embeds"
REASON_HAS_ATTACHMENTS = "has_attachments"


class EmbedAuthor(BaseModel):
    name: str | None = None
    url: str | None = None
    icon_url: str | None = None


class EmbedFooter(BaseModel):
    text: str | None = None
    icon_url: str | None = None


class EmbedField(BaseModel):
    name: str = ""
    value: str = ""
    inline: bool = False


class EmbedContent(BaseModel):
    title: str | None = None
    url: str | None = None
    description: str | None = None
    color: int | None = None
    author: EmbedAuthor | None = None
    fields: list[EmbedField] = Field(default_factory=list)
    image_url: str | None = None
    thumbnail_url: str | None = None
    footer: EmbedFooter | None = None
    #: 編輯器不直接編輯的欄位原樣保留；目前只有 timestamp（ISO 字串，或 TIMESTAMP_NOW 表示送出時帶當下時間）
    extra: dict[str, Any] = Field(default_factory=dict)


class MessageContent(BaseModel):
    content: str | None = None
    embed: EmbedContent | None = None


class FieldError(BaseModel):
    path: str
    reason: str


def _length(value: str | None) -> int:
    return len(value) if value else 0


def embed_is_empty(e: EmbedContent | None) -> bool:
    """沒有任何文字或圖片類欄位就是空的；只有 color 或 timestamp 也算空。"""
    if e is None:
        return True
    return not (
        e.title
        or e.description
        or (e.author and e.author.name)
        or e.fields
        or (e.footer and e.footer.text)
        or e.image_url
        or e.thumbnail_url
    )


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _timestamp_ok(value: Any) -> bool:
    if value == TIMESTAMP_NOW:
        return True
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate(c: MessageContent) -> list[FieldError]:
    """照 Discord 上限檢查，回傳所有錯誤；path 與前端 validateMessage 一致。"""
    errors: list[FieldError] = []

    def check_len(path: str, value: str | None, limit: int, label: str) -> None:
        if _length(value) > limit:
            errors.append(FieldError(path=path, reason=f"{label}不能超過 {limit} 字"))

    def check_url(path: str, value: str | None, label: str) -> None:
        if value and not _is_http_url(value):
            errors.append(FieldError(path=path, reason=f"{label}必須是 http 或 https 網址"))

    check_len("content", c.content, CONTENT_MAX, "文字")
    e = c.embed
    if embed_is_empty(e) and not (c.content and c.content.strip()):
        errors.append(FieldError(path="content", reason="文字與 embed 至少要填一項"))
    if e is None:
        return errors

    check_len("embed.title", e.title, TITLE_MAX, "標題")
    check_url("embed.url", e.url, "標題連結")
    check_len("embed.description", e.description, DESCRIPTION_MAX, "說明")
    if e.color is not None and not 0 <= e.color <= COLOR_MAX:
        errors.append(FieldError(path="embed.color", reason="顏色必須在 0 到 16777215 之間"))
    if e.author:
        check_len("embed.author.name", e.author.name, AUTHOR_NAME_MAX, "作者名稱")
        check_url("embed.author.url", e.author.url, "作者連結")
        check_url("embed.author.icon_url", e.author.icon_url, "作者圖示")
    if len(e.fields) > FIELDS_MAX:
        errors.append(FieldError(path="embed.fields", reason=f"field 不能超過 {FIELDS_MAX} 個"))
    for i, f in enumerate(e.fields):
        if not f.name.strip():
            errors.append(FieldError(path=f"embed.fields.{i}.name", reason="field 名稱不能空白"))
        check_len(f"embed.fields.{i}.name", f.name, FIELD_NAME_MAX, "field 名稱")
        if not f.value.strip():
            errors.append(FieldError(path=f"embed.fields.{i}.value", reason="field 內容不能空白"))
        check_len(f"embed.fields.{i}.value", f.value, FIELD_VALUE_MAX, "field 內容")
    check_url("embed.image_url", e.image_url, "圖片")
    check_url("embed.thumbnail_url", e.thumbnail_url, "縮圖")
    if e.footer:
        check_len("embed.footer.text", e.footer.text, FOOTER_TEXT_MAX, "頁尾文字")
        check_url("embed.footer.icon_url", e.footer.icon_url, "頁尾圖示")
    for key, value in e.extra.items():
        if key not in EXTRA_KEYS:
            errors.append(FieldError(path=f"embed.extra.{key}", reason="不支援的欄位"))
        elif key == "timestamp" and not _timestamp_ok(value):
            errors.append(FieldError(path="embed.extra.timestamp", reason="時間戳格式不正確"))

    total = (
        _length(e.title)
        + _length(e.description)
        + (_length(e.author.name) if e.author else 0)
        + (_length(e.footer.text) if e.footer else 0)
        + sum(_length(f.name) + _length(f.value) for f in e.fields)
    )
    if total > EMBED_TOTAL_MAX:
        reason = f"embed 的標題、說明、field、作者與頁尾加總不能超過 {EMBED_TOTAL_MAX} 字（目前 {total}）"
        errors.append(FieldError(path="embed", reason=reason))
    return errors


def _embed_dict(e: EmbedContent) -> dict[str, Any]:
    d: dict[str, Any] = {}
    if e.title:
        d["title"] = e.title
        if e.url:
            d["url"] = e.url
    if e.description:
        d["description"] = e.description
    if e.color is not None:
        d["color"] = e.color
    if e.author and e.author.name:
        d["author"] = {k: v for k, v in e.author.model_dump().items() if v}
    if e.fields:
        d["fields"] = [{"name": f.name, "value": f.value, "inline": f.inline} for f in e.fields]
    if e.image_url:
        d["image"] = {"url": e.image_url}
    if e.thumbnail_url:
        d["thumbnail"] = {"url": e.thumbnail_url}
    if e.footer and e.footer.text:
        d["footer"] = {k: v for k, v in e.footer.model_dump().items() if v}
    timestamp = e.extra.get("timestamp")
    if timestamp == TIMESTAMP_NOW:
        d["timestamp"] = datetime.now(UTC).isoformat()
    elif timestamp:
        d["timestamp"] = timestamp
    return d


def to_send_kwargs(c: MessageContent) -> dict[str, Any]:
    """回 {content, embeds} 給 send／edit；空的 embed 不送，空文字回 None（edit 時會清掉文字）。"""
    embeds = [] if c.embed is None or embed_is_empty(c.embed) else [discord.Embed.from_dict(_embed_dict(c.embed))]
    return {"content": c.content or None, "embeds": embeds}


def from_message(m: discord.Message) -> tuple[MessageContent | None, str | None]:
    """從既有訊息讀回內容；兩則以上 embed 或帶附件時回 (None, 原因代碼)。

    只算 rich embed；連結自動展開的 link／image／video 不算。
    """
    if m.attachments:
        return None, REASON_HAS_ATTACHMENTS
    rich = [e for e in m.embeds if e.type == "rich"]
    if len(rich) > 1:
        return None, REASON_MULTIPLE_EMBEDS
    embed = None
    if rich:
        d = rich[0].to_dict()
        author, footer = d.get("author"), d.get("footer")
        embed = EmbedContent(
            title=d.get("title"),
            url=d.get("url"),
            description=d.get("description"),
            color=d.get("color"),
            author=EmbedAuthor(name=author.get("name"), url=author.get("url"), icon_url=author.get("icon_url"))
            if author
            else None,
            fields=[
                EmbedField(name=f.get("name", ""), value=f.get("value", ""), inline=bool(f.get("inline", True)))
                for f in d.get("fields", [])
            ],
            image_url=(d.get("image") or {}).get("url"),
            thumbnail_url=(d.get("thumbnail") or {}).get("url"),
            footer=EmbedFooter(text=footer.get("text"), icon_url=footer.get("icon_url")) if footer else None,
            extra={k: v for k, v in d.items() if k in EXTRA_KEYS},
        )
    return MessageContent(content=m.content or None, embed=embed), None


def to_json(c: MessageContent) -> str:
    return c.model_dump_json()


def from_json(s: str) -> MessageContent:
    return MessageContent.model_validate(json.loads(s))
