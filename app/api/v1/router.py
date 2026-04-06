"""Version 1 API router that aggregates all sub-routers."""

from fastapi import APIRouter

from app.api.v1.routes import qasm

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(qasm.router)
