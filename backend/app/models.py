from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
    DateTime,
)

from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    projects = relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan"
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    title = Column(
        String(200),
        nullable=False
    )

    description = Column(
        String(1000),
        nullable=True
    )

    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    owner = relationship(
        "User",
        back_populates="projects"
    )

    files = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan"
    )
    requirements = relationship(
    "Requirement",
    cascade="all, delete-orphan"
    )
    checklist_items = relationship(
    "ChecklistItem",
    cascade="all, delete-orphan"
    )

class ProjectFile(Base):
    __tablename__ = "project_files"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    project_id = Column(
        Integer,
        ForeignKey(
            "projects.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    filename = Column(
        String(255),
        nullable=False
    )

    file_path = Column(
        String(500),
        nullable=False
    )

    uploaded_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    project = relationship(
        "Project",
        back_populates="files"
    )
    requirements = relationship(
    "Requirement",
    cascade="all, delete-orphan"
    )
class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    file_id = Column(
        Integer,
        ForeignKey("project_files.id", ondelete="CASCADE"),
        nullable=False
    )

    title = Column(
        String(255),
        nullable=False
    )

    description = Column(
        String(2000),
        nullable=False
    )

    priority = Column(
        String(20),
        nullable=False
    )
    checklist_items = relationship(
    "ChecklistItem",
    cascade="all, delete-orphan"
    )
class ChecklistItem(Base):
    __tablename__ = "checklist_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    requirement_id = Column(
        Integer,
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False
    )

    title = Column(
        String(255),
        nullable=False
    )

    completed = Column(
        Integer,
        default=0,
        nullable=False
    )  
class SubmissionResult(Base):
    __tablename__ = "submission_results"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    file_id = Column(
        Integer,
        ForeignKey("project_files.id", ondelete="CASCADE"),
        nullable=False
    )

    requirement_id = Column(
        Integer,
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False
    )

    feedback = Column(
        String(2000),
        nullable=False
    )          