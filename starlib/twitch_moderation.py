"""頻道聊天室過濾設定、訊息判定與執法紀錄。"""

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, NotRequired, TypedDict
from unicodedata import category
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlmodel import Session, select

from starlib._twitch_unicode import EMOJI_PRESENTATION_RANGES, LATIN_RANGES, TEXT_EMOJI_RANGES
from starlib.database import TwitchEnforcementLog, TwitchModerationFilter, TwitchModerationSetting, sqldb
from starlib.messaging import cache_invalidation
from starlib.twitch_audit import AuditActor, record_change
from starlib.utils import nowtz

FILTER_KINDS = ("link", "blocked_word", "caps", "emote", "symbol", "repetition", "length", "duplicate")
EXEMPT_LEVELS = ("subscriber", "regular", "vip", "mod")
FILTER_LABELS = {
    "link": "連結",
    "blocked_word": "禁字",
    "caps": "大寫",
    "emote": "表情符號過多",
    "symbol": "符號過多",
    "repetition": "重複內容",
    "length": "訊息過長",
    "duplicate": "跨訊息重複",
}
COUNT_RANGE = (1, 500)
PERCENT_RANGE = (1, 100)
DUPLICATE_SECONDS_RANGE = (1, 300)
DUPLICATE_COUNT_RANGE = (2, 100)
DEFAULT_NOTICE = "{user}，請遵守聊天室的{filter}分享規則。"
GENERAL_NOTICE = "{user}，請遵守聊天室的{filter}過濾規則。"
NOTICE_SECONDS = 10
NOTICE_MAX_LENGTH = 500
STRIKE_RESET_MINUTES = 60
RAID_PAUSE_SECONDS = 120
PERMIT_SECONDS = 60
STAGE_COUNT_RANGE = (1, 5)
TIMEOUT_SECONDS_RANGE = (1, 14 * 24 * 60 * 60)
STRIKE_RESET_MINUTES_RANGE = (1, 24 * 60)
RAID_PAUSE_SECONDS_RANGE = (0, 10 * 60)
PERMIT_SECONDS_RANGE = (10, 10 * 60)


class Stage(TypedDict):
    action: str
    duration: int | None


class _FilterFields(TypedDict):
    enabled: bool
    exempt_level: str
    params: dict[str, Any]
    notice: str | None
    silent: bool


class FilterValues(_FilterFields):
    stages: NotRequired[list[Stage] | None]


class _FilterSnapshot(_FilterFields):
    stages: list[Stage] | None


class FilterConfig(_FilterSnapshot):
    kind: str
    updated_at: str | None


class _PenaltyValues(TypedDict):
    stages: list[Stage]
    strike_reset_minutes: int
    permit_seconds: int


class SettingsValues(_PenaltyValues):
    raid_pause_seconds: NotRequired[int]


class _SettingsSnapshot(_PenaltyValues):
    raid_pause_seconds: int


class Settings(_SettingsSnapshot):
    updated_at: str | None


class ModerationConfig(TypedDict):
    settings: Settings
    filters: list[FilterConfig]


type Verify = Callable[[dict[str, str | None]], None]


class InvalidField(ValueError):
    def __init__(self, field: str, reason: str):
        super().__init__(reason)
        self.field = field


@dataclass(frozen=True, slots=True)
class _Threshold:
    default: int
    label: str
    bounds: tuple[int, int]


_THRESHOLDS = {
    "caps": {
        "min_count": _Threshold(8, "大寫字母數", COUNT_RANGE),
        "min_percent": _Threshold(70, "大寫比例", PERCENT_RANGE),
    },
    "emote": {"min_count": _Threshold(3, "表情數", COUNT_RANGE)},
    "symbol": {"min_count": _Threshold(8, "符號數", COUNT_RANGE)},
    "repetition": {"min_percent": _Threshold(45, "重複比例", PERCENT_RANGE)},
    "length": {"min_length": _Threshold(300, "訊息字元數", COUNT_RANGE)},
    "duplicate": {
        "window_seconds": _Threshold(30, "比對時間", DUPLICATE_SECONDS_RANGE),
        "min_count": _Threshold(3, "相同訊息則數", DUPLICATE_COUNT_RANGE),
    },
}


