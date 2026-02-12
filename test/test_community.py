import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from starlib.providers.social.models import RettiwtTweetUser  # noqa: E402
from starlib.providers.social.platforms import CLIInterface  # noqa: E402

pytestmark = pytest.mark.integration

TEST_USER = os.getenv("RETTIWT_TEST_USER", "")


@pytest.fixture(scope="module")
def cli_interface():
    if shutil.which("rettiwt") is None:
        pytest.skip("rettiwt CLI not found in PATH")

    cli = CLIInterface()
    if not getattr(cli, "rettiwt_api_key", None):
        pytest.skip("Rettiwt API key is not configured in sqldb")

    return cli


def test_get_user_details_live(cli_interface):
    user = cli_interface.get_user_details(TEST_USER)

    assert user is not None, "Expected user details from live Rettiwt call"
    assert isinstance(user, RettiwtTweetUser)
    assert user.id
    assert user.userName


def test_get_user_details_accepts_at_symbol(cli_interface):
    plain_user = cli_interface.get_user_details(TEST_USER)
    prefixed_user = cli_interface.get_user_details(f"@{TEST_USER}")

    assert plain_user is not None and prefixed_user is not None
    assert plain_user.id == prefixed_user.id


def test_get_user_details_invalid_user(cli_interface):
    user = cli_interface.get_user_details("this_user_should_not_exist_987654321")

    assert user is None
