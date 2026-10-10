import pytest

from starServer.redirects import is_allowed_return_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/",
        "https://cup.example.com/admin/",
        "https://CUP.Example.com/path?x=1#top",
        "https://a.b.example.com",
    ],
)
def test_same_site_urls_are_allowed(url: str):
    assert is_allowed_return_url(url, "example.com")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/",
        "https://example.com.evil.com/",
        "https://evilexample.com/",
        "https://evil.com/?https://cup.example.com",
        "https://cup.example.com@evil.com/",
        "https://evil.com\\@cup.example.com/",
        "http://cup.example.com/",  # 非本機一律要 https
        "//cup.example.com/",
        "/admin",
        "javascript:alert(1)",
        "https://cup.example.com/\n",
        "https://[",
        "",
    ],
)
def test_other_urls_are_rejected(url: str):
    assert not is_allowed_return_url(url, "example.com")


def test_localhost_allows_http_for_development():
    assert is_allowed_return_url("http://localhost:5173/admin/", "localhost")
    assert not is_allowed_return_url("http://evil.com/", "localhost")
