from unittest.mock import MagicMock

from sqlmodel import Session

from starlib.database.postgresql.client import CurrencyRepository


def make_repo(rowcount: int):
    session = MagicMock(spec=Session)
    session.exec.return_value.rowcount = rowcount
    return CurrencyRepository(engine=MagicMock(), session_factory=session), session


def test_transfer_insufficient_rolls_back():
    repo, session = make_repo(rowcount=0)
    assert repo.transfer_scoin(1, 2, 10) == "星塵不足"
    session.rollback.assert_called_once()
    session.commit.assert_not_called()
    assert session.exec.call_count == 1


def test_transfer_success_commits_both_updates():
    repo, session = make_repo(rowcount=1)
    assert repo.transfer_scoin(1, 2, 10) is None
    assert session.exec.call_count == 2
    session.commit.assert_called_once()
