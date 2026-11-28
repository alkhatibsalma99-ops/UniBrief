
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Annotated

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
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
from app.translation_routes import (
    router as translation_router,
    delete_user_translation_cache,
    delete_project_translation_cache,
)
from app.r2_storage import (
    upload_file_to_r2,
    download_file_from_r2,
    delete_file_from_r2,
)
from fastapi import Request

from app.login_rate_limit import (
    initialize_login_rate_limit,
    check_login_limit,
    record_failed_login,
    clear_login_attempts,
)
from app.ai_rate_limit import (
    initialize_ai_rate_limit,
    ai_request_slot,
    delete_user_ai_data,
)
from app.ai_service import extract_requirements_with_evidence

from app.requirement_pipeline import process_requirements



# ==================================================
# CONFIGURATION
# ==================================================

MAX_PDF_SIZE = 20 * 1024 * 1024

DEFAULT_CORS_ORIGINS = [
    "https://late-king-42e3.alkhatibsalma99.workers.dev",
]

ADDITIONAL_CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", ""
    ).split(",")
    if origin.strip() and origin.strip() != "*"
]


# ==================================================
# DATABASE
# ==================================================

Base.metadata.create_all(bind=engine)
initialize_login_rate_limit(engine)
initialize_ai_rate_limit(engine)


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
    version="1.3.1",
)

app.include_router(translation_router)

security = HTTPBearer()


# ==================================================
# AUTHENTICATION HELPERS
# ==================================================

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
):
    payload = decode_access_token(
        credentials.credentials
    )

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


# ==================================================
# PROJECT OWNERSHIP
# ==================================================

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


# ==================================================
# FILE OWNERSHIP
# ==================================================

def get_owned_project_file(
    project_id: int,
    file_id: int,
    db: Session,
    current_user: models.User,
):
    get_owned_project(
        project_id,
        db,
        current_user,
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
            status_code=404,
            detail="File not found",
        )

    return db_file




# ==================================================
# FILE ROLE VALIDATION
# ==================================================

def ensure_file_role(
    db_file: models.ProjectFile,
    expected_role: schemas.FileRole,
):
    allowed_roles = {
        expected_role.value,
        schemas.FileRole.UNCLASSIFIED.value,
    }

    if db_file.file_role not in allowed_roles:
        raise HTTPException(
            status_code=400,
            detail=(
                f"This operation requires a "
                f"{expected_role.value} PDF."
            ),
        )


def lock_owned_project_file(
    project_id: int,
    file_id: int,
    db: Session,
    current_user: models.User,
):
    get_owned_project(
        project_id,
        db,
        current_user,
    )

    db_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id == project_id,
        )
        .populate_existing()
        .with_for_update()
        .first()
    )

    if db_file is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    return db_file


# ==================================================
# FILE STORAGE
# ==================================================

def get_file_bytes(db_file):
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


# ==================================================
# PDF TEXT EXTRACTION
# ==================================================

def read_pdf_pages(db_file) -> list[dict]:

    if not db_file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported",
        )

    pdf_bytes = get_file_bytes(db_file)

    try:
        reader = PdfReader(BytesIO(pdf_bytes))

        pages = []

        for page_number, page in enumerate(
            reader.pages,
            start=1,
        ):
            page_text = page.extract_text() or ""

            pages.append(
                {
                    "page_number": page_number,
                    "text": page_text,
                }
            )

        return pages

    except Exception as error:
        print(
            "PDF ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=422,
            detail="Could not extract text from PDF",
        ) from error


# ==================================================
# BACKWARD COMPATIBLE PDF TEXT EXTRACTION
# ==================================================

def read_pdf_text(db_file) -> str:

    pages = read_pdf_pages(db_file)

    return "\n".join(
        page["text"]
        for page in pages
        if page["text"]
    )
# ==================================================
# HEALTH CHECK
# ==================================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "connected"}


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


# ==================================================
# REFRESH TOKEN HELPERS
# ==================================================

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


# ==================================================
# LOGIN
# ==================================================


@app.post("/login")
def login(
    user: schemas.UserLogin,
    request: Request,
    db: Session = Depends(get_db),
):
    rate_key = check_login_limit(
        db,
        request,
        user.email,
    )

    try:
        db_user = (
            db.query(models.User)
            .filter(
                models.User.email == user.email
            )
            .first()
        )

        valid_password = (
            db_user is not None
            and verify_password(
                user.password,
                db_user.password_hash,
            )
        )

        if not valid_password:
            record_failed_login(db, rate_key)

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

        clear_login_attempts(db, rate_key)

        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


# ==================================================
# REFRESH ACCESS TOKEN
# ==================================================

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


# ==================================================
# LOGOUT
# ==================================================

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
# DELETE PROJECT PDF
# ==================================================

