
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
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
    create_refresh_token,
    hash_refresh_token,
    get_refresh_token_expiry,
    utc_now,
)
from app.ai_service import (
    extract_requirements_with_ai,
    check_submission_with_ai,
)
from app.translation_routes import router as translation_router
from app.r2_storage import (
    upload_file_to_r2,
    download_file_from_r2,
)


# ==========================================
# CONFIGURATION
# ==========================================

MAX_PDF_SIZE = 20 * 1024 * 1024


# ==========================================
# DATABASE
# ==========================================

Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==========================================
# FASTAPI
# ==========================================

app = FastAPI(
    title="UniBrief API",
    version="1.3.0",
)


# ==========================================
# CORS
# ==========================================

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


# ==========================================
# TRANSLATION
# ==========================================

app.include_router(translation_router)


# ==========================================
# AUTHENTICATION
# ==========================================

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    try:
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
        )

    user = (
        db.query(models.User)
        .filter(models.User.id == user_id)
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user


# ==========================================
# PROJECT OWNERSHIP
# ==========================================

def get_owned_project(
    project_id: int,
    db: Session,
    current_user: models.User,
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
            status_code=404,
            detail="Project not found",
        )

    return project


# ==========================================
# FILE OWNERSHIP
# ==========================================

def get_owned_project_file(
    project_id: int,
    file_id: int,
    db: Session,
    current_user: models.User,
):
    get_owned_project(project_id, db, current_user)

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
            status_code=404,
            detail="File not found",
        )

    return db_file


# ==========================================
# STORAGE HELPERS
# ==========================================

def get_file_bytes(db_file):
    """
    New files use Cloudflare R2.
    Older local files remain readable.
    """

    stored_path = db_file.file_path or ""

    if stored_path.startswith("r2://"):
        object_key = stored_path[len("r2://"):]

        if not object_key:
            raise HTTPException(
                status_code=500,
                detail="Invalid R2 object key",
            )

        try:
            return download_file_from_r2(object_key)
        except Exception as error:
            print(
                "R2 DOWNLOAD ERROR:",
                type(error).__name__,
            )
            raise HTTPException(
                status_code=502,
                detail="Could not retrieve file from storage",
            ) from error

    if not os.path.isfile(stored_path):
        raise HTTPException(
            status_code=404,
            detail="File does not exist in local storage",
        )

    try:
        with open(stored_path, "rb") as file:
            return file.read()
    except OSError as error:
        raise HTTPException(
            status_code=500,
            detail="Could not read local file",
        ) from error


def read_pdf_text(db_file):
    if not db_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    pdf_bytes = get_file_bytes(db_file)

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages_text = []

        for page in reader.pages:
            page_text = page.extract_text()

            if page_text:
                pages_text.append(page_text)

        return "\n".join(pages_text)

    except Exception as error:
        print("PDF ERROR:", type(error).__name__)

        raise HTTPException(
            status_code=422,
            detail="Could not extract text from PDF",
        ) from error


# ==========================================
# HEALTH
# ==========================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}


# ==========================================
# REGISTER
# ==========================================

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
            status_code=400,
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


# ==========================================
# REFRESH TOKEN REQUEST
# ==========================================

class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(
        min_length=1,
        max_length=512,
    )


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def issue_refresh_token(
    db: Session,
    user_id: int,
) -> str:
    token = create_refresh_token()

    db.add(
        models.RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(token),
            created_at=utc_now(),
            expires_at=get_refresh_token_expiry(),
            revoked=False,
        )
    )

    return token


