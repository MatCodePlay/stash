import logging
import hashlib
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("stash.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///stash.db"
Base = declarative_base()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String)
    password = Column(String)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    content = Column(String)
    is_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Journal(Base):
    __tablename__ = "journal"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    description = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def init_db():
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "fromostrzeszow@gmail.com").first()
        if not admin:
            admin = User(
                email="fromostrzeszow@gmail.com",
                full_name="Admin",
                password=hash_password("admin123"),
            )
            db.add(admin)
            db.commit()
            db.refresh(admin)
            logger.info("Admin user created: fromostrzeszow@gmail.com")
            log_activity(admin.id, "Admin user created")
        else:
            logger.info("Admin user already exists")
    finally:
        db.close()


def log_activity(user_id: int, description: str):
    db = SessionLocal()
    try:
        log = ActivityLog(user_id=user_id, description=description)
        db.add(log)
        db.commit()
    finally:
        db.close()


app = FastAPI(title="STASH")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))

ADMIN_ID = 1


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request) -> int | None:
    user_id = request.session.get("user_id")
    return user_id


def login_required(request: Request):
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)
    return user_id
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str | None = None):
    logger.info("Login page accessed")
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": error}
    )


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, email: str = Form(...), password: str = Form(...)):
    logger.info(f"Login attempt: {email}")
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    db.close()

    if user is not None and user.password == hash_password(password):
        request.session["user_id"] = user.id
        request.session["email"] = user.email
        logger.info(f"Login successful: {email}")
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid email or password"}
    )


@app.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    request.session.clear()
    logger.info("User logged out")
    return RedirectResponse(url="/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    logger.info("Home page accessed")
    db = SessionLocal()
    tasks_count = db.query(Task).filter(Task.user_id == ADMIN_ID).count()
    completed_count = (
        db.query(Task).filter(Task.user_id == ADMIN_ID, Task.is_done == True).count()
    )
    journal_count = db.query(Journal).filter(Journal.user_id == ADMIN_ID).count()
    recent_logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == ADMIN_ID)
        .order_by(ActivityLog.created_at.desc())
        .limit(5)
        .all()
    )
    db.close()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks_count": tasks_count,
            "completed_count": completed_count,
            "journal_count": journal_count,
            "recent_logs": recent_logs,
        },
        status_code=200,
    )


@app.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, page: int = Query(1, ge=1)):
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    logger.info("Tasks page accessed")
    db = SessionLocal()
    per_page = 8
    offset = (page - 1) * per_page
    total = db.query(Task).filter(Task.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    active = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == False)
        .order_by(Task.created_at.desc())
        .all()
    )
    completed = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == True)
        .order_by(Task.completed_at.desc())
        .all()
    )
    all_tasks = active + completed
    tasks = all_tasks[offset : offset + per_page]
    db.close()
    return templates.TemplateResponse(
        "tasks.html",
        {
            "request": request,
            "tasks": tasks,
            "page": page,
            "total_pages": total_pages,
            "per_page": per_page,
        },
    )


def is_htmx(request: Request) -> bool:
    return request.headers.get("hx-request") == "true"


@app.post("/tasks", response_class=HTMLResponse)
async def add_task(
    request: Request, content: str = Form(...), page: int = Query(1, ge=1)
):
    logger.info(f"Task added: {content[:50]}")
    db = SessionLocal()
    task = Task(user_id=ADMIN_ID, content=content)
    db.add(task)
    db.commit()
    db.refresh(task)
    log_activity(ADMIN_ID, f"Added task: {content[:30]}")
    per_page = 8
    offset = (page - 1) * per_page
    total = db.query(Task).filter(Task.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    active = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == False)
        .order_by(Task.created_at.desc())
        .all()
    )
    completed = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == True)
        .order_by(Task.completed_at.desc())
        .all()
    )
    all_tasks = active + completed
    tasks = all_tasks[offset : offset + per_page]
    db.close()
    if is_htmx(request):
        return templates.TemplateResponse(
            "_tasks_list.html",
            {
                "request": request,
                "tasks": tasks,
                "page": page,
                "total_pages": total_pages,
            },
        )
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": tasks, "page": page, "total_pages": total_pages},
    )


