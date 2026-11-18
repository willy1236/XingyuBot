"""starlib.polls 的純函式：可見範圍、管理資格、欄位驗證。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from starlib.polls import can_manage, results_mode, validate_poll_input, viewer_role, visibility

NOW = datetime(2026, 11, 18, 12, 0, 30, tzinfo=UTC)


def poll(*, check=True, only_initiator=False, show_name=True, ended=False, creator_id=1):
    return SimpleNamespace(
        check_results_in_advance=check,
        results_only_initiator=only_initiator,
        show_name=show_name,
        end_at=NOW if ended else None,
        creator_id=creator_id,
    )


class TestVisibility:
    @pytest.mark.parametrize("role", ["creator", "member"])
    def test_everyone_sees_counts_in_progress(self, role):
        assert visibility(poll(), role) == (True, True)

    def test_creator_only_in_progress(self):
        p = poll(only_initiator=True)
        assert visibility(p, "creator") == (True, True)
        assert visibility(p, "member") == (False, False)

    @pytest.mark.parametrize("role", ["creator", "member"])
    def test_after_end_hides_everyone_in_progress(self, role):
        assert visibility(poll(check=False), role) == (False, False)

    def test_check_off_overrides_only_initiator(self):
        p = poll(check=False, only_initiator=True)
        assert results_mode(p) == "after_end"
        assert visibility(p, "creator") == (False, False)

    @pytest.mark.parametrize("p", [poll(check=False), poll(only_initiator=True), poll(check=False, only_initiator=True)])
    def test_ended_shows_everyone(self, p):
        p.end_at = NOW
        assert visibility(p, "member") == (True, True)

    def test_anonymous_never_names(self):
        assert visibility(poll(show_name=False), "creator") == (True, False)
        assert visibility(poll(show_name=False, ended=True), "member") == (True, False)

    def test_modes(self):
        assert results_mode(poll()) == "everyone"
        assert results_mode(poll(only_initiator=True)) == "creator_only"


class TestViewerRole:
    def test_creator(self):
        assert viewer_role(poll(creator_id=5), 5, is_owner=False, creator_in_guild=True) == "creator"

    def test_other_member(self):
        assert viewer_role(poll(creator_id=5), 6, is_owner=False, creator_in_guild=True) == "member"

    def test_bot_owner(self):
        assert viewer_role(poll(creator_id=5), 6, is_owner=True, creator_in_guild=True) == "creator"

    def test_creator_left_guild(self):
        assert viewer_role(poll(creator_id=5), 6, is_owner=False, creator_in_guild=False) == "creator"

    def test_can_manage(self):
        assert can_manage("creator") is True
        assert can_manage("member") is False


def valid(**overrides):
    args = {"title": "標題", "options": ["甲", "乙"], "number_of_user_votes": 1, "role_weights": {}, "deadline": None, "now": NOW}
    args.update(overrides)
    return validate_poll_input(**args)


def paths(errors):
    return [e["path"] for e in errors]


class TestValidate:
    def test_ok(self):
        assert valid() == []

    def test_title_limits(self):
        assert valid(title="字" * 45) == []
        assert paths(valid(title="字" * 46)) == ["title"]
        assert paths(valid(title="   ")) == ["title"]

    def test_option_count(self):
        assert paths(valid(options=[])) == ["options"]
        assert valid(options=[str(i) for i in range(20)]) == []

    def test_too_many_options(self):
        errors = valid(options=[str(i) for i in range(21)])
        assert "options" in paths(errors)

    def test_option_length_empty_duplicate(self):
        assert paths(valid(options=["字" * 81, "乙"])) == ["options[0]"]
        assert valid(options=["字" * 80, "乙"]) == []
        assert paths(valid(options=["甲", " "])) == ["options[1]"]
        assert paths(valid(options=["甲", "乙", "甲 "])) == ["options[2]"]

    def test_number_of_votes_range(self):
        assert valid(number_of_user_votes=2) == []
        assert paths(valid(number_of_user_votes=3)) == ["number_of_user_votes"]
        assert paths(valid(number_of_user_votes=0)) == ["number_of_user_votes"]

    def test_weights(self):
        assert valid(role_weights={1: 1, 2: 10}) == []
        assert paths(valid(role_weights={1: 0, 2: 11})) == ["role_weights[1]", "role_weights[2]"]

    def test_deadline_future_truncates_seconds(self):
        # NOW 為 12:00:30，截止 12:00:50 捨去秒數後是 12:00:00，不晚於現在
        assert paths(valid(deadline=NOW.replace(second=50))) == ["deadline"]
        assert valid(deadline=NOW + timedelta(minutes=1)) == []

    def test_deadline_past_and_too_far(self):
        assert paths(valid(deadline=NOW - timedelta(minutes=1))) == ["deadline"]
        assert valid(deadline=(NOW + timedelta(days=30)).replace(second=0)) == []
        assert paths(valid(deadline=NOW + timedelta(days=30, minutes=1))) == ["deadline"]

    def test_deadline_needs_timezone(self):
        assert paths(valid(deadline=datetime(2027, 1, 1))) == ["deadline"]
