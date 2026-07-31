# Mini User and Project Management API

A small REST API over users and the projects they own, built with FastAPI, Pydantic v2,
SQLAlchemy 2.0 and PostgreSQL.

## Running the application

```bash
docker-compose up
```

That is the only command required. It builds the API image, starts PostgreSQL, waits for
the database to become healthy, creates the schema, and serves the API on port 8000.
No `.env` file, migration step or manual database initialisation is needed.

- API: <http://localhost:8000>
- Interactive documentation (Swagger UI): <http://localhost:8000/docs>
- Alternative documentation (ReDoc): <http://localhost:8000/redoc>
- OpenAPI schema: <http://localhost:8000/openapi.json>
- Health check: <http://localhost:8000/health>

## Endpoints

| Method | Path | Success | Notes |
| --- | --- | --- | --- |
| POST | `/users` | 201 | 409 if the email is already registered |
| GET | `/users` | 200 | Paginated via `limit` (1–100, default 20) and `offset` |
| GET | `/users/{user_id}` | 200 | 404 if absent |
| DELETE | `/users/{user_id}` | 204 | 404 if absent; cascades to the user's projects |
| POST | `/projects` | 201 | 404 if the owner does not exist |
| GET | `/projects/{project_id}` | 200 | 404 if absent |
| GET | `/users/{user_id}/projects` | 200 | 404 if the user does not exist |
| GET | `/health` | 200 | Liveness probe |

Validation failures return 422, produced by Pydantic without any custom handling.

`GET /users` returns a pagination envelope rather than a bare array, so a client can tell
whether more rows exist:

```json
{ "items": [ ... ], "total": 42, "limit": 20, "offset": 0 }
```

`GET /users/{user_id}/projects` returns a plain array. The specification asks for all of a
user's projects there, so it is deliberately not paginated.

## Architectural decisions

**SQLAlchemy 2.0 with separate Pydantic schemas, not SQLModel.** SQLModel merges the ORM
model and the serialisation model into one class, which is convenient but blurs two
genuinely different responsibilities: what is stored and what is exposed. FastAPI already
depends on Pydantic, so pairing it with plain SQLAlchemy costs nothing and keeps the
request/response contract independent of the table definition.

**A flat module layout rather than nested packages.** The brief suggests `models/`,
`schemas/` and `services/` directories. With two entities and seven endpoints, those would
be packages holding one short module each, and a service layer would consist of
pass-through functions that add a file to open without adding a decision to make.
Separation of concerns here is by responsibility rather than by directory depth: HTTP
handling lives in `app/routers/`, persistence in `app/models.py`, the wire contract in
`app/schemas.py`, and infrastructure in `app/database.py`. The layout is worth revisiting
at roughly the point a third entity or any non-trivial business rule appears.

**Routers grouped by URL prefix.** `GET /users/{user_id}/projects` lives in
`routers/users.py` because that router owns the `/users` prefix; splitting a prefix across
two files to satisfy a conceptual grouping costs more than it returns. The endpoint carries
the `projects` OpenAPI tag, so `/docs` still groups it with the other project operations.

**Email uniqueness is enforced by the database.** `POST /users` attempts the insert and
converts an `IntegrityError` on the named `uq_users_email` constraint into a 409. Querying
for an existing row first would leave a window between the check and the insert in which a
concurrent request could claim the same address; the constraint is the only guarantee that
holds under concurrency.

**Sessions are injected, not imported.** `get_db` yields a request-scoped session and
closes it in a `finally` block. Routes depend on the `DbSession` alias, which lets the test
suite substitute a session with a single `dependency_overrides` entry.

**Schema creation over migrations.** `Base.metadata.create_all()` runs in the FastAPI
lifespan handler, which satisfies the requirement that the schema appear with no manual
step. Alembic is the right tool once a deployed schema has to evolve without data loss;
for a greenfield service that is recreated on every start, it would be ceremony.

**Synchronous SQLAlchemy.** Every endpoint here is a small indexed query. Async drivers
pay off under high concurrency on slow queries, and in exchange they complicate sessions,
testing and stack traces. Synchronous code running in FastAPI's thread pool is the simpler
correct choice at this size.

**Dependencies are deliberately minimal:** `fastapi`, `uvicorn`, `sqlalchemy`,
`psycopg`, and `email-validator` (which backs Pydantic's `EmailStr`). No settings library,
dependency-injection framework, or pagination package — FastAPI's own dependency system
covers all three needs.

## User deletion behaviour

**Deleting a user deletes all of their projects.** A project cannot exist without an owner,
because `owner_id` is `NOT NULL`; orphaning is therefore not an available option, and soft
deletion would add a state that every read path would then have to filter. Cascade is the
behaviour that matches the domain.

It is implemented at both levels:

- `ForeignKey("users.id", ondelete="CASCADE")` makes PostgreSQL perform the delete, so it
  is correct even for rows removed outside the API.
- `relationship(cascade="all, delete-orphan", passive_deletes=True)` tells SQLAlchemy to
  defer to the database. Without `passive_deletes=True`, SQLAlchemy would load every child
  row and try to null out its foreign key, which the `NOT NULL` column would reject.

`DELETE /users/{user_id}` returns `204 No Content` on success and `404 Not Found` if the
user does not exist. There is a test asserting that a deleted user's projects are gone.

## Running the tests

The suite runs against the real PostgreSQL service, not SQLite:

```bash
docker-compose up -d
docker-compose run --rm api pytest
```

The choice of database matters here. SQLite does not enforce foreign keys unless
`PRAGMA foreign_keys=ON` is set, so the cascade-delete test would pass without proving
anything. Running against PostgreSQL means the tests exercise the same constraint
behaviour as production.

Coverage includes creation and retrieval for both entities, the 409 duplicate-email path,
422 validation failures, 404s on every lookup, pagination windows and boundary values,
204 on delete, and the cascade from a deleted user to their projects.

## Project structure

```
app/
├── main.py            # app instance, lifespan schema creation, health check, router wiring
├── database.py        # engine, session factory, declarative base
├── dependencies.py    # get_db, user lookup helper, pagination parameters
├── models.py          # SQLAlchemy models: User, Project
├── schemas.py         # Pydantic request/response models
└── routers/
    ├── users.py       # everything under /users
    └── projects.py    # everything under /projects
tests/
├── conftest.py        # engine, client and truncation fixtures
├── test_users.py
└── test_projects.py
Dockerfile
docker-compose.yml
pyproject.toml         # ruff and pytest configuration
requirements.txt
```

## Notes

Linting and formatting are configured through ruff in `pyproject.toml`:

```bash
ruff check .
ruff format .
```

Dependencies are declared with lower bounds for readability. A production service would pin
exact versions in a lock file.
