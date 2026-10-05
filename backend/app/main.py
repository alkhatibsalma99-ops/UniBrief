import os
import shutil
import uuid

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy import text
from sqlalchemy.orm import Session

from pypdf import PdfReader

from app import models, schemas
from app.database import Base, SessionLocal, engine
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.ai_service import (
    extract_requirements_with_ai,
    check_submission_with_ai,
)


# ==================================================
# DATABASE
# ==================================================

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==================================================
# FASTAPI
# ==================================================

app = FastAPI(
    title="UniBrief API",
    version="1.0.0",
)


# ==================================================
# CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5000",
        "http://localhost:8000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# AUTHENTICATION
# ==================================================

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    token = credentials.credentials

    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id = payload.get("sub")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


# ==================================================
# HEALTH
# ==================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
    }


@app.get("/db-check")
def db_check(
    db: Session = Depends(get_db),
):
    db.execute(text("SELECT 1"))

    return {
        "database": "connected",
    }


# ==================================================
# REGISTER
# ==================================================

@app.post("/register")
def register(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    existing_user = (
        db.query(models.User)
        .filter(models.User.email == user.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    new_user = models.User(
        name=user.name,
        email=user.email,
        password_hash=hash_password(user.password),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "id": new_user.id,
        "name": new_user.name,
        "email": new_user.email,
    }


# ==================================================
# LOGIN
# ==================================================

@app.post("/login")
def login(
    user: schemas.UserLogin,
    db: Session = Depends(get_db),
):
    db_user = (
        db.query(models.User)
        .filter(models.User.email == user.email)
        .first()
    )

    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(
        user.password,
        db_user.password_hash,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(
        {
            "sub": str(db_user.id),
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ==================================================
# CURRENT USER
# ==================================================

@app.get("/me")
def get_me(
    current_user: models.User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
    }


# ==================================================
# CREATE PROJECT
# ==================================================

@app.post("/projects")
def create_project(
    project: schemas.ProjectCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    new_project = models.Project(
        title=project.title,
        description=project.description,
        user_id=current_user.id,
    )

    db.add(new_project)
    db.commit()
    db.refresh(new_project)

    return {
        "id": new_project.id,
        "title": new_project.title,
        "description": new_project.description,
        "user_id": new_project.user_id,
    }


# ==================================================
# GET PROJECTS
# ==================================================

@app.get("/projects")
def get_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    projects = (
        db.query(models.Project)
        .filter(
            models.Project.user_id == current_user.id
        )
        .all()
    )

    return projects


# ==================================================
# UPDATE PROJECT
# ==================================================

@app.patch("/projects/{project_id}")
def update_project(
    project_id: int,
    update: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if update.title is not None:
        project.title = update.title

    if update.description is not None:
        project.description = update.description

    db.commit()
    db.refresh(project)

    return {
        "id": project.id,
        "title": project.title,
        "description": project.description,
        "user_id": project.user_id,
    }


# ==================================================
# DELETE PROJECT
# ==================================================

@app.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db.delete(project)
    db.commit()

    return {
        "message": "Project deleted",
    }


# ==================================================
# UPLOAD FILE
# ==================================================

@app.post("/projects/{project_id}/files")
def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    upload_directory = "uploads"

    os.makedirs(
        upload_directory,
        exist_ok=True,
    )

    original_filename = file.filename or "file"

    unique_filename = (
        f"{uuid.uuid4()}_{original_filename}"
    )

    file_path = os.path.join(
        upload_directory,
        unique_filename,
    )

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(
                file.file,
                buffer,
            )

    except Exception as e:
        print("UPLOAD ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save file",
        )

    db_file = models.ProjectFile(
        project_id=project_id,
        filename=original_filename,
        file_path=file_path,
    )

    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return {
        "id": db_file.id,
        "project_id": db_file.project_id,
        "filename": db_file.filename,
        "file_path": db_file.file_path,
        "uploaded_at": db_file.uploaded_at,
    }


# ==================================================
# GET PROJECT FILES
# ==================================================

@app.get("/projects/{project_id}/files")
def get_project_files(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    files = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.project_id == project_id
        )
        .all()
    )

    return files


# ==================================================
# EXTRACT PDF TEXT
# ==================================================

@app.get(
    "/projects/{project_id}/files/{file_id}/text"
)
def get_file_text(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id == project_id,
        )
        .first()
    )

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if not os.path.exists(db_file.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File does not exist on disk",
        )

    if not db_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for now",
        )

    try:
        reader = PdfReader(db_file.file_path)

        pages_text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages_text.append(page_text)

        extracted_text = "\n".join(pages_text)

    except Exception as e:
        print("PDF ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not read PDF",
        )

    return {
        "file_id": file_id,
        "filename": db_file.filename,
        "text": extracted_text,
    }


# ==================================================
# SIMPLE REQUIREMENTS EXTRACTION
# ==================================================

@app.get(
    "/projects/{project_id}/files/{file_id}/requirements"
)
def extract_requirements(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id == project_id,
        )
        .first()
    )

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if not os.path.exists(db_file.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File does not exist on disk",
        )

    if not db_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for now",
        )

    try:
        reader = PdfReader(db_file.file_path)

        pages_text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages_text.append(page_text)

        extracted_text = "\n".join(pages_text)

    except Exception as e:
        print("PDF ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not read PDF",
        )

    keywords = [
        "must",
        "should",
        "required",
        "requirement",
        "implement",
        "create",
        "develop",
        "use",
        "submit",
        "muss",
        "soll",
        "erstellen",
        "implementieren",
    ]

    requirements = []

    for line in extracted_text.splitlines():
        cleaned_line = line.strip()

        if not cleaned_line:
            continue

        lower_line = cleaned_line.lower()

        if any(
            keyword in lower_line
            for keyword in keywords
        ):
            requirements.append(cleaned_line)

    return {
        "file_id": file_id,
        "requirements": requirements,
    }


# ==================================================
# AI ANALYZE FILE
# ==================================================

@app.post(
    "/projects/{project_id}/files/{file_id}/analyze"
)
def analyze_file_with_ai(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id == project_id,
        )
        .first()
    )

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    if not os.path.exists(db_file.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File does not exist on disk",
        )

    if not db_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for now",
        )

    try:
        reader = PdfReader(db_file.file_path)

        pages_text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages_text.append(page_text)

        extracted_text = "\n".join(pages_text)

    except Exception as e:
        print("PDF ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not read PDF",
        )

    if not extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from PDF",
        )

    try:
        ai_result = extract_requirements_with_ai(
            extracted_text
        )

    except Exception as e:
        print("AI ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI analysis failed",
        )

    saved_requirements = []

    for item in ai_result["requirements"]:
        db_requirement = models.Requirement(
            project_id=project_id,
            file_id=file_id,
            title=item["title"],
            description=item["description"],
            priority=item["priority"],
        )

        db.add(db_requirement)
        db.commit()
        db.refresh(db_requirement)

        saved_requirements.append(
            {
                "id": db_requirement.id,
                "project_id": db_requirement.project_id,
                "file_id": db_requirement.file_id,
                "title": db_requirement.title,
                "description": db_requirement.description,
                "priority": db_requirement.priority,
            }
        )

    return {
        "project_id": project_id,
        "file_id": file_id,
        "requirements": saved_requirements,
    }