@app.put("/tasks/{task_id}", response_class=HTMLResponse)
async def toggle_task(task_id: int, request: Request, page: int = Query(1, ge=1)):
    logger.info(f"Task toggled: {task_id}")
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        task.is_done = not task.is_done
        task.completed_at = datetime.utcnow() if task.is_done else None
        db.commit()
        log_activity(ADMIN_ID, f"Toggled task: {task.content[:30]}")
    per_page = 8
    offset = (page - 1) * per_page
    total = db.query(Task).filter(Task.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    active = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == False)
        .order_by(Task.created_at.desc())
        .all()
    )
    completed = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == True)
        .order_by(Task.completed_at.desc())
        .all()
    )
    all_tasks = active + completed
    tasks = all_tasks[offset : offset + per_page]
    db.close()
    if is_htmx(request):
        return templates.TemplateResponse(
            "_tasks_list.html",
            {
                "request": request,
                "tasks": tasks,
                "page": page,
                "total_pages": total_pages,
            },
        )
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": tasks, "page": page, "total_pages": total_pages},
    )


@app.delete("/tasks/{task_id}", response_class=HTMLResponse)
async def delete_task(task_id: int, request: Request, page: int = Query(1, ge=1)):
    logger.info(f"Task deleted: {task_id}")
    db = SessionLocal()
    task = db.query(Task).filter(Task.id == task_id).first()
    if task:
        content = task.content
        db.delete(task)
        db.commit()
        log_activity(ADMIN_ID, f"Deleted task: {content[:30]}")
    per_page = 8
    offset = (page - 1) * per_page
    total = db.query(Task).filter(Task.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    active = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == False)
        .order_by(Task.created_at.desc())
        .all()
    )
    completed = (
        db.query(Task)
        .filter(Task.user_id == ADMIN_ID, Task.is_done == True)
        .order_by(Task.completed_at.desc())
        .all()
    )
    all_tasks = active + completed
    tasks = all_tasks[offset : offset + per_page]
    db.close()
    if is_htmx(request):
        return templates.TemplateResponse(
            "_tasks_list.html",
            {
                "request": request,
                "tasks": tasks,
                "page": page,
                "total_pages": total_pages,
            },
        )
    return templates.TemplateResponse(
        "tasks.html",
        {"request": request, "tasks": tasks, "page": page, "total_pages": total_pages},
    )


@app.get("/journal", response_class=HTMLResponse)
async def journal_page(request: Request, page: int = Query(1, ge=1)):
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    logger.info("Journal page accessed")
    db = SessionLocal()
    per_page = 10
    offset = (page - 1) * per_page
    total = db.query(Journal).filter(Journal.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    entries = (
        db.query(Journal)
        .filter(Journal.user_id == ADMIN_ID)
        .order_by(Journal.created_at.desc())
        .limit(per_page)
        .offset(offset)
        .all()
    )
    db.close()
    return templates.TemplateResponse(
        "journal.html",
        {
            "request": request,
            "entries": entries,
            "page": page,
            "total_pages": total_pages,
        },
    )


@app.post("/journal", response_class=HTMLResponse)
async def add_journal(
    request: Request, content: str = Form(...), page: int = Query(1, ge=1)
):
    logger.info(f"Journal entry added")
    db = SessionLocal()
    entry = Journal(user_id=ADMIN_ID, content=content)
    db.add(entry)
    db.commit()
    log_activity(ADMIN_ID, "Added journal entry")
    per_page = 10
    offset = (page - 1) * per_page
    total = db.query(Journal).filter(Journal.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    entries = (
        db.query(Journal)
        .filter(Journal.user_id == ADMIN_ID)
        .order_by(Journal.created_at.desc())
        .limit(per_page)
        .offset(offset)
        .all()
    )
    db.close()
    if is_htmx(request):
        return templates.TemplateResponse(
            "_journal_list.html",
            {
                "request": request,
                "entries": entries,
                "page": page,
                "total_pages": total_pages,
            },
        )
    return templates.TemplateResponse(
        "journal.html",
        {
            "request": request,
            "entries": entries,
            "page": page,
            "total_pages": total_pages,
        },
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, page: int = Query(1, ge=1)):
    user_id = get_current_user(request)
    if not user_id:
        return RedirectResponse(url="/login", status_code=302)

    logger.info("Logs page accessed")
    db = SessionLocal()
    per_page = 10
    offset = (page - 1) * per_page
    total = db.query(ActivityLog).filter(ActivityLog.user_id == ADMIN_ID).count()
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1
    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.user_id == ADMIN_ID)
        .order_by(ActivityLog.created_at.desc())
        .limit(per_page)
        .offset(offset)
        .all()
    )
    db.close()
    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "logs": logs, "page": page, "total_pages": total_pages},
    )


if __name__ == "__main__":
    import uvicorn

    init_db()
    logger.info("Starting STASH application")
    uvicorn.run(app, host="0.0.0.0", port=8000)
