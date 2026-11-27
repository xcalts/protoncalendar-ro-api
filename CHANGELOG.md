# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.1.0] 2026-11-27

First release.

### Added

- `GET /events/{day}` returns the events of a Proton Calendar for one day (`DD-Mon-YYYY`, e.g. `11-Dec-2025`).
  - Each event has the calendar name, title, start and end time (`HH:MM`, empty for all-day events) and time zone.
  - "A day" and the event times use the configured `TIMEZONE`.
  - All-day events come first, then events by start time.
  - Recurring events are expanded, including exceptions and modified occurrences. A malformed recurring event is skipped instead of failing the whole day.
- `GET /health` for health checks.
- Interactive API documentation at `/docs` (Swagger UI) and `/redoc`.
- API key authentication with the `X-API-KEY` header.
- Configuration with environment variables or a `.env` file: `TIMEZONE`, `X_API_KEY`, `PROTON_CALENDAR_URL` and `DEBUG`. The API refuses to start if a value is missing or invalid.
- Clear error responses: `401` for a wrong or missing API key, `404` when Proton rejects the calendar link, `422` for an invalid date, and `502` when the calendar cannot be downloaded or parsed.
- The calendar share link, which contains the decryption key, is treated as a secret:
  - It is never written to the logs.
  - The API only sends it to `calendar.proton.me` over HTTPS, including on redirects.
  - Event responses are sent with `Cache-Control: no-store`.
- Docker image that runs as a non-root user, contains no development tools or secrets, and has a `HEALTHCHECK`. The port is configurable with `UVICORN_PORT`.
- GitHub Actions: CI (lint, tests on Python 3.12 to 3.14, Docker smoke test) and publishing to Docker Hub on version tags.
- Test suite with 100% line and branch coverage, enforced in CI.
