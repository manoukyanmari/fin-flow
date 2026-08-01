# Mini User & Project Management API

A small REST API where users own projects. FastAPI, Pydantic v2, SQLAlchemy 2.0, PostgreSQL.

## What you need

Docker Desktop, or Docker Engine with the Compose plugin. Nothing else to run the API.

Ports 8000 and 5433 need to be free. 8000 serves the API, 5433 is where the database is
exposed so the tests can reach it from outside Docker.

If you want to run the tests, you'll also need Python 3.11 or newer.

## Running it

```bash
docker-compose up --build
```

That's the whole setup. It starts Postgres, waits until it's actually accepting connections,
creates the schema, and serves the API on port 8000. No `.env` to copy, no migration to run,
no database to prepare first.

If your Docker ships Compose v2 only, use `docker compose up --build`. Same thing.

The first build takes a few minutes while the base images download. You'll know it's ready
when the database reports healthy and Uvicorn says it's listening on `0.0.0.0:8000`.

* API: <http://localhost:8000>
* Swagger UI: <http://localhost:8000/docs>
* ReDoc: <http://localhost:8000/redoc>
* OpenAPI schema: <http://localhost:8000/openapi.json>
* Health check: <http://localhost:8000/health>

Why 5433 and not the usual 5432? So it won't fight with a Postgres you might already have
running. Inside the compose network the API still talks to it on 5432, so this only affects
you if you're connecting from your own machine.

Done with it:

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

`GET /users` takes `limit` (1 to 100, default 20) and `offset` (default 0) and gives you back
a plain array. `GET /users/{user_id}/projects` returns everything that user owns and isn't
paginated, because the brief asks for all of them.

The 422s come from Pydantic. I didn't write any of that handling.

## Trying it out

`docker-compose up --build` is the only step you have to run. Everything below is optional:
a quick sanity check, a script that inserts some rows, and a tour of every endpoint. Skip all
of it and the API still works exactly the same.

The database starts empty, so there's nobody in it until you create someone or run the seed.

### Quick check

```bash
curl localhost:8000/health                # {"status":"ok"}
curl localhost:8000/users                 # []
```

An empty array is the right answer here, not a sign something is wrong.

### Want some data to play with?

```bash
docker-compose exec api python seed.py
```

Not required, just saves you typing. It adds two users and two projects and tells you what it
made:

```
user 1: Anahit Sargsyan <anahit@example.com>
user 2: Narek Petrosyan <narek@example.com>
project 1: Billing Service (owner 1)
project 2: Internal Dashboard (owner 1)
```

Run it twice and nothing happens. It checks for existing users first and backs out with
`Database already contains users. Nothing inserted.`

These rows are throwaway sample data standing in until there's anything real. No part of the
application reads them, so delete them, or the whole volume, and nothing changes. The seed
leaves you in exactly the state that steps 1, 2, 5 and 6 below would, so you can seed and
jump straight to step 3.

### The full tour

Every endpoint and every error, in a few minutes. Paste the bodies into Swagger at
<http://localhost:8000/docs>, or use curl. On an empty database the ids come out exactly as
written here.

1. `POST /users` with `{"name": "Anahit Sargsyan", "email": "anahit@example.com"}` gives you
   201 and user 1.
2. `POST /users` with `{"name": "Narek Petrosyan", "email": "narek@example.com"}` gives you
   201 and user 2.
3. `POST /users` with `anahit@example.com` again gives you 409.
4. `POST /users` with `{"name": "Anahit", "email": "not-an-email"}` gives you 422.
5. `POST /projects` with
   `{"name": "Billing Service", "description": "Invoicing and payment reconciliation", "owner_id": 1}`
   gives you 201 and project 1.
6. `POST /projects` with `{"name": "Internal Dashboard", "owner_id": 1}` gives you 201 and
   project 2, with `description` set to null.
7. `POST /projects` with `{"name": "Orphan", "owner_id": 999}` gives you 404. There's no such
   owner.
8. `GET /users?limit=1&offset=1` returns Narek only. That's the pagination window moving.
9. `GET /users/1/projects` returns both of Anahit's projects.
10. `GET /users/999/projects` gives you 404, not an empty list. That distinction is
    deliberate, see below.
