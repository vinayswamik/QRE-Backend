# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Added baseline API hardening headers (CSP, HSTS on HTTPS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).
- Added per-client in-memory rate limiting for `POST /api/v1/qasm/validate` and `POST /api/v1/qasm/analyze`.
- Added configurable rate-limit settings in `app/core/config.py`.
- Added ADR documenting launch hardening decisions.