@app.delete("/projects/{project_id}/files/{file_id}")
def delete_project_pdf(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Check project and file ownership.
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    stored_path = db_file.file_path or ""

    # Validate the storage path before deletion.
    if stored_path.startswith("r2://"):
        object_key = stored_path[len("r2://"):]

        expected_prefix = (
            f"users/{current_user.id}/"
            f"projects/{project_id}/"
        )

        if (
            not object_key
            or not object_key.startswith(expected_prefix)
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid R2 file path",
            )

    else:
        # Do not delete local files automatically.
        # Local paths require separate safe-path validation.
        raise HTTPException(
            status_code=400,
            detail="Only R2 files can be deleted",
        )

    # Lock the file row while preparing deletion.
    db_file = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.id == file_id,
            models.ProjectFile.project_id == project_id,
        )
        .with_for_update()
        .first()
    )

    if db_file is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    try:
        # Find requirements belonging to this PDF.
        requirement_ids = [
            requirement_id
            for (requirement_id,) in (
                db.query(models.Requirement.id)
                .filter(
                    models.Requirement.project_id == project_id,
                    models.Requirement.file_id == file_id,
                )
                .all()
            )
        ]

        # Delete submission results directly linked
        # to the file or its requirements.
        result_filter = (
            models.SubmissionResult.file_id == file_id
        )

        if requirement_ids:
            from sqlalchemy import or_

            result_filter = or_(
                models.SubmissionResult.file_id == file_id,
                models.SubmissionResult.requirement_id.in_(
                    requirement_ids
                ),
            )

        db.query(models.SubmissionResult).filter(
            models.SubmissionResult.project_id == project_id,
            result_filter,
        ).delete(synchronize_session=False)

        # Remove checklist items for this PDF's requirements.
        if requirement_ids:
            db.query(models.ChecklistItem).filter(
                models.ChecklistItem.project_id == project_id,
                models.ChecklistItem.requirement_id.in_(
                    requirement_ids
                ),
            ).delete(synchronize_session=False)

        # Remove requirements extracted from this PDF.
        db.query(models.Requirement).filter(
            models.Requirement.project_id == project_id,
            models.Requirement.file_id == file_id,
        ).delete(synchronize_session=False)

        # Delete the file's database record.
        db.delete(db_file)

        # Flush first to detect database constraint errors.
        db.flush()

        # Delete the actual object from R2.
        # If R2 fails, the database transaction rolls back.
        delete_file_from_r2(object_key)

        db.commit()

    except Exception as error:
        db.rollback()

        print(
            "PDF DELETE ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Could not complete PDF deletion. "
                "Please check the server logs."
            ),
        ) from error

    return {
        "message": "PDF deleted successfully",
        "file_id": file_id,
        "project_id": project_id,
    }



# ==================================================
# GET PROJECTS
# ==================================================

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



# ==================================================
# DELETE PROJECT + CLOUDFLARE R2 CLEANUP
# ==================================================

@app.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # 1. Verify project ownership.
    project = get_owned_project(
        project_id,
        db,
        current_user,
    )

    # 2. Retrieve all files belonging to this project.
    project_files = (
        db.query(models.ProjectFile)
        .filter(
            models.ProjectFile.project_id == project_id
        )
        .all()
    )

    # 3. Validate all storage paths before deleting.
    storage_objects = []

    uploads_directory = os.path.realpath(
        os.path.join(os.getcwd(), "uploads")
    )

    for project_file in project_files:
        stored_path = project_file.file_path or ""

        if stored_path.startswith("r2://"):
            object_key = stored_path[len("r2://"):]

            if not object_key:
                raise HTTPException(
                    status_code=500,
                    detail="Invalid R2 object key",
                )

            storage_objects.append(
                ("r2", object_key)
            )

        elif stored_path:
            target_path = os.path.realpath(
                stored_path
            )

            # Prevent deleting arbitrary local files.
            try:
                is_safe = (
                    os.path.commonpath(
                        [
                            uploads_directory,
                            target_path,
                        ]
                    )
                    == uploads_directory
                )
            except ValueError:
                is_safe = False

            if not is_safe:
                raise HTTPException(
                    status_code=400,
                    detail="Unsafe local file path",
                )

            storage_objects.append(
                ("local", target_path)
            )

    # 4. Delete physical files.
    # If storage deletion fails, keep database records.
    try:
        for storage_type, storage_path in storage_objects:
            if storage_type == "r2":
                delete_file_from_r2(storage_path)

            elif storage_type == "local":
                if os.path.isfile(storage_path):
                    os.remove(storage_path)

    except Exception as error:
        db.rollback()

        print(
            "PROJECT STORAGE CLEANUP ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
                  detail=(
                "Could not delete all project files "
                "from storage"
            ),
        ) from error


      # 5. Delete project and related database records.
    try:
        db.query(models.SubmissionResult).filter(
            models.SubmissionResult.project_id == project_id
        ).delete(synchronize_session=False)

        db.delete(project)
        db.flush()

        delete_project_translation_cache(
            current_user.id,
            project_id,
        )

        db.commit()
    except Exception as error:
        db.rollback()

        print(
            "PROJECT DATABASE DELETE ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Project files were removed from storage, "
                "but database deletion failed"
            ),
        ) from error

    return {
        "message": "Project deleted",
        "deleted_files": len(project_files),
    }

