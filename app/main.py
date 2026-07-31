from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, engine
from app import models  # noqa: F401  -- registers the tables before create_all()
from app.routers import projects, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Mini User and Project Management API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(users.router)
app.include_router(projects.router)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
