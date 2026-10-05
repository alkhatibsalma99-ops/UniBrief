from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = {
        "from_attributes": True
    }


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
class ProjectCreate(BaseModel):
    title: str
    description: str | None = None


class ProjectResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    user_id: int

    model_config = {
        "from_attributes": True
    }
class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None

    
class ChecklistUpdate(BaseModel):
    completed: bool    