# ==================================================
# GET PROJECT FILES
# ==================================================

@app.get(
    "/projects/{project_id}/files",
    response_model=list[schemas.ProjectFileResponse],
)
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

# ==================================================
# DELETE PROJECT FILE
# ==================================================

#@app.delete("/projects/{project_id}/files/{file_id}")
def delete_project_file(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Verify that the project and file belong to this user.
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    stored_path = db_file.file_path or ""

    # Find requirements extracted from this file.
    requirement_ids = [
        row[0]
        for row in (
            db.query(models.Requirement.id)
            .filter(
                models.Requirement.project_id == project_id,
                models.Requirement.file_id == file_id,
            )
            .all()
        )
    ]

    try:
        # Delete submission results linked directly
        # to this file.
        db.query(models.SubmissionResult).filter(
            models.SubmissionResult.project_id == project_id,
            models.SubmissionResult.file_id == file_id,
        ).delete(synchronize_session=False)

        if requirement_ids:
            # Delete submission results linked to
            # requirements extracted from this file,
            # even when the submission is another PDF.
            db.query(models.SubmissionResult).filter(
                models.SubmissionResult.project_id == project_id,
                models.SubmissionResult.requirement_id.in_(
                    requirement_ids
                ),
            ).delete(synchronize_session=False)

            # Delete checklist items for these requirements.
            db.query(models.ChecklistItem).filter(
                models.ChecklistItem.project_id == project_id,
                models.ChecklistItem.requirement_id.in_(
                    requirement_ids
                ),
            ).delete(synchronize_session=False)

            # Delete only requirements from this file.
            db.query(models.Requirement).filter(
                models.Requirement.project_id == project_id,
                models.Requirement.file_id == file_id,
            ).delete(synchronize_session=False)

        # Delete file metadata from the current transaction.
        # Changes are not committed yet.
        db.delete(db_file)
        db.flush()

        # Remove the physical file.
        if stored_path.startswith("r2://"):
            object_key = stored_path[len("r2://"):]

            if not object_key:
                raise HTTPException(
                    status_code=500,
                    detail="Invalid R2 object key",
                )

            delete_file_from_r2(object_key)

        elif stored_path:
            # Legacy local files:
            # only remove files inside the upload directory.
            uploads_directory = os.path.realpath(
                os.path.join(os.getcwd(), "uploads")
            )

            target_path = os.path.realpath(stored_path)

            if os.path.commonpath(
                [uploads_directory, target_path]
            ) != uploads_directory:
                raise HTTPException(
                    status_code=400,
                    detail="Unsafe local file path",
                )

            if os.path.isfile(target_path):
                os.remove(target_path)

        # Commit database changes after storage deletion.
        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()

        print(
            "FILE DELETE ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=502,
            detail="Could not delete project file",
        ) from error

    return {
        "message": "File deleted successfully",
        "project_id": project_id,
        "file_id": file_id,
        "deleted_requirements": len(requirement_ids),
    }




# ==================================================
# EXTRACT PDF TEXT
# ==================================================

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
    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    ensure_file_role(
        db_file,
        schemas.FileRole.REQUIREMENTS,
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

    # ==========================================
    # STEP 1: OWNERSHIP CHECK
    # ==========================================

    db_file = get_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    ensure_file_role(
        db_file,
        schemas.FileRole.REQUIREMENTS,
    )

    # ==========================================
    # STEP 2: PAGE-AWARE PDF EXTRACTION
    # ==========================================

    pages = read_pdf_pages(db_file)

    if not pages or not any(
        page["text"].strip()
        for page in pages
    ):

        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from PDF",
        )

    # ==========================================
    # STEP 3: AI REQUIREMENT EXTRACTION V3
    # ==========================================

    try:

        with ai_request_slot(current_user.id):

            ai_result = extract_requirements_with_evidence(
                pages
            )

        # ======================================
        # STEP 4: COMBINE ALL AI REQUIREMENTS
        # ======================================

        extracted_requirements = (
            ai_result["requirements"]
            + ai_result["unverified_requirements"]
        )

        # ======================================
        # STEP 5: REQUIREMENT QUALITY PIPELINE
        # ======================================

        pipeline_result = process_requirements(
            requirements=extracted_requirements,
            pages=pages,
        )

    except HTTPException:

        raise

    except Exception as error:

        print(
            "AI PIPELINE ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="AI analysis failed",
        ) from error

    # ==========================================
    # STEP 6: PRESERVE DISTINCT SOURCE EVIDENCE
    # ==========================================

    def evidence_key(item):

        return (
            item["title"],
            item["description"],
            item["priority"],
            item["source_page"],
            item["source_evidence"],
        )

    requirements_to_save = list(
        pipeline_result["requirements"]
    )

    known_evidence = {
        evidence_key(item)
        for item in requirements_to_save
    }

    preserved_source_count = 0

    for duplicate_info in pipeline_result["exact_duplicates"]:

        duplicate = duplicate_info["duplicate"]

        key = evidence_key(duplicate)

        if key not in known_evidence:

            requirements_to_save.append(duplicate)

            known_evidence.add(key)

            preserved_source_count += 1

    # ==========================================
    # STEP 7: RECHECK OWNERSHIP AND FILE ROLE
    # ==========================================

    db_file = lock_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    ensure_file_role(
        db_file,
        schemas.FileRole.REQUIREMENTS,
    )

    # ==========================================
    # STEP 8: LOAD EXISTING REQUIREMENTS
    # ==========================================

    existing_requirements = (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id,
            models.Requirement.file_id == file_id,
        )
        .order_by(models.Requirement.id)
        .all()
    )

    def serialize_requirement(requirement):

        return {
            "id": requirement.id,
            "project_id": requirement.project_id,
            "file_id": requirement.file_id,
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,
            "source_page": requirement.source_page,
            "source_evidence": requirement.source_evidence,
            "evidence_verified": requirement.evidence_verified,
            "pipeline_version": requirement.pipeline_version,
        }

    existing_by_key = {}

    for requirement in existing_requirements:

        if requirement.evidence_verified is True:

            key = evidence_key(
                serialize_requirement(requirement)
            )

            existing_by_key.setdefault(
                key,
                requirement,
            )

    # ==========================================
    # STEP 9: SAVE VALIDATED REQUIREMENTS
    # ==========================================

    saved_requirements = []

    inserted_count = 0

    reused_count = 0

    try:

        for item in requirements_to_save:

            key = evidence_key(item)

            existing = existing_by_key.get(key)

            # Avoid inserting identical requirements
            # during repeated analysis.

            if existing is not None:

                saved_requirements.append(
                    serialize_requirement(existing)
                )

                reused_count += 1

                continue

            db_requirement = models.Requirement(
                project_id=project_id,
                file_id=file_id,
                title=item["title"],
                description=item["description"],
                priority=item["priority"],
                source_page=item["source_page"],
                source_evidence=item["source_evidence"],
                evidence_verified=item["evidence_verified"],
                pipeline_version=pipeline_result[
                    "pipeline_version"
                ],
            )

            db.add(db_requirement)

            db.flush()

            existing_by_key[key] = db_requirement

            saved_requirements.append(
                serialize_requirement(db_requirement)
            )

            inserted_count += 1

        db.commit()

    except Exception as error:

        db.rollback()

        print(
            "REQUIREMENT SAVE ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="Could not save requirements",
        ) from error

    # ==========================================
    # STEP 10: RETURN ANALYSIS RESULTS
    # ==========================================

    return {
        "project_id": project_id,
        "file_id": file_id,

        # Existing API response field
        "requirements": saved_requirements,

        # New quality information
        "analysis": {
            "pipeline_version": pipeline_result[
                "pipeline_version"
            ],
            "status": pipeline_result["status"],
            "review_required": pipeline_result[
                "review_required"
            ],
            "statistics": pipeline_result["statistics"],
            "priority_counts": pipeline_result[
                "priority_counts"
            ],
            "performance": pipeline_result[
                "performance"
            ],
            "invalid_requirements": pipeline_result[
                "invalid_requirements"
            ],
            "exact_duplicates": pipeline_result[
                "exact_duplicates"
            ],
            "possible_duplicates": pipeline_result[
                "possible_duplicates"
            ],
            "persistence": {
                "inserted_count": inserted_count,
                "reused_count": reused_count,
                "returned_count": len(saved_requirements),
                "preserved_source_count": preserved_source_count,
            },
        },
    }


