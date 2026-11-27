import fastapi
import pytest

import api.core.security
import tests.conftest


def test_accepts_the_configured_key():
    assert api.core.security.verify_api_key(tests.conftest.API_KEY) is None


@pytest.mark.parametrize(
    "api_key",
    [
        None,
        "",
        "wrong",
        tests.conftest.API_KEY.upper(),
        tests.conftest.API_KEY + " ",
        tests.conftest.API_KEY[:-1],
        "κλειδί",  # non-ASCII must be rejected, not crash compare_digest
        "\xe9",  # latin-1 decoded header byte
    ],
)
def test_rejects_other_keys(api_key):
    with pytest.raises(fastapi.HTTPException) as exc_info:
        api.core.security.verify_api_key(api_key)
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or missing API Key"
    assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}