# ==================================================
# GET SAVED REQUIREMENTS
# ==================================================

@app.get("/projects/{project_id}/requirements")
def get_project_requirements(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    requirements = (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id
        )
        .all()
    )

    return [
        {
            "id": requirement.id,
            "project_id": requirement.project_id,
            "file_id": requirement.file_id,
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
        }
        for requirement in requirements
    ]


# ==================================================
# GENERATE CHECKLIST
# ==================================================

@app.post(
    "/projects/{project_id}/checklist/generate"
)
def generate_checklist(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    requirements = (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id
        )
        .all()
    )

    if not requirements:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No requirements found",
        )

    checklist = []

    for requirement in requirements:
        existing_item = (
            db.query(models.ChecklistItem)
            .filter(
                models.ChecklistItem.requirement_id
                == requirement.id
            )
            .first()
        )

        if existing_item:
            checklist.append(
                {
                    "id": existing_item.id,
                    "project_id": existing_item.project_id,
                    "requirement_id":
                        existing_item.requirement_id,
                    "title": existing_item.title,
                    "completed":
                        bool(existing_item.completed),
                }
            )

            continue

        item = models.ChecklistItem(
            project_id=project_id,
            requirement_id=requirement.id,
            title=requirement.title,
            completed=0,
        )

        db.add(item)
        db.commit()
        db.refresh(item)

        checklist.append(
            {
                "id": item.id,
                "project_id": item.project_id,
                "requirement_id": item.requirement_id,
                "title": item.title,
                "completed": bool(item.completed),
            }
        )

    return checklist


# ==================================================
# GET CHECKLIST
# ==================================================

