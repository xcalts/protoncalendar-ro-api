import os
import pathlib
import subprocess
import sys

import pydantic
import pytest

import api.core.config
import tests.conftest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _settings(**overrides):
    values = {
        "TIMEZONE": "Europe/Athens",
        "X_API_KEY": "key",
        "PROTON_CALENDAR_URL": tests.conftest.CALENDAR_URL,
    } | overrides
    return api.core.config.Settings(_env_file=None, **values)


def test_loads_valid_settings():
    loaded = _settings(TIMEZONE="UTC", X_API_KEY="abc")
    assert loaded.TIMEZONE == "UTC"
    assert loaded.X_API_KEY.get_secret_value() == "abc"
    assert loaded.PROTON_CALENDAR_URL.get_secret_value() == tests.conftest.CALENDAR_URL
    assert loaded.DEBUG is False


def test_calendar_url_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("PROTON_CALENDAR_URL", f"  {tests.conftest.CALENDAR_URL}\n")
    loaded = api.core.config.Settings(_env_file=None)
    # Surrounding whitespace (e.g. from a ".env" file) is removed.
    assert loaded.PROTON_CALENDAR_URL.get_secret_value() == tests.conftest.CALENDAR_URL


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        f"https://evil.example/?PassphraseKey={tests.conftest.SECRET}",
        tests.conftest.CALENDAR_URL.replace("https://", "http://"),
    ],
)
def test_rejects_invalid_calendar_urls_without_revealing_them(url):
    with pytest.raises(pydantic.ValidationError, match="PROTON_CALENDAR_URL") as exc:
        _settings(PROTON_CALENDAR_URL=url)
    for rendering in (str(exc.value), repr(exc.value)):
        # pydantic shortens long inputs in the middle, so checking for the whole
        # secret is not enough: the input must not be rendered at all.
        assert "input_value" not in rendering
        assert tests.conftest.SECRET not in rendering


def test_startup_failure_does_not_print_the_calendar_url():
    """End-to-end: what a misconfigured server actually prints when it refuses to
    start."""

    bad_url = tests.conftest.CALENDAR_URL.replace("https://", "http://")
    result = subprocess.run(
        [sys.executable, "-c", "import api.core.config"],
        cwd=ROOT,
        env=os.environ | {"PROTON_CALENDAR_URL": bad_url},
        capture_output=True,
        text=True,
        timeout=30,
    )

    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "PROTON_CALENDAR_URL must be a Proton Calendar share link" in output
    assert "input_value" not in output
    assert tests.conftest.SECRET not in output


@pytest.mark.parametrize("timezone", ["Mars/Olympus_Mons", "", "../../etc/passwd"])
def test_rejects_unknown_timezone(timezone):
    with pytest.raises(pydantic.ValidationError, match="time zone"):
        _settings(TIMEZONE=timezone)


@pytest.mark.parametrize("api_key", ["", "   "])
def test_rejects_empty_api_key(api_key):
    with pytest.raises(pydantic.ValidationError, match="X_API_KEY"):
        _settings(X_API_KEY=api_key)


def test_requires_timezone_api_key_and_calendar_url(monkeypatch):
    monkeypatch.delenv("TIMEZONE")
    monkeypatch.delenv("X_API_KEY")
    monkeypatch.delenv("PROTON_CALENDAR_URL")
    with pytest.raises(pydantic.ValidationError) as exc_info:
        api.core.config.Settings(_env_file=None)
    assert {error["loc"][0] for error in exc_info.value.errors()} == {
        "TIMEZONE",
        "X_API_KEY",
        "PROTON_CALENDAR_URL",
    }


def test_secrets_are_never_rendered():
    loaded = _settings(X_API_KEY="do-not-print-me")
    for rendering in (repr(loaded), str(loaded), loaded.model_dump_json()):
        assert "do-not-print-me" not in rendering
        assert tests.conftest.SECRET not in rendering


def test_module_level_timezone_matches_settings():
    assert (
        str(api.core.config.tz) == api.core.config.settings.TIMEZONE == "Europe/Athens"
    )
