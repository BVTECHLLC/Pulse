"""v0.24 PSA projects & Kanban board.

Staff (OWNER/TECH) manage projects and tasks; the owning client can VIEW their
own projects/board (read-only) — real client transparency. The board groups
tasks into the canonical columns and `move` is the drag-between-columns action."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...core.db import get_db
from ...core.deps import assert_client_access, current_user, is_staff, require_roles
from ...models import (
    Client, Project, ProjectStatus, ProjectTask, Role, TASK_COLUMNS, User,
)
from ...services import audit

router = APIRouter(prefix="/api", tags=["projects"])


def _ip(req: Request) -> str:
    return req.headers.get("cf-connecting-ip") or (req.client.host if req.client else "?")


def _proj_out(p: Project, tasks: list[ProjectTask]) -> dict:
    done = sum(1 for t in tasks if t.status == "done")
    total = len(tasks)
    return {
        "id": p.id, "client_id": p.client_id, "name": p.name, "description": p.description,
        "status": p.status.value, "budget_hours": p.budget_hours,
        "owner_user_id": p.owner_user_id,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "due_date": p.due_date.isoformat() if p.due_date else None,
        "task_count": total, "done_count": done,
        "progress": round(done / total * 100) if total else 0,
    }


def _task_out(t: ProjectTask) -> dict:
    return {
        "id": t.id, "project_id": t.project_id, "title": t.title, "description": t.description,
        "status": t.status, "assignee_user_id": t.assignee_user_id, "priority": t.priority,
        "estimate_hours": t.estimate_hours, "position": t.position,
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


def _get_project(db: Session, user: User, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    assert_client_access(user, p.client_id)
    return p


# --------------------------------------------------------------------------- #
# Projects
# --------------------------------------------------------------------------- #
class ProjectIn(BaseModel):
    client_id: int
    name: str
    description: str | None = None
    due_date: datetime | None = None
    budget_hours: float | None = None


@router.get("/projects")
def list_projects(client_id: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    q = db.query(Project)
    if is_staff(user):
        if client_id:
            q = q.filter(Project.client_id == client_id)
    else:
        q = q.filter(Project.client_id == user.client_id)
    projects = q.order_by(Project.created_at.desc()).all()
    # one task query for the rollups
    ids = [p.id for p in projects]
    tasks_by_proj: dict[int, list[ProjectTask]] = {i: [] for i in ids}
    if ids:
        for t in db.query(ProjectTask).filter(ProjectTask.project_id.in_(ids)).all():
            tasks_by_proj.setdefault(t.project_id, []).append(t)
    return [_proj_out(p, tasks_by_proj.get(p.id, [])) for p in projects]


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    if not db.get(Client, body.client_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    p = Project(client_id=body.client_id, name=body.name.strip(), description=body.description,
                due_date=body.due_date, budget_hours=body.budget_hours, owner_user_id=user.id)
    db.add(p)
    db.commit()
    audit.record(db, action="project.create", actor_user_id=user.id, actor_email=user.email,
                 actor_role=user.role.value, target_type="project", target_id=str(p.id),
                 client_id=p.client_id, ip=_ip(request), detail=f"name={p.name}")
    return _proj_out(p, [])


class ProjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    budget_hours: float | None = None


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectPatch, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    p = _get_project(db, user, project_id)
    if body.name is not None:
        p.name = body.name.strip()
    if body.description is not None:
        p.description = body.description
    if body.status is not None:
        try:
            p.status = ProjectStatus(body.status)
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid status")
    if body.due_date is not None:
        p.due_date = body.due_date
    if body.budget_hours is not None:
        p.budget_hours = body.budget_hours
    db.commit()
    tasks = db.query(ProjectTask).filter(ProjectTask.project_id == p.id).all()
    return _proj_out(p, tasks)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    p = _get_project(db, user, project_id)
    db.query(ProjectTask).filter(ProjectTask.project_id == p.id).delete()
    db.delete(p)
    db.commit()


@router.get("/projects/{project_id}/board")
def project_board(project_id: int, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    p = _get_project(db, user, project_id)
    tasks = (db.query(ProjectTask).filter(ProjectTask.project_id == p.id)
             .order_by(ProjectTask.position, ProjectTask.id).all())
    columns = {c: [] for c in TASK_COLUMNS}
    for t in tasks:
        columns.setdefault(t.status, []).append(_task_out(t))
    return {"project": _proj_out(p, tasks), "columns": TASK_COLUMNS, "tasks": columns}


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #
class TaskIn(BaseModel):
    title: str
    description: str | None = None
    status: str = "todo"
    assignee_user_id: int | None = None
    priority: str = "normal"
    due_date: datetime | None = None
    estimate_hours: float | None = None


@router.post("/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: int, body: TaskIn, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    p = _get_project(db, user, project_id)
    col = body.status if body.status in TASK_COLUMNS else "todo"
    last = (db.query(ProjectTask).filter(ProjectTask.project_id == p.id, ProjectTask.status == col)
            .order_by(ProjectTask.position.desc()).first())
    t = ProjectTask(
        project_id=p.id, client_id=p.client_id, title=body.title.strip(),
        description=body.description, status=col, assignee_user_id=body.assignee_user_id,
        priority=body.priority if body.priority in ("low", "normal", "high", "urgent") else "normal",
        due_date=body.due_date, estimate_hours=body.estimate_hours,
        position=((last.position + 1) if last else 0),
        completed_at=datetime.now(timezone.utc) if col == "done" else None,
    )
    db.add(t)
    db.commit()
    return _task_out(t)


class TaskPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    assignee_user_id: int | None = None
    priority: str | None = None
    due_date: datetime | None = None
    estimate_hours: float | None = None


def _get_task(db: Session, user: User, task_id: int) -> ProjectTask:
    t = db.get(ProjectTask, task_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Task not found")
    assert_client_access(user, t.client_id)
    return t


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskPatch, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = _get_task(db, user, task_id)
    if body.title is not None:
        t.title = body.title.strip()
    if body.description is not None:
        t.description = body.description
    if body.assignee_user_id is not None:
        t.assignee_user_id = body.assignee_user_id or None
    if body.priority is not None and body.priority in ("low", "normal", "high", "urgent"):
        t.priority = body.priority
    if body.due_date is not None:
        t.due_date = body.due_date
    if body.estimate_hours is not None:
        t.estimate_hours = body.estimate_hours
    db.commit()
    return _task_out(t)


class TaskMove(BaseModel):
    status: str
    position: int | None = None


@router.post("/tasks/{task_id}/move")
def move_task(task_id: int, body: TaskMove, db: Session = Depends(get_db),
              user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    """The Kanban drag action: change a task's column (and optionally its order).
    Moving into `done` stamps completed_at; moving out clears it."""
    t = _get_task(db, user, task_id)
    if body.status not in TASK_COLUMNS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"status must be one of {TASK_COLUMNS}")
    t.status = body.status
    if body.position is not None:
        t.position = max(0, body.position)
    t.completed_at = datetime.now(timezone.utc) if body.status == "done" else None
    db.commit()
    return _task_out(t)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db),
                user: User = Depends(require_roles(Role.OWNER, Role.TECH))):
    t = _get_task(db, user, task_id)
    db.delete(t)
    db.commit()
