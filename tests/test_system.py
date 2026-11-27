import pathlib
import re
import tomllib

import fastapi.testclient
import httpx

import api.main

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_check_needs_no_api_key(client):
    assert client.get("/health", headers={}).status_code == 200


def test_lifespan_manages_a_shared_http_client():
    with fastapi.testclient.TestClient(api.main.app):
        http_client = api.main.app.state.http_client
        assert isinstance(http_client, httpx.Client)
        assert not http_client.is_closed
    assert http_client.is_closed


def test_openapi_schema(client):
    schema = client.get("/openapi.json").json()

    assert schema["info"]["license"]["name"] == "GPL-3.0-only"
    operation = schema["paths"]["/events/{day}"]["get"]
    assert {"X-API-KEY": []} in operation["security"]
    params = {p["name"]: p for p in operation["parameters"]}
    assert params["day"]["schema"]["examples"] == ["11-Dec-2025"]
    assert "url" not in params
    assert {"401", "404", "422", "502"} <= set(operation["responses"])


def test_versions_are_in_sync():
    """The release workflow and the bump script rely on these staying equal."""

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]

    assert api.main.app.version == version
    bake = (ROOT / "docker-bake.hcl").read_text()
    assert re.search(
        r'variable "VERSION_TAG" \{\s*default = "' + re.escape(version) + '"', bake
    )
    readme = (ROOT / "README.md").read_text()
    assert re.findall(r"protoncalendar-ro-api:(\S+)", readme) == [version]


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins(lines) -> dict[str, str]:
    """Map normalized package names to versions for "name==version" lines."""

    pins = {}
    for line in lines:
        line = line.strip()
        if line and not line.startswith(("#", "-")):
            name, sep, version = line.partition("==")
            assert sep, f"not pinned to an exact version: {line!r}"
            pins[_normalize(name)] = version
    return pins


def test_dependencies_are_pinned():
    """The Docker image and CI install straight from pyproject.toml.

    Every dependency must be pinned to an exact version, and the development tools
    (installed only by CI and developers) must never be runtime dependencies, which
    are the only ones that enter the Docker image.
    """

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    runtime = _pins(pyproject["project"]["dependencies"])
    dev = _pins(pyproject["dependency-groups"]["dev"])

    assert runtime
    assert dev
    assert not runtime.keys() & dev.keys()
