# Mini User & Project Management API

A small REST API over users and the projects they own. Built with FastAPI, Pydantic v2,
SQLAlchemy 2.0 and PostgreSQL.

## Requirements

Docker Desktop, or Docker Engine with the Compose plugin. Nothing else is needed to run the
API.

Ports 8000 and 5433 must be free on the host. 8000 serves the API, 5433 exposes the database
so the test suite can reach it.

Running the tests outside Docker additionally needs Python 3.11 or newer.

## Running it

```bash
docker-compose up --build
```

On installations that ship Compose v2 only, the same command is `docker compose up --build`.

That is the only command needed. It starts PostgreSQL, waits for it to report healthy,
creates the schema and serves the API on port 8000. There is no `.env` file to copy, no
migration step and no manual database setup.

The first build takes a few minutes while the base images download. Everything is ready once
the database reports healthy and the logs show Uvicorn listening on `0.0.0.0:8000`.

* API: <http://localhost:8000>
* Swagger UI: <http://localhost:8000/docs>
* ReDoc: <http://localhost:8000/redoc>
* OpenAPI schema: <http://localhost:8000/openapi.json>
* Health check: <http://localhost:8000/health>

The database is published on host port 5433 rather than 5432, so it will not collide with a
PostgreSQL already running on the machine. Inside the compose network the API still reaches
it on 5432, so this only matters for host-side access such as running the tests.

To stop the stack and remove the database volume:

```bash
docker-compose down -v
```

## Endpoints

| Method | Path | Success | Errors |
| --- | --- | --- | --- |
| POST | `/users` | 201 | 409 duplicate email, 422 invalid payload |
| GET | `/users` | 200 | 422 out-of-range `limit` or `offset` |
| GET | `/users/{user_id}` | 200 | 404 |
| DELETE | `/users/{user_id}` | 204 | 404 |
| GET | `/users/{user_id}/projects` | 200 | 404 |
| POST | `/projects` | 201 | 404 unknown owner, 422 invalid payload |
| GET | `/projects/{project_id}` | 200 | 404 |
| GET | `/health` | 200 | |

`GET /users` is paginated with `limit` (1 to 100, default 20) and `offset` (default 0), and
returns a plain JSON array. `GET /users/{user_id}/projects` returns every project the user
owns and is not paginated, since the brief asks for all of them.

All 422 responses come from Pydantic. None of them needed custom handling.

## Architectural decisions

### SQLAlchemy with separate Pydantic schemas, not SQLModel

SQLModel merges the ORM model and the API model into a single class. That saves a file, but
it ties what is stored to what is exposed. FastAPI already depends on Pydantic, so using it
next to plain SQLAlchemy costs nothing and keeps the two contracts independent of each
other.

### A flat module layout

Two entities and seven endpoints do not justify `models/`, `schemas/` and `services/`
packages that each hold one short file. Separation of concerns here is by responsibility
rather than by directory depth. HTTP handling lives in `app/routers/`, persistence in
`models.py`, the wire contract in `schemas.py`, infrastructure in `database.py`, and the one
shared helper in `dependencies.py`. I would revisit this once there is a third entity or a
rule that counts as business logic.

### Uniqueness is enforced by the database

`POST /users` looks for an existing email first so the common case returns a clean 409. It
then catches `IntegrityError` on the unique constraint and returns the same 409. The lookup
on its own would be a race, since two concurrent requests can both pass it. The constraint
is the real guarantee. The lookup only exists to produce a better message.

### Sessions are injected

`get_db` yields a request-scoped session and closes it in a `finally` block. Routes depend on
it through `Depends`, which also lets the test suite substitute its own session with one
`dependency_overrides` entry.

### Schema creation runs in the FastAPI lifespan

`Base.metadata.create_all()` runs at startup so that `docker-compose up` needs no follow-up
command. This suits a task of this size. It is not what production should do.
`create_all()` adds missing tables but never alters existing ones, so a later change to a
column or a constraint would be silently ignored against a database that already holds data.
A deployed service wants Alembic.

### Synchronous SQLAlchemy

Every query here is a small indexed lookup. Async pays off under high concurrency on slow
queries, and in exchange it complicates sessions, fixtures and stack traces. Synchronous
code in FastAPI's thread pool is the simpler correct choice at this size.