def _default_params(kind: str) -> dict[str, Any]:
    match kind:
        case "link":
            return {"whitelist": []}
        case "blocked_word":
            return {"words": []}
        case _:
            return {key: threshold.default for key, threshold in _THRESHOLDS[kind].items()}


# 裸網域只認這份封閉清單；有 http(s) 的 URL 則不受 TLD 限制。
_BARE_TLDS = frozenset(
    """
    com net org edu gov mil int info biz name pro aero coop museum app dev live online site shop store tech xyz
    ac ad ae af ag ai al am ao aq ar as at au aw ax az ba bb bd be bf bg bh bi bj bm bn bo br bs bt bv bw by bz
    ca cc cd cf cg ch ci ck cl cm cn co cr cu cv cw cx cy cz de dj dk dm do dz ec ee eg er es et eu fi fj fk fm
    fo fr ga gb gd ge gf gg gh gi gl gm gn gp gq gr gs gt gu gw gy hk hm hn hr ht hu id ie il im in io iq ir is
    it je jm jo jp ke kg kh ki km kn kp kr kw ky kz la lb lc li lk lr ls lt lu lv ly ma mc md me mg mh mk ml mm
    mn mo mp mq mr ms mt mu mv mw mx my mz na nc ne nf ng ni nl no np nr nu nz om pa pe pf pg ph pk pl pm pn pr
    ps pt pw py qa re ro rs ru rw sa sb sc sd se sg sh si sj sk sl sm sn so sr ss st su sv sx sy sz tc td tf tg
    th tj tk tl tm tn to tr tt tv tw tz ua ug uk us uy uz va vc ve vg vi vn vu wf ws ye yt za zm zw
    """.split()
)
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN = rf"(?:{_LABEL}\.)+{_LABEL}"
_URL_CHARS = r"""[^\s<>"'\x00-\x1f，。！？、；：」』）】]"""
_LINK = re.compile(
    rf"(?P<url>https?://{_URL_CHARS}*)|"
    rf"(?ai:(?<![a-z0-9_@.-])(?P<host>{_DOMAIN})(?![a-z0-9_@-]|\.[a-z0-9]))"
    rf"(?::[0-9]+)?(?P<path>/{_URL_CHARS}*)?",
    re.IGNORECASE,
)
_HOST = re.compile(_DOMAIN, re.IGNORECASE | re.ASCII)
_LATIN = re.compile(f"[{LATIN_RANGES}]")
_EMOJI_ELEMENT = (
    rf"(?:[{EMOJI_PRESENTATION_RANGES}](?!\ufe0e)\ufe0f?|[{TEXT_EMOJI_RANGES}]\ufe0f)"
    r"[\U0001f3fb-\U0001f3ff]?"
)
_EMOJI = re.compile(
    r"[\U0001f1e6-\U0001f1ff]{2}|[#*0-9]\ufe0f?\u20e3|"
    r"\U0001f3f4[\U000e0020-\U000e007e]+\U000e007f|"
    rf"{_EMOJI_ELEMENT}(?:\u200d{_EMOJI_ELEMENT})*"
)


def _host_path(host: str, path: str) -> tuple[str, str]:
    host = host.lower()
    if host.count(".") > 1:
        host = host.removeprefix("www.")
    return host, path.lower().rstrip("/")


