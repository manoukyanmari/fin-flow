from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app import models  # noqa: F401  -- registers the tables before create_all()
from app.routers import projects, users

OPENAPI_TAGS = [
    {"name": "Users", "description": "Create, retrieve, list and delete users."},
    {"name": "Projects", "description": "Projects, each owned by exactly one user."},
    {"name": "Health", "description": "Liveness probe."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Mini User and Project Management API",
    version="1.0.0",
    description="A small REST API over users and the projects they own.",
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(projects.router)


@app.get("/health", tags=["Health"], summary="Health check")
def health_check() -> dict[str, str]:
    """Return 200 while the application is running."""
    return {"status": "ok"}