@app.get("/projects/{project_id}/requirements")
def get_project_requirements(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    # ==========================================
    # STEP 1: VERIFY PROJECT OWNERSHIP
    # ==========================================

    get_owned_project(
        project_id,
        db,
        current_user,
    )

    # ==========================================
    # STEP 2: LOAD SAVED REQUIREMENTS
    # ==========================================

    requirements = (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id
        )
        .order_by(models.Requirement.id.asc())
        .all()
    )

    # ==========================================
    # STEP 3: RETURN REQUIREMENTS WITH EVIDENCE
    # ==========================================

    return [
        {
            "id": requirement.id,
            "project_id": requirement.project_id,
            "file_id": requirement.file_id,
            "title": requirement.title,
            "description": requirement.description,
            "priority": requirement.priority,

            # Source evidence
            "source_page": requirement.source_page,
            "source_evidence": requirement.source_evidence,
            "evidence_verified": requirement.evidence_verified,

            # Pipeline metadata
            "pipeline_version": requirement.pipeline_version,
        }
        for requirement in requirements
    ]




# ==================================================
# SMART CHECKLIST V2 - HELPERS
# ==================================================

def serialize_checklist_item(item, requirement, source_file):

    return {
        "id": item.id,
        "project_id": item.project_id,
        "requirement_id": item.requirement_id,
        "title": item.title,
        "completed": bool(item.completed),

        # Requirement information
        "description": requirement.description,
        "priority": requirement.priority,

        # Source information
        "file_id": requirement.file_id,
        "source_filename": (
            source_file.filename
            if source_file is not None
            else None
        ),
        "source_page": requirement.source_page,
        "source_evidence": requirement.source_evidence,
        "evidence_verified": requirement.evidence_verified,
        "pipeline_version": requirement.pipeline_version,
    }