def _normalize_whitelist_entry(entry: str) -> str:
    raw = entry.strip()
    try:
        parsed = urlsplit(raw if "://" in raw else "//" + raw)
        if (
            parsed.scheme not in {"", "http", "https"}
            or not parsed.hostname
            or not _HOST.fullmatch(parsed.hostname)
            or parsed.netloc.lower() != parsed.hostname
            or "?" in raw
            or "#" in raw
            or any(character.isspace() or ord(character) < 32 for character in raw)
        ):
            raise ValueError
    except ValueError:
        raise InvalidField("params", "白名單請輸入網域或網域加路徑") from None
    return "".join(_host_path(parsed.hostname, parsed.path))


def detect_link(text: str, whitelist: Sequence[str]) -> bool:
    """訊息有任何一個不在白名單內的連結時回傳 True。"""
    allowed = [entry.partition("/") for entry in whitelist]
    for match in _LINK.finditer(text):
        if match["url"] is not None:
            # 白名單看實際的目的地，包含在 URL 帳號欄位中的網域不算。
            try:
                url = urlsplit(match["url"].rstrip(".,!;:)}").replace("\\", "/"))
                domain = url.hostname
            except ValueError:
                continue
            if domain is None:
                continue
            raw_path = url.path
        else:
            domain = match["host"]
            if domain.rsplit(".", 1)[1].lower() not in _BARE_TLDS:
                continue
            raw_path = (match["path"] or "").split("?", 1)[0].split("#", 1)[0]
        host, path = _host_path(domain, raw_path.rstrip(".,!;:)]}"))
        if not any(
            (host == allowed_host or host.endswith("." + allowed_host))
            and (not separator or path == "/" + prefix or path.startswith("/" + prefix + "/"))
            for allowed_host, separator, prefix in allowed
        ):
            return True
    return False


