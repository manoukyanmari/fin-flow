from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_user_or_404
from app.models import Project
from app.schemas import ProjectCreate, ProjectRead

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    responses={404: {"description": "The specified owner does not exist."}},
)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    """Create a project owned by an existing user."""
    get_user_or_404(db, payload.owner_id)

    project = Project(
        name=payload.name,
        description=payload.description,
        owner_id=payload.owner_id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Retrieve a project",
    responses={404: {"description": "Project not found."}},
)
def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    """Retrieve a single project by id."""
    project = db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    return project