def load_smart_checklist(
    project_id: int,
    db: Session,
    item_id: int | None = None,
):

    query = (
        db.query(
            models.ChecklistItem,
            models.Requirement,
            models.ProjectFile,
        )
        .join(
            models.Requirement,
            (
                models.Requirement.id
                == models.ChecklistItem.requirement_id
            )
            & (
                models.Requirement.project_id
                == models.ChecklistItem.project_id
            ),
        )
        .outerjoin(
            models.ProjectFile,
            (
                models.ProjectFile.id
                == models.Requirement.file_id
            )
            & (
                models.ProjectFile.project_id
                == models.Requirement.project_id
            ),
        )
        .filter(
            models.ChecklistItem.project_id == project_id
        )
    )

    if item_id is not None:
        query = query.filter(
            models.ChecklistItem.id == item_id
        )

    rows = query.all()

    priority_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }

    rows.sort(
        key=lambda row: (
            priority_order.get(
                row[1].priority,
                3,
            ),
            row[0].id,
        )
    )

    return [
        serialize_checklist_item(
            item,
            requirement,
            source_file,
        )
        for item, requirement, source_file in rows
    ]


# ==================================================
# GENERATE SMART CHECKLIST
# ==================================================

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

    try:

        # Serialize concurrent generation requests
        locked_project = (
            db.query(models.Project)
            .filter(
                models.Project.id == project_id,
                models.Project.user_id == current_user.id,
            )
            .with_for_update()
            .first()
        )

        if locked_project is None:
            raise HTTPException(
                status_code=404,
                detail="Project not found",
            )

        requirements = (
            db.query(models.Requirement)
            .filter(
                models.Requirement.project_id == project_id
            )
            .order_by(models.Requirement.id.asc())
            .all()
        )

        if not requirements:
            raise HTTPException(
                status_code=404,
                detail="No requirements found",
            )

        existing_items = (
            db.query(models.ChecklistItem)
            .filter(
                models.ChecklistItem.project_id == project_id
            )
            .all()
        )

        existing_requirement_ids = {
            item.requirement_id
            for item in existing_items
        }

        new_items = []

        for requirement in requirements:

            if requirement.id in existing_requirement_ids:
                continue

            item = models.ChecklistItem(
                project_id=project_id,
                requirement_id=requirement.id,
                title=requirement.title,
                completed=0,
            )

            new_items.append(item)

            existing_requirement_ids.add(
                requirement.id
            )

        if new_items:
            db.add_all(new_items)
            db.flush()

        result = load_smart_checklist(
            project_id,
            db,
        )

        db.commit()

        return result

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()

        print(
            "Checklist generation failed:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="Could not generate checklist",
        ) from error


# ==================================================
# GET SMART CHECKLIST
# ==================================================

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

    return load_smart_checklist(
        project_id,
        db,
    )


# ==================================================
# UPDATE SMART CHECKLIST ITEM
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
            status_code=404,
            detail="Checklist item not found",
        )

    try:

        item.completed = (
            1 if update.completed else 0
        )

        db.flush()

        result = load_smart_checklist(
            item.project_id,
            db,
            item_id=item.id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail="Checklist requirement not found",
            )

        db.commit()

        return result[0]

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()

        print(
            "Checklist update failed:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="Could not update checklist item",
        ) from error



# ==================================================
# CHECK SUBMISSION WITH AI
# ==================================================



from app.ai_service import check_submission_with_evidence


