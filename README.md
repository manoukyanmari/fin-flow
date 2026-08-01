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

## Trying it out

The database starts empty, so there are no preloaded users.

### Quick check

```bash
curl localhost:8000/health                # {"status":"ok"}
curl localhost:8000/users                 # []
```

An empty array is the correct response before anything has been created.

### Optional: load sample data

```bash
docker-compose exec api python seed.py
```

This inserts two users and two projects, so there is something to look at without typing
anything first. It prints what it created:

```
user 1: Anahit Sargsyan <anahit@example.com>
user 2: Narek Petrosyan <narek@example.com>
project 1: Billing Service (owner 1)
project 2: Internal Dashboard (owner 1)
```

Running it twice does nothing. It prints `Database already contains users. Nothing inserted.`
and stops.

The rows are temporary sample data for reviewing the API, standing in until there is real
data. Nothing in the application reads them or depends on them, and deleting them, or the
volume, changes nothing about how the service behaves. The seed produces exactly the state
that steps 1, 2, 5 and 6 below would produce by hand, so you can seed and then start at step
3.

### Manual walkthrough

The sequence below covers every endpoint and every error case in a few minutes. Paste the
bodies into Swagger UI at <http://localhost:8000/docs>, or use the curl equivalents.

On a fresh database the ids come out as written here, since the sequences start at 1.

1. `POST /users` with `{"name": "Anahit Sargsyan", "email": "anahit@example.com"}` returns 201 and
   user id 1.
2. `POST /users` with `{"name": "Narek Petrosyan", "email": "narek@example.com"}` returns 201
   and user id 2.
3. `POST /users` with `anahit@example.com` again returns 409.
4. `POST /users` with `{"name": "Anahit", "email": "not-an-email"}` returns 422.
5. `POST /projects` with
   `{"name": "Billing Service", "description": "A general purpose machine", "owner_id": 1}`
   returns 201 and project id 1.
6. `POST /projects` with `{"name": "Internal Dashboard", "owner_id": 1}` returns 201 and project id 2,
   with `description` set to null.
7. `POST /projects` with `{"name": "Orphan", "owner_id": 999}` returns 404, because the
   owner does not exist.
8. `GET /users?limit=1&offset=1` returns only Narek, which shows the pagination window
   moving.
9. `GET /users/1/projects` returns both of Anahit's projects.
10. `GET /users/999/projects` returns 404 rather than an empty list.
11. `DELETE /users/1` returns 204.
12. `GET /projects/1` and `GET /projects/2` now return 404. Deleting Anahit removed her
    projects through the database cascade.
13. `GET /users/2` still returns Narek, and `GET /users` shows her alone.

The same walkthrough as curl, for the first few steps:

```bash
curl -X POST localhost:8000/users \
  -H 'Content-Type: application/json' \
  -d '{"name": "Anahit Sargsyan", "email": "anahit@example.com"}'

curl -X POST localhost:8000/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "Billing Service", "owner_id": 1}'

curl localhost:8000/users/1/projects
```

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

Thirteen tests. Each one is here because something specific would break silently without it,
rather than to cover every success path.

* **User creation, and a duplicate email returning 409.** The second is the one that earns
  its place: it proves uniqueness is actually enforced rather than assumed.
* **Emails are stored lowercase.** `create_user` lowercases the address before saving. Remove
  that line and every other test still passes, but the unique constraint compares bytes, so
  `ANAHIT@Example.COM` and `anahit@example.com` would become two accounts for one person.
  This test is what keeps uniqueness case insensitive.
* **422 on an invalid email, a blank name, and a project with no owner.** These hold the
  Pydantic constraints in place. Drop `min_length=1` and a user with an empty name would be
  created without complaint. The third also separates two failures worth distinguishing: 422
  means `owner_id` was missing, 404 means it was supplied but pointed at nobody.
* **Pagination returns the correct window, in order.** The ordering assertion is deliberate.
  `OFFSET` and `LIMIT` without an `ORDER BY` have no guaranteed row order in PostgreSQL, so
  pages could repeat one row and skip another. Comparing an exact ordered list is what
  catches that.
* **Project creation, and creation against an owner who does not exist returning 404.**
  Confirms ownership is validated before insert rather than left to the foreign key.
* **Listing a user's projects, in three parts.** Only that user's projects come back, a
  missing user returns 404, and a user who exists with nothing returns an empty list. The
  three matter together rather than separately: with only the first two, an implementation
  that returned 404 whenever the query found no rows would still pass, and a new user who had
  simply not created anything would be told they do not exist.
* **Deleting a user removes every project they own.** The failure this guards against is
  quiet. Without `passive_deletes=True`, SQLAlchemy would load the child rows and try to null
  a `NOT NULL` foreign key instead of letting the database cascade.

Between them every status code in the table above is asserted: 200, 201, 204, 404, 409 and
422, and every endpoint has at least one test.

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
seed.py                # optional sample rows, not used by the application
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

## A note on tooling

I used Claude Opus while building this, mostly to pressure test the architectural decisions
described above. Whether SQLModel was worth the coupling, how much structure two entities
actually justify, where the delete cascade belongs, and which dependencies to leave out were
all worked through that way before anything was written. It was also useful for the quieter
failure modes, such as the missing `ORDER BY` on the paginated query and the interaction
between `passive_deletes` and a `NOT NULL` foreign key.

The decisions here are mine and I am happy to walk through the reasoning behind any of them.
