# Security policy

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately on GitHub instead: [Report a vulnerability](https://github.com/xcalts/protoncalendar-ro-api/security/advisories/new) (the **Security** tab → **Report a vulnerability**).

Include:

- what an attacker can do, and under which conditions,
- the steps or a proof of concept to reproduce it,
- the version (image tag) you tested.

Never include a real calendar share link or API key in a report.

This project is maintained in spare time. You can expect an acknowledgement within 7 days. Once a fix is released, the advisory is published and you are credited, unless you prefer otherwise.

## Supported versions

Only the latest release receives security fixes. Fixes ship as a new release: update by pulling the new image tag.

## Scope

In scope:

- the API code in this repository,
- the Docker image [`xcalts/protoncalendar-ro-api`](https://hub.docker.com/r/xcalts/protoncalendar-ro-api), as built by this repository.

Out of scope:

- Proton's own services: report those to Proton.
- Vulnerabilities in the image's Debian packages that Debian has not fixed yet. Each release installs every Debian security update available when it is built.
- Leaks caused by how the API is deployed, for example the share link in your shell history or the API exposed to the internet without HTTPS (see below).

## Security model

The API is designed to guarantee the following. A way to break any of them is in scope.

- **The share link stays secret.** It contains the key that decrypts the calendar. It is never written to the logs (not even with `DEBUG=true`), never included in error messages or responses, and only ever sent over HTTPS to `calendar.proton.me`. Requests to any other host, including redirects, are refused.
- **Calendar data requires the API key.** `/events` requires the `X-API-KEY` header, which is compared in constant time. Only `/health` and the API documentation (`/docs`, `/redoc`, `/openapi.json`) are public.
- **Calendar data is not cached.** Event responses carry `Cache-Control: no-store`.
- **Read-only.** The API never writes to Proton Calendar.
- **Minimal container.** The image runs as an unprivileged user (UID 10001), contains no pip or development tools, and is published with an SBOM and build provenance.

It does not provide:

- **HTTPS.** The API serves plain HTTP. If it is reachable from outside your machine or trusted network, put it behind a reverse proxy that terminates HTTPS. Otherwise the API key and your events travel unencrypted.
- **Rate limiting.** Use a long random API key, for example `openssl rand -hex 32`.
