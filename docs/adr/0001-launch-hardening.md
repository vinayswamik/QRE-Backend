# ADR 0001: Launch Security Hardening Baseline

- Status: Accepted
- Date: 2026-04-18

## Context

Pre-launch checks identified missing production hardening controls:
- No explicit security headers.
- No request throttling for expensive public endpoints.
- No decision record for these operational controls.

The QRE Backend exposes computation-heavy endpoints (`/api/v1/qasm/analyze`) that can be abused without per-client throttling. We also need a clear baseline for response security headers in API responses.

## Decision

1. Add baseline HTTP security headers on all responses in the FastAPI app:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Referrer-Policy: no-referrer`
   - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
   - `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`
   - `Strict-Transport-Security` only on HTTPS requests

2. Add in-memory per-client rate limiting for:
   - `POST /api/v1/qasm/validate`
   - `POST /api/v1/qasm/analyze`

3. Make rate limiting configurable via environment-backed settings:
   - `RATE_LIMIT_ENABLED`
   - `RATE_LIMIT_WINDOW_SECONDS`
   - `RATE_LIMIT_VALIDATE_REQUESTS`
   - `RATE_LIMIT_ANALYZE_REQUESTS`

## Consequences

### Positive
- Reduces abuse risk and accidental overload.
- Establishes explicit security-header policy.
- Keeps operational controls configurable per environment.

### Negative / Trade-offs
- In-memory rate limiting is process-local (not shared across Lambda concurrency units).
- Clients behind shared NAT may share quotas.

## Follow-up

- Evaluate distributed rate limiting at API Gateway/WAF for stronger global enforcement.
- Add observability counters for 429 rates and top throttled client identifiers.
