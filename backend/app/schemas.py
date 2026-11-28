
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


# ==========================================
# USER REGISTRATION
# ==========================================

class UserCreate(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=100,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=128,
    )


# ==========================================
# USER RESPONSE
# ==========================================

class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = {
        "from_attributes": True
    }


# ==========================================
# USER LOGIN
# ==========================================

class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ==========================================
# JWT TOKEN RESPONSE
# ==========================================

class TokenResponse(BaseModel):
    access_token: str
    token_type: str


# ==========================================
# PROJECT CREATION
# ==========================================

class ProjectCreate(BaseModel):
    title: str
    description: str | None = None


# ==========================================
# PROJECT RESPONSE
# ==========================================

class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    user_id: int

    model_config = {
        "from_attributes": True
    }


# ==========================================
# PROJECT UPDATE
# ==========================================

class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None


# ==========================================
# CHECKLIST UPDATE
# ==========================================

class ChecklistUpdate(BaseModel):
    completed: bool


# ==========================================
# NEW: FILE ROLE
# ==========================================

class FileRole(str, Enum):
    REQUIREMENTS = "requirements"
    SUBMISSION = "submission"
    UNCLASSIFIED = "unclassified"


# ==========================================
# NEW: ASSIGNABLE FILE ROLE
# ==========================================

class AssignableFileRole(str, Enum):
    REQUIREMENTS = "requirements"
    SUBMISSION = "submission"


# ==========================================
# NEW: PROJECT FILE RESPONSE
# ==========================================

class ProjectFileResponse(BaseModel):
    id: int
    project_id: int
    filename: str
    file_path: str
    file_role: FileRole
    uploaded_at: datetime

    model_config = {
        "from_attributes": True
    }


# ==========================================
# NEW: FILE ROLE UPDATE
# ==========================================

class ProjectFileRoleUpdate(BaseModel):
    file_role: AssignableFileRole