def serialize_submission_result(db_result):
    return {
        "id": db_result.id,
        "project_id": db_result.project_id,
        "file_id": db_result.file_id,
        "requirement_id": db_result.requirement_id,
        "status": db_result.status,
        "feedback": db_result.feedback,
        "source_page": db_result.source_page,
        "source_evidence": db_result.source_evidence,
        "evidence_verified": db_result.evidence_verified,
        "suggested_improvement": db_result.suggested_improvement,
        "pipeline_version": db_result.pipeline_version,
    }


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

    ensure_file_role(
        db_file,
        schemas.FileRole.SUBMISSION,
    )

    pages = read_pdf_pages(db_file)

    if not pages or not any(
        page["text"].strip()
        for page in pages
    ):
        raise HTTPException(
            status_code=400,
            detail="No text could be extracted from submission PDF",
        )

    requirements_db = (
        db.query(models.Requirement)
        .filter(
            models.Requirement.project_id == project_id
        )
        .order_by(models.Requirement.id)
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

    user_id = current_user.id

    try:
        with ai_request_slot(user_id):

            report = check_submission_with_evidence(
                pages=pages,
                requirements=requirements,
            )

            if report.get("can_persist") is not True:
                raise HTTPException(
                    status_code=502,
                    detail=(
                        "Submission evaluation failed validation. "
                        "Existing results were preserved."
                    ),
                )

            db_file = lock_owned_project_file(
                project_id,
                file_id,
                db,
                current_user,
            )

            ensure_file_role(
                db_file,
                schemas.FileRole.SUBMISSION,
            )

            current_requirements_db = (
                db.query(models.Requirement)
                .filter(
                    models.Requirement.project_id == project_id
                )
                .order_by(models.Requirement.id)
                .populate_existing()
                .with_for_update()
                .all()
            )

            current_requirements = [
                {
                    "id": requirement.id,
                    "title": requirement.title,
                    "description": requirement.description,
                    "priority": requirement.priority,
                }
                for requirement in current_requirements_db
            ]

            if current_requirements != requirements:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Project requirements changed during "
                        "evaluation. Please try again."
                    ),
                )

            db.query(models.SubmissionResult).filter(
                models.SubmissionResult.project_id == project_id,
                models.SubmissionResult.file_id == file_id,
            ).delete(synchronize_session=False)

            saved_results = []

            for item in report["results"]:

                db_result = models.SubmissionResult(
                    project_id=project_id,
                    file_id=file_id,
                    requirement_id=item["requirement_id"],
                    status=item["status"],
                    feedback=item["feedback"],
                    source_page=item["source_page"],
                    source_evidence=item["source_evidence"],
                    evidence_verified=item["evidence_verified"],
                    suggested_improvement=item["suggested_improvement"],
                    pipeline_version=item["pipeline_version"],
                )

                db.add(db_result)
                db.flush()

                saved_results.append(
                    serialize_submission_result(db_result)
                )

            response = {
                "project_id": project_id,
                "file_id": file_id,
                "results": saved_results,
                "evaluation": {
                    "pipeline_version": report["pipeline_version"],
                    "status": report["status"],
                    "can_persist": report["can_persist"],
                    "review_required": report["review_required"],
                    "status_counts": report["status_counts"],
                    "statistics": report["statistics"],
                },
            }

            db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()

        print(
            "SUBMISSION CHECK ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail="Submission check failed",
        ) from error

    return response


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

    get_owned_project(
        project_id,
        db,
        current_user,
    )

    results = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id
            == project_id
        )
        .order_by(
            models.SubmissionResult.file_id,
            models.SubmissionResult.requirement_id,
            models.SubmissionResult.id,
        )
        .all()
    )

    return [
        serialize_submission_result(result)
        for result in results
    ]




# ==================================================
# FINAL SUBMISSION REPORT
# ==================================================