11. `DELETE /users/1` gives you 204.
12. `GET /projects/1` and `GET /projects/2` now give you 404. Deleting Anahit took her
    projects with her.
13. `GET /users/2` still returns Narek, and `GET /users` shows him on his own.

The first few as curl:

```bash
curl -X POST localhost:8000/users \
  -H 'Content-Type: application/json' \
  -d '{"name": "Anahit Sargsyan", "email": "anahit@example.com"}'

curl -X POST localhost:8000/projects \
  -H 'Content-Type: application/json' \
  -d '{"name": "Billing Service", "owner_id": 1}'

curl localhost:8000/users/1/projects
```

## Decisions I made, and why

### SQLAlchemy with separate Pydantic schemas, not SQLModel

SQLModel folds the table and the API model into one class. It saves a file, but it ties what
you store to what you expose, and those change for different reasons. FastAPI already brings
Pydantic along, so pairing it with plain SQLAlchemy costs nothing and keeps the two apart.

### A flat layout instead of the suggested packages

The brief suggests `models/`, `schemas/` and `services/` directories. With two entities and
seven endpoints, those would be packages holding one short file each, and the service layer
would be functions that pass their arguments straight to the ORM.

So the separation here is by responsibility, not by folder depth. Routing lives in
`app/routers/`, tables in `models.py`, the API contract in `schemas.py`, plumbing in
`database.py`, and the single shared helper in `dependencies.py`. I'd revisit it the moment
there's a third entity or a rule that's genuinely business logic.

### The database enforces email uniqueness, not the code

`POST /users` looks for the address first so you get a clean 409 in the normal case. Then it
catches `IntegrityError` on the constraint and returns the same 409.

Both, because the lookup alone is a race. Two requests can pass it before either commits. The
constraint is what actually guarantees anything; the lookup just makes the error nicer.

### Sessions come through dependency injection

`get_db` hands out a session per request and closes it in a `finally`. Routes take it via
`Depends`, which is also what lets the tests swap in their own session with a single
`dependency_overrides` line.

### Schema created at startup, no Alembic

`Base.metadata.create_all()` runs in the FastAPI lifespan, which is how `docker-compose up`
manages without a follow-up command.

Fine here. Wrong for production. `create_all()` will add a missing table but never alter an
existing one, so any later change to a column or constraint gets silently ignored on a
database that already has data in it. Real deployments want Alembic.

### Synchronous, not async

Every query in here is a small indexed lookup. Async earns its keep under heavy concurrency
on slow queries, and charges you in awkward sessions, awkward fixtures and worse tracebacks.
At this size that's a bad trade.

### Five dependencies

`fastapi`, `uvicorn`, `sqlalchemy`, `psycopg`, `email-validator`. No settings library, no DI
framework, no pagination package. FastAPI's own `Depends` and `Query` cover all three.

## What happens when you delete a user

Their projects go too.

`owner_id` is `NOT NULL`, so a project can't outlive its owner. Orphaning isn't an option,
and soft deletion would add a state that every read in the codebase then has to remember to
filter out. Cascading is what the domain actually means.

It's declared twice, on purpose:

* `ForeignKey("users.id", ondelete="CASCADE")` puts it in the database, so it holds even for
  rows deleted outside the API.
* `relationship(cascade="all, delete-orphan", passive_deletes=True)` tells SQLAlchemy to step
  back and let it. Without `passive_deletes=True` SQLAlchemy loads every child row and tries
  to null the foreign key, which a `NOT NULL` column rejects.

`DELETE /users/{user_id}` returns 204 when it works and 404 when the user isn't there.

## Tests

Thirteen of them. Each one is here because something specific would break quietly without it,
not to cover every happy path.

**User creation, and a duplicate email returning 409.** The 409 is the one worth having. It
proves uniqueness is enforced rather than hoped for.

**Emails stored lowercase.** `create_user` lowercases before saving. Take that line out and
every other test still passes, but the unique constraint compares raw bytes, so
`ANAHIT@Example.COM` and `anahit@example.com` become two accounts for one person. This test
is the only thing keeping uniqueness case insensitive.