@lru_cache(maxsize=128)
def _blocked_patterns(words: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    return tuple(tuple(part for part in word.casefold().split("*") if part) for word in words if word)


def detect_blocked_word(text: str, words: Sequence[str]) -> bool:
    """萬用字元兩側的文字只需依序出現，不限制中間字元。"""
    folded = text.casefold()
    for pattern in _blocked_patterns(tuple(words)):
        if not pattern:
            continue
        start = 0
        for part in pattern:
            index = folded.find(part, start)
            if index < 0:
                break
            start = index + len(part)
        else:
            return True
    return False


def detect_caps(text: str, min_count: int, min_percent: int) -> bool:
    letters = [letter for letter in _LATIN.findall(text) if letter.isalpha()]
    uppercase = sum(letter.isupper() for letter in letters)
    return uppercase >= min_count and uppercase * 100 >= len(letters) * min_percent


def detect_emotes(text: str, twitch_count: int, min_count: int) -> bool:
    return twitch_count >= min_count or twitch_count + len(_EMOJI.findall(text)) >= min_count


_COMMON_FULLWIDTH_PUNCTUATION = frozenset("。，、！？：；「」『』（）～…—")


def detect_symbols(text: str, min_count: int) -> bool:
    count = sum(
        char not in _COMMON_FULLWIDTH_PUNCTUATION and category(char)[0] in "PS"
        for char in _EMOJI.sub("", text)
    )
    return count >= min_count


def _prefix_matches(chars: Sequence[str | None]) -> list[int]:
    """Z function: length of the prefix matching at each position."""
    matches = [0] * len(chars)
    start = end = 0
    for index in range(1, len(chars)):
        if index < end:
            matches[index] = min(end - index, matches[index - start])
        while index + matches[index] < len(chars) and chars[matches[index]] == chars[index + matches[index]]:
            matches[index] += 1
        if index + matches[index] > end:
            start, end = index, index + matches[index]
    return matches


def detect_repetition(text: str, min_percent: int) -> bool:
    length = len(text)
    if length < 10:
        return False
    threshold = (length * min_percent + 99) // 100
    if threshold <= length and text == text[0] * length:
        return True
    # A repeated interval cannot cover characters that occur only once.
    if (length - len(set(text))) * 2 < threshold:
        return False

    coverage = [0] * (length + 1)
    pending = [(0, length)]
    while pending:
        start, end = pending.pop()
        size = end - start
        if size < 2:
            continue
        if size == 2:
            if text[start] == text[start + 1]:
                coverage[start] += 1
                coverage[end] -= 1
            continue
        middle = size // 2
        segment = list(text[start:end])
        left, right = segment[:middle], segment[middle:]
        left.reverse()
        backward = _prefix_matches([*left, None, *reversed(segment)])
        forward = _prefix_matches([*right, None, *segment])
        left_matches, right_matches = _prefix_matches(left), _prefix_matches(right)
        # A tandem repeat crossing the midpoint includes a matching pair at distance p
        # with one member at that midpoint. Extend those pairs in both directions.
        for period in range(1, size // 2 + 1):
            for index, before, after in (
                (
                    middle - period,
                    left_matches[period] if period < middle else 0,
                    forward[len(right) + 1 + middle - period],
                ),
                (
                    middle,
                    backward[size + 1 - period],
                    right_matches[period] if period < len(right) else 0,
                ),
            ):
                if before + after < period:
                    continue
                if before + period + after >= threshold:
                    return True
                coverage[start + index - before] += 1
                coverage[start + index + period + after] -= 1
        pending.extend(((start, start + middle), (start + middle, end)))

    active = repeated = 0
    for delta in coverage:
        active += delta
        repeated += active > 0
    return repeated >= threshold


def detect_length(text: str, min_length: int) -> bool:
    return len(text) >= min_length


def detect_duplicate(occurrences: int, min_count: int) -> bool:
    return occurrences >= min_count


def detect_message(kind: str, params: dict[str, Any], text: str, twitch_count: int, occurrences: int) -> bool:
    match kind:
        case "link":
            return detect_link(text, params["whitelist"])
        case "blocked_word":
            return detect_blocked_word(text, params["words"])
        case "caps":
            return detect_caps(text, params["min_count"], params["min_percent"])
        case "emote":
            return detect_emotes(text, twitch_count, params["min_count"])
        case "symbol":
            return detect_symbols(text, params["min_count"])
        case "repetition":
            return detect_repetition(text, params["min_percent"])
        case "length":
            return detect_length(text, params["min_length"])
        case "duplicate":
            return detect_duplicate(occurrences, params["min_count"])
    return False


def _validate_common(values: FilterValues) -> None:
    level = values["exempt_level"]
    if level not in EXEMPT_LEVELS:
        raise InvalidField("exempt_level", "請選擇訂閱者、常客、VIP 或 mod")
    notice = values["notice"]
    if notice is not None and (not notice.strip() or len(notice) > NOTICE_MAX_LENGTH):
        raise InvalidField("notice", f"告知文字需為 1 到 {NOTICE_MAX_LENGTH} 字")
    if notice is not None and any(character in notice for character in "\r\n\0"):
        raise InvalidField("notice", "告知文字只能有一行")


def _validate_whitelist(raw: object) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(entry, str) for entry in raw):
        raise InvalidField("params", "白名單必須是網域或路徑的清單")
    return list(dict.fromkeys(_normalize_whitelist_entry(entry) for entry in raw))


def _validate_range(value: int, bounds: tuple[int, int], field: str, label: str) -> None:
    lower, upper = bounds
    if type(value) is not int or not lower <= value <= upper:
        raise InvalidField(field, f"{label}必須是 {lower} 到 {upper} 的整數")


def _validate_stages(stages: list[Stage]) -> None:
    _validate_range(len(stages), STAGE_COUNT_RANGE, "stages", "處罰段數")
    for stage in stages:
        action = stage["action"]
        duration = stage["duration"]
        if action == "timeout":
            if duration is None:
                raise InvalidField("stages", "請填寫 timeout 秒數")
            _validate_range(duration, TIMEOUT_SECONDS_RANGE, "stages", "timeout 秒數")
        elif action not in ("delete", "ban") or duration is not None:
            raise InvalidField("stages", "請選擇有效的處罰動作，秒數只適用於 timeout")


def validate_settings(values: SettingsValues) -> None:
    _validate_stages(values["stages"])
    _validate_range(
        values["strike_reset_minutes"], STRIKE_RESET_MINUTES_RANGE, "strike_reset_minutes", "犯規次數歸零分鐘數"
    )
    _validate_range(values["permit_seconds"], PERMIT_SECONDS_RANGE, "permit_seconds", "放行秒數")
    if "raid_pause_seconds" in values:
        _validate_range(values["raid_pause_seconds"], RAID_PAUSE_SECONDS_RANGE, "raid_pause_seconds", "Raid 後暫停秒數")


def validate_filter(kind: str, values: FilterValues) -> FilterValues:
    if kind not in FILTER_KINDS:
        raise InvalidField("kind", "未知的過濾器")
    _validate_common(values)
    if (stages := values.get("stages")) is not None:
        _validate_stages(stages)
    params = values["params"]
    validated: dict[str, Any]
    match kind:
        case "link":
            validated = {"whitelist": _validate_whitelist(params.get("whitelist"))}
        case "blocked_word":
            words = params.get("words")
            if not isinstance(words, list) or not all(isinstance(word, str) for word in words):
                raise InvalidField("params", "禁字必須是文字清單")
            if any(word.strip() and not word.replace("*", "").strip() for word in words):
                raise InvalidField("params", "每個禁字至少需要一個非萬用字元")
            validated = {"words": list(dict.fromkeys(word.strip() for word in words if word.strip()))}
        case _:
            validated = {}
            for key, threshold in _THRESHOLDS[kind].items():
                value = params.get(key)
                lower, upper = threshold.bounds
                if type(value) is not int or not lower <= value <= upper:
                    raise InvalidField("params", f"{threshold.label}必須是 {lower} 到 {upper} 的整數")
                validated[key] = value
    return {**values, "params": validated}


def _snapshot(row: TwitchModerationFilter | None, kind: str) -> _FilterSnapshot:
    if row is None:
        return {
            "enabled": False,
            "exempt_level": "vip",
            "params": _default_params(kind),
            "stages": None,
            "notice": None,
            "silent": False,
        }
    return {
        "enabled": row.enabled,
        "exempt_level": row.exempt_level,
        "params": {**_default_params(kind), **row.params},
        "stages": _stages(row.stages) if row.stages is not None else None,
        "notice": row.notice,
        "silent": row.silent,
    }


def comparable(values: FilterValues | _FilterSnapshot) -> dict[str, str | None]:
    result = {
        "enabled": str(values["enabled"]).lower(),
        "exempt_level": values["exempt_level"],
        "params": json.dumps(values["params"], sort_keys=True, ensure_ascii=False),
        "notice": values["notice"],
        "silent": str(values["silent"]).lower(),
    }
    if "stages" in values:
        stages = values["stages"]
        result["stages"] = json.dumps(stages, sort_keys=True) if stages is not None else None
    return result


def comparable_settings(values: SettingsValues | _SettingsSnapshot) -> dict[str, str | None]:
    comparable: dict[str, str | None] = {
        "stages": json.dumps(values["stages"], sort_keys=True),
        "strike_reset_minutes": str(values["strike_reset_minutes"]),
        "permit_seconds": str(values["permit_seconds"]),
    }
    if "raid_pause_seconds" in values:
        comparable["raid_pause_seconds"] = str(values["raid_pause_seconds"])
    return comparable


def _stages(rows: list[dict[str, Any]]) -> list[Stage]:
    return [{"action": row["action"], "duration": row["duration"]} for row in rows]


def _filter_config(row: TwitchModerationFilter | None, kind: str) -> FilterConfig:
    return {
        **_snapshot(row, kind),
        "kind": kind,
        "updated_at": row.updated_at.isoformat() if row is not None else None,
    }


def _settings_values(row: TwitchModerationSetting | None) -> _SettingsSnapshot:
    return {
        "stages": _stages(row.stages)
        if row is not None
        else [{"action": "delete", "duration": None}, {"action": "timeout", "duration": 600}],
        "strike_reset_minutes": row.strike_reset_minutes if row is not None else STRIKE_RESET_MINUTES,
        "raid_pause_seconds": row.raid_pause_seconds if row is not None else RAID_PAUSE_SECONDS,
        "permit_seconds": row.permit_seconds if row is not None else PERMIT_SECONDS,
    }


def _settings_config(row: TwitchModerationSetting | None) -> Settings:
    return {
        **_settings_values(row),
        "updated_at": row.updated_at.isoformat() if row is not None else None,
    }


def get_config(twitch_id: int) -> ModerationConfig:
    session = sqldb.session
    row = session.get(TwitchModerationSetting, twitch_id, populate_existing=True)
    filters = session.exec(
        select(TwitchModerationFilter)
        .where(TwitchModerationFilter.twitch_id == twitch_id)
        .execution_options(populate_existing=True)
    )
    by_kind = {item.kind: item for item in filters}
    return {
        "settings": _settings_config(row),
        "filters": [_filter_config(by_kind.get(kind), kind) for kind in FILTER_KINDS],
    }


def _lock_channel_settings(session: Session, twitch_id: int) -> None:
    # 鎖也涵蓋尚無設定列的頻道。
    session.connection().execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"twitch_moderation:{twitch_id}"}
    )


