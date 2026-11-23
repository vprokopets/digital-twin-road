# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Security Model & Intended Deployment

**Digital Twin Road** is a local cyber-physical research and engineering demonstrator.

By design, simulation control, telemetry ingestion, and scenario persistence endpoints (`/api/*`, `/dashboard/control/*`, `/dashboard/weather_data`, `/dashboard/fiware_entities/clean_idle`) are **unauthenticated** to keep local hardware-in-the-loop (e.g. Raspberry Pi weather stations), benchmarking, and interactive demonstrations frictionless.

- **Local / Trusted Lab Networks:** Safe for default execution via `./manage.sh up-local` or `./manage.sh up`.
- **Public or Untrusted Networks:** Do **not** expose port `8000` or `5173` directly to the public internet without placing the stack behind an authenticating reverse proxy (e.g. OAuth2 Proxy, mTLS, or API gateway), tightening `CORS_ORIGINS`, and restricting write/control endpoints.
- **FIWARE Profile (`--profile fiware`):** Default MongoDB and Orion containers are configured without authentication for isolated local development on the `demo-net` bridge network.

## Reporting a Vulnerability

If you discover a security vulnerability (such as path traversal, unexpected file disclosure, or accidental credential exposure), please report it privately via **GitHub Security Advisories** on the repository's **Security** tab rather than opening a public issue. If advisories are unavailable, open an issue without including exploit details and request a private contact channel.
