import pytest

import sentry_bootstrap as sentry_init


@pytest.fixture(autouse=True)
def reset_sentry_state(monkeypatch):
    class FakeSdk:
        def __init__(self):
            self._captured = None

        def init(self, **kwargs):
            del kwargs

        def set_tag(self, *args, **kwargs):
            del args, kwargs

        def capture_exception(self, exc):
            self._captured = exc

        def push_scope(self):
            class _Scope:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, exc_type, exc, tb):
                    del exc_type, exc, tb
                    return False

                def set_tag(self_inner, key, value):
                    del key, value

                def set_extra(self_inner, key, value):
                    del key, value

            return _Scope()

    monkeypatch.setattr(sentry_init, "sentry_sdk", FakeSdk())
    sentry_init._SENTRY_INITIALIZED = False
    yield
    sentry_init._SENTRY_INITIALIZED = False


def test_init_sentry_skipped_when_disabled(monkeypatch):
    init_called = {"value": False}

    def fake_init(*args, **kwargs):
        del args, kwargs
        init_called["value"] = True

    monkeypatch.setattr(sentry_init, "_read_bool", lambda key, default: False if key == "SENTRY_ENABLED" else default)
    monkeypatch.setattr(sentry_init, "_read_setting", lambda key, default=None: None)
    monkeypatch.setattr(sentry_init.sentry_sdk, "init", fake_init)

    assert sentry_init.init_sentry(service="tests") is False
    assert init_called["value"] is False


def test_init_sentry_called_when_enabled(monkeypatch):
    settings = {
        "SENTRY_DSN": "https://examplePublicKey@o0.ingest.sentry.io/0",
        "SENTRY_ENVIRONMENT": "testing",
        "SENTRY_RELEASE": "1.2.0-test",
    }

    init_args = {}

    def fake_init(**kwargs):
        init_args.update(kwargs)

    monkeypatch.setattr(sentry_init, "_read_bool", lambda key, default: True if key == "SENTRY_ENABLED" else default)
    monkeypatch.setattr(sentry_init, "_read_float", lambda key, default: 0.0)
    monkeypatch.setattr(sentry_init, "_read_setting", lambda key, default=None: settings.get(key, default))
    monkeypatch.setattr(sentry_init.sentry_sdk, "init", fake_init)
    monkeypatch.setattr(sentry_init.sentry_sdk, "set_tag", lambda *args, **kwargs: None)

    assert sentry_init.init_sentry(service="tests") is True
    assert init_args["dsn"] == settings["SENTRY_DSN"]
    assert init_args["environment"] == "testing"
    assert init_args["release"] == "1.2.0-test"
    assert init_args["traces_sample_rate"] == 0.0


def test_before_send_sanitizes_sensitive_fields():
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer abc",
                "Cookie": "jwt=123",
            },
            "data": {
                "access_token": "secret-token",
                "message": "x" * 500,
                "normal": "ok",
            },
        }
    }

    sanitized = sentry_init.before_send(event, {})

    assert sanitized is not None
    assert sanitized["request"]["headers"]["Authorization"] == "[Filtered]"
    assert sanitized["request"]["headers"]["Cookie"] == "[Filtered]"
    assert sanitized["request"]["data"]["access_token"] == "[Filtered]"
    assert len(sanitized["request"]["data"]["message"]) == 120
    assert sanitized["request"]["data"]["normal"] == "ok"


def test_capture_exception_safe_uses_scope_when_tags_or_extras(monkeypatch):
    captured = {"exception": None, "tags": {}, "extras": {}}

    class FakeScope:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

        def set_tag(self, key, value):
            captured["tags"][key] = value

        def set_extra(self, key, value):
            captured["extras"][key] = value

    monkeypatch.setattr(sentry_init.sentry_sdk, "push_scope", lambda: FakeScope())
    monkeypatch.setattr(sentry_init.sentry_sdk, "capture_exception", lambda exc: captured.update({"exception": exc}))

    err = ValueError("boom")
    sentry_init.capture_exception_safe(
        err,
        tags={"service": "tests"},
        extras={"authorization": "secret", "message": "hello"},
    )

    assert captured["exception"] is err
    assert captured["tags"]["service"] == "tests"
    assert captured["extras"]["authorization"] == "[Filtered]"
    assert captured["extras"]["message"] == "hello"
