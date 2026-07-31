from collections.abc import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.schemas import ProjectRead, UserCreate, UserRead

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
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


@router.get("", response_model=list[UserRead])
def list_users(
    db: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Sequence[User]:
    return db.scalars(select(User).order_by(User.id).offset(offset).limit(limit)).all()


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, db: Session = Depends(get_db)) -> User:
    return get_user_or_404(db, user_id)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> Response:
    user = get_user_or_404(db, user_id)

    # Projects are removed by the ON DELETE CASCADE on projects.owner_id.
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{user_id}/projects", response_model=list[ProjectRead])
def list_user_projects(user_id: int, db: Session = Depends(get_db)) -> Sequence[Project]:
    # Checked explicitly so a missing user returns 404 instead of an empty
    # list, which would be indistinguishable from a user with no projects.
    get_user_or_404(db, user_id)

    return db.scalars(
        select(Project).where(Project.owner_id == user_id).order_by(Project.id)
    ).all()
