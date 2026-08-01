"""Insert a small set of sample rows so the API has something to return.

This is throwaway data for reviewing the service. Nothing in the application
reads it or depends on it. Run it deliberately:

    docker-compose exec api python seed.py

Running it a second time does nothing, because it stops when the database
already contains users.
"""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Project, User

SAMPLE_USERS = [
    {"name": "Anahit Sargsyan", "email": "anahit@example.com"},
    {"name": "Narek Petrosyan", "email": "narek@example.com"},
]

SAMPLE_PROJECTS = [
    {
        "name": "Billing Service",
        "description": "Invoicing and payment reconciliation",
        "owner_email": "anahit@example.com",
    },
    {
        "name": "Internal Dashboard",
        "description": None,
        "owner_email": "anahit@example.com",
    },
]


def main() -> None:
    with SessionLocal() as session:
        if session.scalar(select(User).limit(1)) is not None:
            print("Database already contains users. Nothing inserted.")
            return

        users: dict[str, User] = {}
        for row in SAMPLE_USERS:
            user = User(name=row["name"], email=row["email"])
            session.add(user)
            users[row["email"]] = user

        # Assigns the primary keys the projects below need.
        session.flush()

        for row in SAMPLE_PROJECTS:
            session.add(
                Project(
                    name=row["name"],
                    description=row["description"],
                    owner_id=users[row["owner_email"]].id,
                )
            )

        session.commit()

        for user in users.values():
            print(f"user {user.id}: {user.name} <{user.email}>")
        for project in session.scalars(select(Project).order_by(Project.id)):
            print(f"project {project.id}: {project.name} (owner {project.owner_id})")


if __name__ == "__main__":
    main()
