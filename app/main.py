from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import db
from app.routers import admin, agents, cases


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db(reset=False)
    if db.is_empty():
        from seed_db import seed

        seed(reset=False)
    yield


app = FastAPI(
    title="Track C: Department Network",
    description=(
        "Multi-agent civic complaint routing. Each department agent queries only "
        "its own registry; the jurisdiction matrix is the only shared knowledge. "
        "See /docs for the full API, and ARCHITECTURE.md in the repo for the design."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Permissive by default so any frontend origin can integrate during the
# hackathon. Tighten `allow_origins` before any real deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(cases.router)
app.include_router(agents.router)
app.include_router(admin.router)


@app.get("/health")
def health():
    return {"status": "ok"}