@app.get("/projects/{project_id}/checklist")
def get_checklist(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    items = (
        db.query(models.ChecklistItem)
        .filter(
            models.ChecklistItem.project_id == project_id
        )
        .all()
    )

    return [
        {
            "id": item.id,
            "project_id": item.project_id,
            "requirement_id": item.requirement_id,
            "title": item.title,
            "completed": bool(item.completed),
        }
        for item in items
    ]


# ==================================================
# UPDATE CHECKLIST
# ==================================================

@app.patch("/checklist/{item_id}")
def update_checklist_item(
    item_id: int,
    update: schemas.ChecklistUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = (
        db.query(models.ChecklistItem)
        .join(
            models.Project,
            models.Project.id
            == models.ChecklistItem.project_id,
        )
        .filter(
            models.ChecklistItem.id == item_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist item not found",
        )

    item.completed = (
        1 if update.completed else 0
    )

    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "project_id": item.project_id,
        "requirement_id": item.requirement_id,
        "title": item.title,
        "completed": bool(item.completed),
    }


# ==================================================
# SUBMISSION CHECK
# ==================================================

@app.post(
    "/projects/{project_id}/submission/{file_id}/check",
)
def check_submission(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id == project_id,
        )
        .first()
    )

    if db_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission file not found",
        )

    if not os.path.exists(db_file.file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission file does not exist on disk",
        )

    if not db_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for now",
        )

    try:
        reader = PdfReader(db_file.file_path)

        pages_text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages_text.append(page_text)

        submission_text = "\n".join(pages_text)

    except Exception as e:
        print("PDF READ ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not read submission PDF",
        )

    if not submission_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No text could be extracted from submission PDF",
        )

    requirements_db = (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id
        )
        .all()
    )

    if not requirements_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No requirements found",
        )

    requirements = [
        {
            "id": requirement.id,
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
        }
        for requirement in requirements_db
    ]

    try:
        result = check_submission_with_ai(
            submission_text,
            requirements,
        )

    except Exception as e:
        print("SUBMISSION CHECK ERROR:", e)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Submission check failed",
        )

    # Remove previous results for this exact submission.
    db.query(models.SubmissionResult).filter(
        models.SubmissionResult.project_id
        == project_id,
        models.SubmissionResult.file_id
        == file_id,
    ).delete(
        synchronize_session=False
    )

    db.commit()

    saved_results = []

    for item in result["results"]:
        db_result = models.SubmissionResult(
            project_id=project_id,
            file_id=file_id,
            requirement_id=item["requirement_id"],
            status=item["status"],
            feedback=item["feedback"],
        )

        db.add(db_result)
        db.commit()
        db.refresh(db_result)

        saved_results.append(
            {
                "id": db_result.id,
                "requirement_id":
                    db_result.requirement_id,
                "status": db_result.status,
                "feedback": db_result.feedback,
            }
        )

    return {
        "project_id": project_id,
        "file_id": file_id,
        "results": saved_results,
    }


# ==================================================
# GET SUBMISSION RESULTS
# ==================================================

@app.get(
    "/projects/{project_id}/submission-results"
)
def get_submission_results(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    results = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id
            == project_id
        )
        .all()
    )

    return [
        {
            "id": result.id,
            "project_id": result.project_id,
            "file_id": result.file_id,
            "requirement_id":
                result.requirement_id,
            "status": result.status,
            "feedback": result.feedback,
        }
        for result in results
    ]


# ==================================================
# FINAL REPORT FOR SPECIFIC SUBMISSION
# ==================================================

@app.get(
    "/projects/{project_id}/submission/{file_id}/report",
)
def get_submission_report(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = (
        db.query(models.Project)
        .filter(
            models.Project.id == project_id,
            models.Project.user_id == current_user.id,
        )
        .first()
    )

    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    submission_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id
            == project_id,
        )
        .first()
    )

    if submission_file is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Submission file not found",
        )

    results = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id
            == project_id,
            models.SubmissionResult.file_id
            == file_id,
        )
        .all()
    )

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No submission results found",
        )

    total = len(results)

    fulfilled = sum(
        1
        for result in results
        if result.status == "fulfilled"
    )

    missing = sum(
        1
        for result in results
        if result.status == "missing"
    )

    unclear = sum(
        1
        for result in results
        if result.status == "unclear"
    )

    completion_percentage = round(
        (fulfilled / total) * 100,
        2,
    )

    details = [
        {
            "requirement_id":
                result.requirement_id,
            "status": result.status,
            "feedback": result.feedback,
        }
        for result in results
    ]

    return {
        "project_id": project.id,
        "project_title": project.title,
        "file_id": file_id,
        "submission_filename":
            submission_file.filename,
        "summary": {
            "total_requirements": total,
            "fulfilled": fulfilled,
            "missing": missing,
            "unclear": unclear,
            "completion_percentage":
                completion_percentage,
        },
        "details": details,
    }