from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from starlib import twitch_enforcement


@pytest.mark.parametrize(("rows", "has_next"), [(49, False), (50, False), (51, True)])
def test_enforcement_page_uses_extra_row_only_as_lookahead(monkeypatch, rows, has_next):
    monkeypatch.setattr(twitch_enforcement, "_entry_json", lambda row: {"id": row})
    session = SimpleNamespace(exec=Mock())
    session.exec.return_value.all.return_value = list(range(rows))

    result = twitch_enforcement.page_json(twitch_enforcement.list_page(session, twitch_id=1, offset=50))

    query = session.exec.call_args.args[0]
    assert 51 in query.compile().params.values()
    assert result["has_next"] is has_next
    assert len(result["entries"]) == min(rows, 50)