**422 on a bad email, a blank name, and a project with no owner.** These pin the Pydantic
constraints down. Drop `min_length=1` and you can create a user with no name at all. The
third one also keeps two failures apart: 422 means `owner_id` wasn't sent, 404 means it was
sent and pointed at nobody.

**Pagination returns the right window, in order.** The ordering assertion is on purpose.
`OFFSET` and `LIMIT` without an `ORDER BY` have no guaranteed row order in Postgres, so pages
can repeat one row and skip another. Comparing an exact ordered list is what catches it.

**Project creation, and a nonexistent owner returning 404.** Confirms the owner is checked
before the insert rather than left to the foreign key to complain about.

**Listing a user's projects, three tests.** Only that user's projects come back; a missing
user gets 404; a real user with nothing gets an empty list. They only mean something
together. With just the first two, an implementation that returned 404 whenever the query
came back empty would still pass, and a brand new user would be told they don't exist.

**Deleting a user removes their projects.** This is the one that fails quietly. Without
`passive_deletes=True` SQLAlchemy would try to null a `NOT NULL` foreign key instead of
letting the database cascade.

Between them they assert every status code in the table above: 200, 201, 204, 404, 409, 422.
Every endpoint has at least one test.

Running them:

```bash
docker-compose up -d db
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

They run against real Postgres, not SQLite. SQLite leaves foreign keys off unless you ask, so
the cascade test would pass there whether or not the cascade worked, which is worse than not
having it. `conftest.py` truncates between tests, so every test starts from an empty database
with predictable ids.

## Where things live

```
app/
├── main.py            # app, lifespan schema creation, health check, routers wired in
├── database.py        # engine, session factory, Base, get_db
├── dependencies.py    # get_user_or_404, used by both routers
├── models.py          # User and Project
├── schemas.py         # request and response models
└── routers/
    ├── users.py       # everything under /users
    └── projects.py    # everything under /projects
tests/
├── conftest.py
├── test_users.py
└── test_projects.py
seed.py                # optional sample rows, nothing depends on it
Dockerfile
docker-compose.yml
requirements.txt
requirements-dev.txt
```

`GET /users/{user_id}/projects` sits in the users router because that router owns the
`/users` prefix. Splitting a prefix across two files to satisfy a conceptual grouping wasn't
worth it.

## P.S. Notes on approach

The brief suggests a layered structure and I didn't follow it. With two entities and seven
endpoints a service layer would be functions handing their arguments to the ORM and passing
the result back, which is one more file to open on the way to the code that does the work. I
took "clear separation of concerns" to be about responsibilities rather than folder depth,
and I'd rather defend a flat layout than ship layers that exist to look thorough. What would
change my mind is a third entity, or the first rule that's actually business logic.

The rest follows the same thinking. SQLModel saves a file and couples the table to the API
contract. Alembic adds a migration directory to a schema that's rebuilt on every start. Async
makes sessions, fixtures and tracebacks harder in return for concurrency this will never see.
A settings library wraps five lines of `os.environ`. All good tools, all wrong here, and
picking what to leave out is the harder half of the job.

The effort went into the things that fail quietly instead. The cascade is declared twice so
that neither the database nor the ORM is the single point of failure. Email uniqueness rests
on the constraint, not the lookup in front of it, because the lookup is a race. `GET /users`
sorts by id before paging, because without a deterministic sort Postgres can hand you the
same row on two pages and skip another one entirely, which breaks once a week in production
and never in a test. The suite runs on Postgres for the same reason: on SQLite the cascade
test passes no matter what.

If this were going to production instead of review, the first three changes would be Alembic
instead of `create_all()`, pinned versions in a lock file, and structured logging with request
ids. Then an index review once there are real query patterns, and authentication, which the
brief didn't ask for and which would reshape nearly every endpoint here.

## A note on tooling

I used Claude Opus while building this, mostly to pressure test the decisions above. Whether
SQLModel was worth the coupling, how much structure two entities really justify, where the
cascade belongs, what to leave out of the dependency list. It was useful on the quiet failure
modes too, the missing `ORDER BY` and the `passive_deletes` interaction with a `NOT NULL`
column.

The decisions are mine and I'm happy to talk through any of them.