# ==========================================
# LOGIN
# ==========================================

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

    if db_user is None or not verify_password(
        user.password,
        db_user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    access_token = create_access_token(
        {"sub": str(db_user.id)}
    )

    refresh_token = issue_refresh_token(
        db,
        db_user.id,
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ==========================================
# REFRESH TOKEN ROTATION
# ==========================================

@app.post("/refresh")
def refresh_session(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    old_hash = hash_refresh_token(
        request.refresh_token
    )

    stored_token = (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.token_hash == old_hash
        )
        .with_for_update()
        .first()
    )

    if (
        stored_token is None
        or stored_token.revoked
        or normalize_utc(stored_token.expires_at) <= utc_now()
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    user = (
        db.query(models.User)
        .filter(
            models.User.id == stored_token.user_id
        )
        .first()
    )

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    stored_token.revoked = True

    new_access_token = create_access_token(
        {"sub": str(user.id)}
    )

    new_refresh_token = issue_refresh_token(
        db,
        user.id,
    )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


# ==========================================
# LOGOUT
# ==========================================

@app.post("/logout")
def logout_session(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db),
):
    token_hash = hash_refresh_token(
        request.refresh_token
    )

    stored_token = (
        db.query(models.RefreshToken)
        .filter(
            models.RefreshToken.token_hash == token_hash
        )
        .with_for_update()
        .first()
    )

    if stored_token is not None:
        stored_token.revoked = True
        db.commit()

    return {
        "message": "Logged out successfully"
    }


# ==========================================
# CURRENT USER
# ==========================================

@app.get("/me")
def get_me(
    current_user: models.User = Depends(get_current_user),
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
    }


# ==========================================
# CREATE PROJECT
# ==========================================

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


# ==========================================
# GET PROJECTS
# ==========================================

@app.get("/projects")
def get_projects(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.Project)
        .filter(
            models.Project.user_id == current_user.id
        )
        .all()
    )


# ==========================================
# UPDATE PROJECT
# ==========================================

@app.patch("/projects/{project_id}")
def update_project(
    project_id: int,
    update: schemas.ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        db,
        current_user,
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


# ==========================================
# DELETE PROJECT
# ==========================================

@app.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        db,
        current_user,
    )

    db.delete(project)
    db.commit()

    return {"message": "Project deleted"}


# ==========================================
# UPLOAD PDF TO CLOUDFLARE R2
# ==========================================

@app.post("/projects/{project_id}/files")
def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        db,
        current_user,
    )

    original_filename = os.path.basename(
        (file.filename or "file").replace("\\", "/")
    )

    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    try:
        file_bytes = file.file.read(
            MAX_PDF_SIZE + 1
        )
    finally:
        file.file.close()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="File is empty",
        )

    if len(file_bytes) > MAX_PDF_SIZE:
        raise HTTPException(
            status_code=413,
            detail="PDF exceeds 20 MB limit",
        )

    if not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid PDF file",
        )

    object_key = (
        f"users/{current_user.id}/"
        f"projects/{project_id}/"
        f"{uuid.uuid4()}.pdf"
    )

    try:
        upload_file_to_r2(
            file_bytes=file_bytes,
            object_key=object_key,
        )
    except Exception as error:
        print(
            "R2 UPLOAD ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=502,
            detail="Could not upload file to storage",
        ) from error

    db_file = models.ProjectFile(
        project_id=project_id,
        filename=original_filename,
        file_path=f"r2://{object_key}",
    )

    try:
        db.add(db_file)
        db.commit()
        db.refresh(db_file)
    except Exception:
        db.rollback()
        raise

    return {
        "id": db_file.id,
        "project_id": db_file.project_id,
        "filename": db_file.filename,
        "file_path": db_file.file_path,
        "uploaded_at": db_file.uploaded_at,
    }


# ==========================================
# GET PROJECT FILES
# ==========================================

@app.get("/projects/{project_id}/files")
def get_project_files(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        db,
        current_user,
    )

    return (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.project_id == project_id
        )
        .all()
    )


# ==========================================
# EXTRACT PDF TEXT
# ==========================================

