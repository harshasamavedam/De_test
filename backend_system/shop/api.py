"""FastAPI application for the shop commerce platform.

Run with:
    uvicorn shop.api:app --host 0.0.0.0 --port 8100 --reload
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .repository import ShopRepository
from .routes import router
from .service import ShopService
from .ui import router as ui_router


def create_app(host: str | None = None, port: int | None = None,
               keyspace: str | None = None) -> FastAPI:
    host = host or os.getenv("SHOP_CASSANDRA_HOST", "127.0.0.1")
    port = port or int(os.getenv("SHOP_CASSANDRA_PORT", "9042"))
    keyspace = keyspace or os.getenv("SHOP_KEYSPACE", "shop")

    app = FastAPI(
        title="Shop Commerce Platform API",
        description="Traffic, cart, orders and payments on the shop keyspace.",
        version="1.0.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    repository = ShopRepository(host=host, port=port, keyspace=keyspace)
    repository.connect()
    app.state.shop_repository = repository
    app.state.shop_service = ShopService(repository)

    app.include_router(router)
    app.include_router(ui_router)

    @app.get("/", tags=["meta"])
    def root():
        return {"service": "shop", "status": "running", "keyspace": keyspace, "ui": "/ui"}

    @app.on_event("shutdown")
    def shutdown():
        repository.close()

    return app


app = create_app()
