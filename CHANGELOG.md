# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.2.0] 2026-11-27

- Improved CI/CD workflows. @xcalts

## [v0.1.0] 2026-11-27

- `GET /events/{day}` returns the events of a Proton Calendar for one day (`DD-Mon-YYYY`, e.g. `11-Dec-2025`). @xcalts
- `GET /health` for health checks. @xcalts
- Interactive API documentation at `/docs` (Swagger UI) and `/redoc`. @xcalts
- API key authentication with the `X-API-KEY` header. @xcalts
- Configuration with environment variables or a `.env` file: `TIMEZONE`, `X_API_KEY`, `PROTON_CALENDAR_URL` and `DEBUG`. The API refuses to start if a value is missing or invalid. @xcalts
- The calendar share link, which contains the decryption key, is treated as a secret. @xcalts
- Test suite with 100% line and branch coverage, enforced in CI. @xcalts