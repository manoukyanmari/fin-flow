from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_user_or_404
from app.models import Project, User
from app.schemas import ProjectRead, UserCreate, UserRead

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    responses={409: {"description": "A user with this email already exists."}},
)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Create a user.

    Emails are normalised to lowercase and must be unique across all users.
    """
    email = payload.email.strip().lower()

    # Friendly path: report the conflict without relying on a database error.
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {email} already exists.",
        )

    user = User(name=payload.name, email=email)
    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        # The check above leaves a window in which a concurrent request can
        # claim the same address. The unique constraint is what actually
        # guarantees uniqueness, so the same 409 is returned here.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email {email} already exists.",
        ) from exc

    db.refresh(user)
    return user


@router.get(
    "",
    response_model=list[UserRead],
    summary="List users",
)
def list_users(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100, description="Maximum rows to return."),
    offset: int = Query(default=0, ge=0, description="Rows to skip."),
) -> Sequence[User]:
    """Return a page of users, ordered by id so paging is stable."""
    return db.scalars(select(User).order_by(User.id).offset(offset).limit(limit)).all()


@router.get(
    "/{user_id}",
    response_model=UserRead,
    summary="Retrieve a user",
    responses={404: {"description": "User not found."}},
)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    """Retrieve a single user by id."""
    return get_user_or_404(db, user_id)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user",
    responses={404: {"description": "User not found."}},
)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    """Delete a user and, by database cascade, every project they own."""
    user = get_user_or_404(db, user_id)

    # Projects are removed by the ON DELETE CASCADE on projects.owner_id.
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{user_id}/projects",
    response_model=list[ProjectRead],
    summary="List a user's projects",
    responses={404: {"description": "User not found."}},
)
def list_user_projects(user_id: int, db: Session = Depends(get_db)) -> Sequence[Project]:
    """Return every project owned by the user.

    The user is looked up first so that a missing user returns 404 rather than
    an empty list, which would be indistinguishable from a user with no
    projects.
    """
    get_user_or_404(db, user_id)

    return db.scalars(
        select(Project).where(Project.owner_id == user_id).order_by(Project.id)
    ).all()