@app.get(
    "/projects/{project_id}/submission/{file_id}/report"
)
def get_submission_report(
    project_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):

    # ======================================
    # STEP 1: OWNERSHIP VERIFICATION
    # ======================================

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

    # ======================================
    # STEP 2: LOAD SUBMISSION RESULTS
    # ======================================

    results = (
        db.query(models.SubmissionResult)
        .filter(
            models.SubmissionResult.project_id
            == project_id,

            models.SubmissionResult.file_id
            == file_id,
        )
        .order_by(
            models.SubmissionResult.requirement_id,
            models.SubmissionResult.id,
        )
        .all()
    )

    if not results:

        raise HTTPException(
            status_code=404,
            detail="No submission results found",
        )

    # ======================================
    # STEP 3: STATUS STATISTICS
    # ======================================

    total = len(results)

    status_counts = {
        "fulfilled": 0,
        "partially_fulfilled": 0,
        "missing": 0,
        "unclear": 0,
    }

    unknown_status_count = 0

    for result in results:

        if result.status in status_counts:

            status_counts[result.status] += 1

        else:

            unknown_status_count += 1

    fulfilled = status_counts["fulfilled"]

    partially_fulfilled = status_counts[
        "partially_fulfilled"
    ]

    missing = status_counts["missing"]

    unclear = status_counts["unclear"]

    # ======================================
    # STEP 4: COMPLETION PERCENTAGE
    # ======================================

    completion_percentage = round(
        (fulfilled / total) * 100,
        2,
    )

    # ======================================
    # STEP 5: EVIDENCE STATISTICS
    # ======================================

    verified_evidence = sum(
        1
        for result in results
        if result.evidence_verified is True
    )

    unverified_evidence = sum(
        1
        for result in results
        if result.evidence_verified is False
    )

    evidence_not_available = sum(
        1
        for result in results
        if result.evidence_verified is None
    )

    evidence_coverage_percentage = round(
        (verified_evidence / total) * 100,
        2,
    )

    # ======================================
    # STEP 6: LEGACY REPORT SUPPORT
    # ======================================

    legacy_results = sum(
        1
        for result in results
        if result.pipeline_version is None
    )

    pipeline_versions = sorted({
        result.pipeline_version

        for result in results

        if result.pipeline_version is not None
    })

    is_legacy_report = (
        legacy_results == total
    )

    # ======================================
    # STEP 7: CHECK REQUIRED EVIDENCE
    # ======================================

    missing_required_evidence = sum(
        1
        for result in results

        if result.status in (
            "fulfilled",
            "partially_fulfilled",
        )

        and (
            result.evidence_verified is not True

            or result.source_page is None

            or result.source_page <= 0

            or not result.source_evidence

            or not result.source_evidence.strip()
        )
    )

    review_required = (
        unclear > 0
        or legacy_results > 0
        or unverified_evidence > 0
        or missing_required_evidence > 0
        or unknown_status_count > 0
        or len(pipeline_versions) > 1
    )

    # ======================================
    # STEP 8: DETAILED RESULTS
    # ======================================

    details = [
        serialize_submission_result(result)
        for result in results
    ]

    # ======================================
    # STEP 9: FINAL REPORT
    # ======================================

    return {
        "project_id": project.id,

        "project_title": project.title,

        "file_id": file_id,

        "submission_filename": (
            submission_file.filename
        ),

        "summary": {
            "total_requirements": total,

            "fulfilled": fulfilled,

            "partially_fulfilled": (
                partially_fulfilled
            ),

            "missing": missing,

            "unclear": unclear,

            "unknown_status_count": (
                unknown_status_count
            ),

            "completion_percentage": (
                completion_percentage
            ),
        },

        "evidence_summary": {
            "verified_evidence": (
                verified_evidence
            ),

            "unverified_evidence": (
                unverified_evidence
            ),

            "evidence_not_available": (
                evidence_not_available
            ),

            "evidence_coverage_percentage": (
                evidence_coverage_percentage
            ),

            "missing_required_evidence": (
                missing_required_evidence
            ),
        },

        "evaluation": {
            "pipeline_versions": (
                pipeline_versions
            ),

            "is_legacy_report": (
                is_legacy_report
            ),

            "legacy_results": (
                legacy_results
            ),

            "review_required": (
                review_required
            ),
        },

        "details": details,
    }

# ==================================================
# DELETE USER ACCOUNT
# ==================================================

@app.delete("/me")
def delete_account(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    user_id = current_user.id

    try:
        # Prevent new AI reservations during deletion.
        # Reject deletion if an AI reservation is active.
        delete_user_ai_data(db, user_id)

        # Lock and verify the user account.
        user = (
            db.query(models.User)
            .filter(models.User.id == user_id)
            .with_for_update()
            .first()
        )

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="User not found",
            )

        # Retrieve all projects owned by this user.
        projects = (
            db.query(models.Project)
            .filter(
                models.Project.user_id == user_id
            )
            .with_for_update()
            .all()
        )

        project_ids = [
            project.id for project in projects
        ]

        storage_objects = []

        if project_ids:
            project_files = (
                db.query(models.ProjectFile)
                .filter(
                    models.ProjectFile.project_id.in_(
                        project_ids
                    )
                )
                .with_for_update()
                .all()
            )

            # Validate every storage path before deletion.
            for project_file in project_files:
                stored_path = project_file.file_path or ""

                if not stored_path.startswith("r2://"):
                    raise HTTPException(
                        status_code=400,
                        detail="Unsupported storage path",
                    )

                object_key = stored_path[len("r2://"):]

                expected_prefix = (
                    f"users/{user_id}/"
                    f"projects/{project_file.project_id}/"
                )

                if (
                    not object_key
                    or not object_key.startswith(
                        expected_prefix
                    )
                    or object_key == expected_prefix
                ):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid R2 file path",
                    )

                storage_objects.append(object_key)

            # Delete submission results first.
            db.query(models.SubmissionResult).filter(
                models.SubmissionResult.project_id.in_(
                    project_ids
                )
            ).delete(synchronize_session=False)

            # Delete checklist items.
            db.query(models.ChecklistItem).filter(
                models.ChecklistItem.project_id.in_(
                    project_ids
                )
            ).delete(synchronize_session=False)

            # Delete extracted requirements.
            db.query(models.Requirement).filter(
                models.Requirement.project_id.in_(
                    project_ids
                )
            ).delete(synchronize_session=False)

            # Delete PDF metadata.
            db.query(models.ProjectFile).filter(
                models.ProjectFile.project_id.in_(
                    project_ids
                )
            ).delete(synchronize_session=False)

            # Delete projects.
            db.query(models.Project).filter(
                models.Project.user_id == user_id
            ).delete(synchronize_session=False)

        # Delete all refresh tokens.
        db.query(models.RefreshToken).filter(
            models.RefreshToken.user_id == user_id
        ).delete(synchronize_session=False)

        # Delete the user account.
        db.delete(user)

        # Detect database errors before storage cleanup.
        db.flush()

        # Delete all registered PDF objects from R2.
        for object_key in storage_objects:
            delete_file_from_r2(object_key)

        # Delete cached translations belonging to the user.
        delete_user_translation_cache(user_id)

        # Commit PostgreSQL changes.
        db.commit()

        return {
            "message": "Account deleted successfully"
        }

    except HTTPException:
        db.rollback()
        raise

    except Exception as error:
        db.rollback()

        print(
            "ACCOUNT DELETE ERROR:",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not complete account deletion. "
                "Please try again later."
            ),
        ) from error
