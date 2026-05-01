"""FastAPI application entry point with CORS, routing, and health check."""

import logging

from fastapi import FastAPI
from fastapi import Request
from fastapi import encoders as fastapi_encoders
from fastapi import exceptions as fastapi_exceptions
from fastapi.middleware.cors import CORSMiddleware
from fastapi import responses as fastapi_responses

from app.api.v1.router import api_router
from app.core import config as app_core_config

logging.basicConfig(
    level=logging.DEBUG if app_core_config.settings.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(
    title=app_core_config.settings.APP_NAME,
    version=app_core_config.settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_core_config.settings.CORS_ORIGINS,
    allow_origin_regex=app_core_config.settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Accept"],
)

app.include_router(api_router)


def _detail_for_oversized_code_field(
    exc: fastapi_exceptions.RequestValidationError,
) -> dict | None:
    """Match Pydantic string_too_long on body.code; return unified 413 detail."""

    limits = app_core_config.input_limits()
    for err in exc.errors():
        if err.get("type") != "string_too_long":
            continue
        loc = tuple(err.get("loc") or ())
        if loc != ("body", "code"):
            continue
        max_len = int(
            err.get("ctx", {}).get(
                "max_length", app_core_config.settings.MAX_QASM_BYTES
            )
        )
        raw = err.get("input")
        length_note = ""
        if isinstance(raw, str):
            length_note = (
                f" Your request is approximately {len(raw):,} characters long"
                f' (maximum {max_len:,}, field "limits.max_qasm_bytes").'
            )
        return {
            "error": "qasm_payload_too_large",
            "message": (
                "OpenQASM source text is larger than this backend accepts."
                + length_note
                + (
                    ' Use GET /api/v1/qasm/limits (field "limits" below '
                    "includes max_qasm_bytes and structural caps)."
                )
            ),
            "field": "qasm_byte_length",
            "limit": max_len,
            "limits": limits,
        }
    return None


@app.exception_handler(fastapi_exceptions.RequestValidationError)
async def request_validation_exception_handler(
    _: Request,
    exc: fastapi_exceptions.RequestValidationError,
) -> fastapi_responses.JSONResponse:
    """Return 413 for oversized body.code; otherwise default 422 detail list."""
    oversized = _detail_for_oversized_code_field(exc)
    if oversized is not None:
        return fastapi_responses.JSONResponse(
            status_code=413, content={"detail": oversized}
        )
    return fastapi_responses.JSONResponse(
        status_code=422,
        content=fastapi_encoders.jsonable_encoder({"detail": exc.errors()}),
    )


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach baseline hardening headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=63072000; includeSubDomains; preload"
        )
    return response


@app.get("/health", tags=["meta"])
def health_check() -> dict:
    """Return application status and version."""
    return {"status": "ok", "version": app_core_config.settings.APP_VERSION}
