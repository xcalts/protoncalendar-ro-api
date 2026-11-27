<a id="readme-top"></a>

[![coverage][coverage-shield]][coverage-url]
[![CI][ci-shield]][ci-url]
[![CD][cd-shield]][cd-url]
[![docker pulls][dockerhub-shield]][docker-url]
[![version][version-shield]][version-url]

# Proton calendar RO REST API

A self-hosted Proton calendar RO API that can be used to read the calendar events.

## Technologies

- [![python][python-shield]][python-url]
- [![fastapi][fastapi-shield]][fastapi-url]
- [![pydantic][pydantic-shield]][pydantic-url]
- [![uvicorn][uvicorn-shield]][uvicorn-url]
- [![docker][docker-shield]][docker-url]
- [![protoncalendar][protoncalendar-shield]][protoncalendar-url]

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Running

Create a share link in Proton Calendar (`Settings → Calendars → Share → Share with anyone`), then:

```sh
docker run -d -p 8080:80 \
  -e TIMEZONE=Europe/Rome \
  -e X_API_KEY="$(openssl rand -hex 32)" \
  -e PROTON_CALENDAR_URL='https://calendar.proton.me/api/calendar/v1/url/.../calendar.ics?CacheKey=...&PassphraseKey=...' \
  xcalts/protoncalendar-ro-api:0.2.0
```

| Variable              | Required | Description                                                                             |
| --------------------- | -------- | --------------------------------------------------------------------------------------- |
| `TIMEZONE`            | yes      | IANA time zone used to define "a day" and to format event times. |
| `X_API_KEY`           | yes      | API key that clients must send in the `X-API-KEY` header.                               |
| `PROTON_CALENDAR_URL` | yes      | The Proton Calendar share link. |
| `DEBUG`               | no       | `true` enables debug logging. Default: `false`.                                         |
| `UVICORN_PORT`        | no       | Port to listen on inside the container. Default: `80`.                                  |


<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Developing

Requires Python 3.12 or newer (3.14 is used for the Docker image).

```sh
# Create a virtual environment and install the dependencies (including the development tools).
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e . --group dev

# Configure the API.
cp .env.example .env  # then set X_API_KEY and PROTON_CALENDAR_URL

# Run the API.
uvicorn api.main:app --reload

# Run the tests.
pytest

# Lint and format the code (CI runs both in check mode).
ruff check --fix api tests
ruff format api tests
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

[coverage-shield]: https://img.shields.io/badge/coverage-100%25-brightgreen
[coverage-url]: https://github.com/xcalts/protoncalendar-ro-api/actions/workflows/develop.yml
[ci-shield]: https://img.shields.io/github/actions/workflow/status/xcalts/protoncalendar-ro-api/develop.yml?label=CI
[ci-url]: https://github.com/xcalts/protoncalendar-ro-api/actions/workflows/develop.yml
[cd-shield]: https://img.shields.io/github/actions/workflow/status/xcalts/protoncalendar-ro-api/main.yml?label=CD
[cd-url]: https://github.com/xcalts/protoncalendar-ro-api/actions/workflows/main.yml
[dockerhub-shield]: https://img.shields.io/docker/pulls/xcalts/protoncalendar-ro-api?logo=docker
[version-shield]: https://img.shields.io/github/v/tag/xcalts/protoncalendar-ro-api?sort=semver&label=version
[version-url]: CHANGELOG.md
[python-shield]: https://img.shields.io/badge/Python3.12+-black?logo=python
[python-url]: https://www.python.org/
[fastapi-shield]: https://img.shields.io/badge/FastAPI-black?logo=fastapi
[fastapi-url]: https://fastapi.tiangolo.com/
[pydantic-shield]: https://img.shields.io/badge/Pydantic-black?logo=pydantic
[pydantic-url]: https://docs.pydantic.dev/
[uvicorn-shield]: https://img.shields.io/badge/Uvicorn-black
[uvicorn-url]: https://www.uvicorn.org/
[docker-shield]: https://img.shields.io/badge/Docker-black?logo=docker
[docker-url]: https://hub.docker.com/r/xcalts/protoncalendar-ro-api
[protoncalendar-shield]: https://img.shields.io/badge/Proton%20Calendar-black?logo=protoncalendar
[protoncalendar-url]: https://proton.me/calendar