# ==================================================
# UPLOAD PDF TO CLOUDFLARE R2
# ==================================================

@app.post("/projects/{project_id}/files")
def upload_file(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
    file_role: Annotated[
        schemas.FileRole,
        Form(),
    ] = schemas.FileRole.UNCLASSIFIED,
):
    get_owned_project(project_id, db, current_user)

    original_filename = os.path.basename(
        (file.filename or "file").replace("\\", "/")
    )

    if not original_filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    try:
        file_bytes = file.file.read(MAX_PDF_SIZE + 1)
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
        print("R2 UPLOAD ERROR:", type(error).__name__)

        raise HTTPException(
            status_code=502,
            detail="Could not upload file to storage",
        ) from error

    db_file = models.ProjectFile(
        project_id=project_id,
        filename=original_filename,
        file_path=f"r2://{object_key}",
        file_role=file_role.value,
    )

    try:
        db.add(db_file)
        db.flush()

    except Exception as error:
        db.rollback()

        try:
            delete_file_from_r2(object_key)

        except Exception as cleanup_error:
            print(
                "R2 CLEANUP ERROR:",
                type(cleanup_error).__name__,
            )

        raise HTTPException(
            status_code=500,
            detail="Could not save PDF metadata",
        ) from error

    try:
        db.commit()

    except Exception as error:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Could not confirm PDF registration",
        ) from error

    db.refresh(db_file)

    return {
        "id": db_file.id,
        "project_id": db_file.project_id,
        "filename": db_file.filename,
        "file_path": db_file.file_path,
        "file_role": db_file.file_role,
        "uploaded_at": db_file.uploaded_at,
    }




# ==================================================
# ASSIGN FILE ROLE
# ==================================================

@app.patch(
    "/projects/{project_id}/files/{file_id}/role",
    response_model=schemas.ProjectFileResponse,
)
def update_file_role(
    project_id: int,
    file_id: int,
    update: schemas.ProjectFileRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_file = lock_owned_project_file(
        project_id,
        file_id,
        db,
        current_user,
    )

    requested_role = update.file_role.value

    # Repeated requests with the same role are allowed.
    if db_file.file_role == requested_role:
        return db_file

    # Do not change already classified files.
    if (
        db_file.file_role
        != schemas.FileRole.UNCLASSIFIED.value
    ):
        raise HTTPException(
            status_code=409,
            detail="File role is already assigned",
        )

    has_requirements = (
        db.query(models.Requirement.id)
        .filter(
            models.Requirement.project_id == project_id,
            models.Requirement.file_id == file_id,
        )
        .first()
        is not None
    )

    has_submission_results = (
        db.query(models.SubmissionResult.id)
        .filter(
            models.SubmissionResult.project_id == project_id,
            models.SubmissionResult.file_id == file_id,
        )
        .first()
        is not None
    )

    # Protect existing requirements.
    if (
        requested_role == schemas.FileRole.SUBMISSION.value
        and has_requirements
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "This file contains existing requirements "
                "and cannot be assigned as a submission."
            ),
        )

    # Protect existing submission results.
    if (
        requested_role == schemas.FileRole.REQUIREMENTS.value
        and has_submission_results
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "This file contains existing submission "
                "results and cannot be assigned as requirements."
            ),
        )

    db_file.file_role = requested_role

    try:
        db.commit()
        db.refresh(db_file)

    except Exception:
        db.rollback()
        raise

    return db_file


# ==================================================
# GLOBAL CORS MIDDLEWARE
# Keep this AFTER all routes.
# ==================================================

app = CORSMiddleware(
    app=app,
    allow_origins=(
        DEFAULT_CORS_ORIGINS
        + ADDITIONAL_CORS_ORIGINS
    ),
    allow_origin_regex=(
        r"^https?://(?:localhost|127\.0\.0\.1)"
        r"(?::\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
