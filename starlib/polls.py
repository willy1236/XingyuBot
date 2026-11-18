"""投票的共用邏輯：結果計算、可見範圍、管理資格與欄位驗證。

指令、Discord 按鈕與後台都經這裡，結果與規則才會一致。除了 `PollResults.load` 讀資料庫，其餘都是純函式。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from starlib.database import Poll, SQLRepository

TITLE_MAX = 45
OPTION_MAX = 80
OPTIONS_MIN = 1
OPTIONS_MAX = 20
WEIGHT_MIN = 1
WEIGHT_MAX = 10
DEADLINE_MAX = timedelta(days=30)

type ViewerRole = Literal["creator", "member"]
type ResultsMode = Literal["everyone", "creator_only", "after_end"]


@dataclass(frozen=True)
class OptionCount:
    option_id: int
    name: str
    #: 加權後的票數
    count: int


@dataclass(frozen=True)
class VoteRow:
    user_id: int
    option_id: int
    weight: int
    voted_at: datetime


@dataclass(frozen=True)
class PollResults:
    options: list[OptionCount]
    #: 投過票的不重複成員數
    voter_count: int
    votes: list[VoteRow]

    @classmethod
    def load(cls, sqldb: SQLRepository, poll: Poll) -> PollResults:
        """讀出投票目前的結果；ban_alternate_account_voting 時排除小帳的票。"""
        include_alt = not poll.ban_alternate_account_voting
        rows = sqldb.poll_vote_rows(poll.poll_id, include_alt)
        votes = [VoteRow(user_id, option_id, weight, voted_at) for user_id, option_id, weight, voted_at in rows]
        totals: dict[int, int] = {}
        for vote in votes:
            totals[vote.option_id] = totals.get(vote.option_id, 0) + vote.weight
        options = [
            OptionCount(o.option_id, o.option_name, totals.get(o.option_id, 0))
            for o in sorted(sqldb.get_poll_options(poll.poll_id), key=lambda o: o.option_id)
        ]
        return cls(options=options, voter_count=len({v.user_id for v in votes}), votes=votes)


def viewer_role(poll: Poll, user_id: int, *, is_owner: bool, creator_in_guild: bool) -> ViewerRole:
    """發起人、bot owner，以及發起人不在伺服器時的（管理員）操作者，都算 creator。"""
    if user_id == poll.creator_id or is_owner or not creator_in_guild:
        return "creator"
    return "member"


def results_mode(poll: Poll) -> ResultsMode:
    """結果的可見設定；關閉「預先查看結果」時一律是結束才公佈。"""
    if not poll.check_results_in_advance:
        return "after_end"
    return "creator_only" if poll.results_only_initiator else "everyone"


def visibility(poll: Poll, role: ViewerRole) -> tuple[bool, bool]:
    """(看得到票數, 看得到投票人)。匿名投票的投票人恆為 False。"""
    if poll.end_at is not None:
        counts = True
    else:
        mode = results_mode(poll)
        counts = mode == "everyone" or (mode == "creator_only" and role == "creator")
    return counts, counts and bool(poll.show_name)


def can_manage(role: ViewerRole) -> bool:
    """能否結算、刪除。"""
    return role == "creator"


def _field(path: str, reason: str) -> dict:
    return {"path": path, "reason": reason}


def validate_poll_input(
    title: str,
    options: list[str],
    number_of_user_votes: int,
    role_weights: dict[int, int],
    deadline: datetime | None,
    now: datetime,
) -> list[dict]:
    """驗證建立投票的欄位，回傳 `[{"path", "reason"}]`，通過時為空 list。

    標題與選項以去掉前後空白後的內容檢查；呼叫端建立時也要用去掉空白的值。
    """
    errors: list[dict] = []

    title = title.strip()
    if not title:
        errors.append(_field("title", "標題不能為空"))
    elif len(title) > TITLE_MAX:
        errors.append(_field("title", f"標題不能超過 {TITLE_MAX} 字"))

    names = [o.strip() for o in options]
    if not OPTIONS_MIN <= len(names) <= OPTIONS_MAX:
        errors.append(_field("options", f"選項必須是 {OPTIONS_MIN} 到 {OPTIONS_MAX} 項"))
    seen: set[str] = set()
    for i, name in enumerate(names):
        if not name:
            errors.append(_field(f"options[{i}]", "選項不能為空"))
        elif len(name) > OPTION_MAX:
            errors.append(_field(f"options[{i}]", f"選項不能超過 {OPTION_MAX} 字"))
        elif name in seen:
            errors.append(_field(f"options[{i}]", "選項不能重複"))
        seen.add(name)

    max_votes = min(len(names), OPTIONS_MAX)
    if max_votes >= 1 and not 1 <= number_of_user_votes <= max_votes:
        errors.append(_field("number_of_user_votes", f"每人可投票數必須在 1 到 {max_votes} 之間"))

    for role_id, weight in role_weights.items():
        if not WEIGHT_MIN <= weight <= WEIGHT_MAX:
            errors.append(_field(f"role_weights[{role_id}]", f"權重必須在 {WEIGHT_MIN} 到 {WEIGHT_MAX} 之間"))

    if deadline is not None:
        if deadline.tzinfo is None:
            errors.append(_field("deadline", "截止時間必須包含時區"))
        else:
            rounded = deadline.replace(second=0, microsecond=0)
            if rounded <= now:
                errors.append(_field("deadline", "截止時間必須晚於現在"))
            elif rounded > now + DEADLINE_MAX:
                errors.append(_field("deadline", "截止時間最長為 30 天後"))

    return errors
