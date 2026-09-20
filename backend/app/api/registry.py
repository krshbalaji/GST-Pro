from fastapi import FastAPI
from .domain import router as domain_router


def register_domain_routes(app: FastAPI) -> None:
    app.include_router(domain_router)
