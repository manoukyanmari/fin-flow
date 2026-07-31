from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import User


def get_user_or_404(db: Session, user_id: int) -> User:
    """Return the user or raise 404.

    Shared by both routers, which is why it lives here rather than in either
    one of them.
    """
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user