@app.get("/projects/{project_id}/files/{file_id}/text")
def get_file_text(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    extracted_text = read_pdf_text(db_file)

    return {
        "file_id": file_id,
        "filename": db_file.filename,
        "text": extracted_text,
    }


# ==========================================
# SIMPLE REQUIREMENTS EXTRACTION
# ==========================================

@app.get(
    "/projects/{project_id}/files/{file_id}/requirements"
)
def extract_requirements(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    extracted_text = read_pdf_text(db_file)

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


# ==========================================
# AI ANALYZE FILE
# ==========================================

@app.post(
    "/projects/{project_id}/files/{file_id}/analyze"
)
def analyze_file_with_ai(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    extracted_text = read_pdf_text(db_file)

    if not extracted_text.strip():
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from PDF",
        )

    try:
        ai_result = extract_requirements_with_ai(
            extracted_text
        )
    except Exception as error:
        print(
            "AI ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="AI analysis failed",
        ) from error

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
        db.flush()

        saved_requirements.append({
            "id": db_requirement.id,
            "project_id": db_requirement.project_id,
            "file_id": db_requirement.file_id,
            "title": db_requirement.title,
            "description": db_requirement.description,
            "priority": db_requirement.priority,
        })

    db.commit()

    return {
        "project_id": project_id,
        "file_id": file_id,
        "requirements": saved_requirements,
    }


# ==========================================
# GET SAVED REQUIREMENTS
# ==========================================

@app.get("/projects/{project_id}/requirements")
def get_project_requirements(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        db,
        current_user,
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


# ==========================================
# GENERATE CHECKLIST
# ==========================================

@app.post(
    "/projects/{project_id}/checklist/generate"
)
def generate_checklist(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        db,
        current_user,
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
            status_code=404,
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
            checklist.append({
                "id": existing_item.id,
                "project_id": existing_item.project_id,
                "requirement_id": existing_item.requirement_id,
                "title": existing_item.title,
                "completed": bool(existing_item.completed),
            })
            continue

        item = models.ChecklistItem(
            project_id=project_id,
            requirement_id=requirement.id,
            title=requirement.title,
            completed=0,
        )

        db.add(item)
        db.flush()

        checklist.append({
            "id": item.id,
            "project_id": item.project_id,
            "requirement_id": item.requirement_id,
            "title": item.title,
            "completed": bool(item.completed),
        })

    db.commit()

    return checklist


# ==========================================
# GET CHECKLIST
# ==========================================

@app.get("/projects/{project_id}/checklist")
def get_checklist(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        db,
        current_user,
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


# ==========================================
# UPDATE CHECKLIST
# ==========================================

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
            status_code=404,
            detail="Checklist item not found",
        )

    item.completed = 1 if update.completed else 0

    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "project_id": item.project_id,
        "requirement_id": item.requirement_id,
        "title": item.title,
        "completed": bool(item.completed),
    }


# ==========================================
# SUBMISSION CHECK
# ==========================================

@app.post(
    "/projects/{project_id}/submission/{file_id}/check"
)
def check_submission(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    submission_text = read_pdf_text(db_file)

    if not submission_text.strip():
        raise HTTPException(
            status_code=400,
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
            status_code=404,
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
    except Exception as error:
        print(
            "SUBMISSION CHECK ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="Submission check failed",
        ) from error

    db.query(models.SubmissionResult).filter(
        models.SubmissionResult.project_id == project_id,
        models.SubmissionResult.file_id == file_id,
    ).delete(synchronize_session=False)

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
        db.flush()

        saved_results.append({
            "id": db_result.id,
            "requirement_id": db_result.requirement_id,
            "status": db_result.status,
            "feedback": db_result.feedback,
        })

    db.commit()

    return {
        "project_id": project_id,
        "file_id": file_id,
        "results": saved_results,
    }


# ==========================================
# GET SUBMISSION RESULTS
# ==========================================

@app.get(
    "/projects/{project_id}/submission-results"
)
def get_submission_results(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_project(
        project_id,
        db,
        current_user,
    )

    results = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id == project_id
        )
        .all()
    )

    return [
        {
            "id": result.id,
            "project_id": result.project_id,
            "file_id": result.file_id,
            "requirement_id": result.requirement_id,
            "status": result.status,
            "feedback": result.feedback,
        }
        for result in results
    ]


# ==========================================
# FINAL SUBMISSION REPORT
# ==========================================

@app.get(
    "/projects/{project_id}/submission/{file_id}/report"
)
def get_submission_report(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    project = get_owned_project(
        project_id,
        db,
        current_user,
    )

    submission_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    results = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id == project_id,
            models.SubmissionResult.file_id == file_id,
        )
        .all()
    )

    if not results:
        raise HTTPException(
            status_code=404,
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
            "requirement_id": result.requirement_id,
            "status": result.status,
            "feedback": result.feedback,
        }
        for result in results
    ]

    return {
        "project_id": project.id,
        "project_title": project.title,
        "file_id": file_id,
        "submission_filename": submission_file.filename,
        "summary": {
            "total_requirements": total,
            "fulfilled": fulfilled,
            "missing": missing,
            "unclear": unclear,
            "completion_percentage": completion_percentage,
        },
        "details": details,
    }