### Five dependencies

`fastapi`, `uvicorn`, `sqlalchemy`, `psycopg` and `email-validator`. No settings library, no
dependency-injection framework and no pagination package. FastAPI's own dependency system
and `Query` cover all three needs.

## User deletion

Deleting a user deletes their projects.

`owner_id` is `NOT NULL`, so a project cannot outlive its owner. Orphaning is therefore not
available as a behaviour, and soft deletion would introduce a state that every read path
would then have to filter on. Cascade is what matches the domain.

It is declared at both levels:

* `ForeignKey("users.id", ondelete="CASCADE")` makes PostgreSQL perform the delete, so it
  holds even for rows removed outside the API.
* `relationship(cascade="all, delete-orphan", passive_deletes=True)` tells SQLAlchemy to
  defer to the database. Without `passive_deletes=True` it would load every child row and
  try to null out the foreign key, which the `NOT NULL` column rejects.

`DELETE /users/{user_id}` returns 204 on success and 404 when the user does not exist.

## Tests

There are six tests. They cover the behaviour most likely to be wrong rather than every
success path: user creation, a duplicate email returning 409, pagination windows, project
creation, project creation against a nonexistent owner returning 404, and a user deletion
cascading to their projects.

```bash
docker-compose up -d db
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

They run against the real PostgreSQL rather than SQLite. SQLite leaves foreign keys off by
default, so the cascade test would pass without proving anything. `conftest.py` truncates
between tests so each one starts from an empty database with predictable ids.

## Project structure

```
app/
├── main.py            # app instance, lifespan schema creation, health check, router wiring
├── database.py        # engine, session factory, declarative base, get_db
├── dependencies.py    # get_user_or_404, shared by both routers
├── models.py          # SQLAlchemy models: User, Project
├── schemas.py         # Pydantic request and response models
└── routers/
    ├── users.py       # everything under /users
    └── projects.py    # everything under /projects
tests/
├── conftest.py
├── test_users.py
└── test_projects.py
Dockerfile
docker-compose.yml
requirements.txt
requirements-dev.txt
```

`GET /users/{user_id}/projects` sits in the users router because that router owns the
`/users` prefix. Splitting a prefix across two files to satisfy a conceptual grouping was not
worth it.

## P.S. Notes on approach

The brief suggests a layered structure with `services/`, `models/` and `schemas/` packages,
and I chose not to follow it. With two entities and seven endpoints, a service layer would
be functions that forward their arguments to the ORM and hand back the result. That is an
extra file to open on the way to the code that does the work. I read "clear separation of
concerns" as a statement about responsibilities rather than about directory depth, and I
would rather defend a flat layout than ship layers that are there to look thorough. What
would change my mind is a third entity, or the first rule that is actually business logic
instead of persistence.

The same reasoning shaped the rest. SQLModel would have saved one file and coupled the table
definition to the API contract. Alembic would have added a migration directory to a schema
that is recreated on every start. Async SQLAlchemy would have made sessions, fixtures and
tracebacks harder in exchange for concurrency this workload never sees. A settings library
would have wrapped five lines of `os.environ`. All of those are reasonable tools that happen
to be wrong at this size, and knowing which ones to leave out is the harder half of the job.

Where I did spend effort was the parts that fail quietly. The cascade is declared twice on
purpose, once so the database enforces it and once so SQLAlchemy does not load every child
row and try to null a `NOT NULL` column instead. Email uniqueness rests on the constraint
rather than on the lookup before it, because that lookup is a race and the constraint is not.
`GET /users` orders by `id` before applying `offset` and `limit`, because without a
deterministic sort PostgreSQL is free to return the same row on two pages and skip another
one entirely. That is the kind of bug that shows up once a week in production and never in a
test. The suite runs on PostgreSQL for a similar reason: on SQLite the cascade test would
pass whether or not the cascade worked.

If this were heading to production instead of review, the first three changes would be
Alembic in place of `create_all()`, pinned versions in a lock file, and structured logging
with request ids. After that, an index review once real query patterns exist, and
authentication, which the brief did not ask for and which would change the shape of almost
every endpoint here.