def update_filter(twitch_id: int, kind: str, actor: AuditActor, values: FilterValues, verify: Verify) -> FilterConfig:
    values = validate_filter(kind, values)
    session = sqldb.session
    try:
        _lock_channel_settings(session, twitch_id)
        row = session.get(TwitchModerationFilter, (twitch_id, kind), populate_existing=True, with_for_update=True)
        before = _snapshot(row, kind)
        verify(comparable(before))
        values.setdefault("stages", before["stages"])
        if before == values:
            result = _filter_config(row, kind)
            session.rollback()
            return result
        created = row is None
        if row is None:
            row = TwitchModerationFilter(twitch_id=twitch_id, kind=kind, **values)
        else:
            row.sqlmodel_update(dict(values))
        row.updated_at = nowtz()
        session.add(row)
        session.flush()
        record_change(
            twitch_id,
            actor,
            "dashboard",
            "moderation",
            kind,
            "create" if created else "update",
            dict(before),
            dict(values),
        )
        result = _filter_config(row, kind)
        sqldb.commit()
    except BaseException:
        session.rollback()
        raise
    cache_invalidation.invalidate("twitch_moderation", str(twitch_id))
    return result


def update_settings(twitch_id: int, actor: AuditActor, values: SettingsValues, verify: Verify) -> Settings:
    validate_settings(values)
    session = sqldb.session
    try:
        _lock_channel_settings(session, twitch_id)
        row = session.get(TwitchModerationSetting, twitch_id, populate_existing=True, with_for_update=True)
        before = _settings_values(row)
        verify(comparable_settings(before))
        after: _SettingsSnapshot = {**before, **values}
        if before == after:
            result = _settings_config(row)
            session.rollback()
            return result
        created = row is None
        if row is None:
            row = TwitchModerationSetting(twitch_id=twitch_id, **after)
        else:
            row.sqlmodel_update(dict(after))
        row.updated_at = nowtz()
        session.add(row)
        session.flush()
        record_change(
            twitch_id,
            actor,
            "dashboard",
            "moderation",
            "channel",
            "create" if created else "update",
            dict(before),
            dict(after),
        )
        session.refresh(row, attribute_names=["updated_at"])
        result = _settings_config(row)
        sqldb.commit()
    except BaseException:
        session.rollback()
        raise
    cache_invalidation.invalidate("twitch_moderation", str(twitch_id))
    return result


def record_enforcement(entry: TwitchEnforcementLog) -> None:
    sqldb.add(entry)
