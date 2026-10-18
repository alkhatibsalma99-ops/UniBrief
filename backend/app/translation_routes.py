
import hashlib
import os
import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.security import decode_access_token
from app.ai_service import translate_content_with_ai


router = APIRouter(tags=["AI Translation"])
security = HTTPBearer()

CACHE_PATH = Path(
    os.getenv(
        "TRANSLATION_CACHE_PATH",
        "translation_cache.sqlite3",
    )
)


class TranslationRequest(BaseModel):
    target_language: Literal["en", "de", "ar"]
    texts: list[str] = Field(
        min_length=1,
        max_length=30,
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(
        security
    ),
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


def open_cache():
    CACHE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    connection = sqlite3.connect(
        str(CACHE_PATH),
        timeout=15,
    )

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS translations (
            cache_key TEXT PRIMARY KEY,
            translated_text TEXT NOT NULL
        )
        """
    )

    connection.commit()
    return connection


def create_cache_key(
    user_id: int,
    project_id: int,
    language: str,
    text: str,
) -> str:
    raw = (
        f"{user_id}:{project_id}:"
        f"{language}:{text}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


@router.post(
    "/projects/{project_id}/translate"
)
def translate_project_content(
    project_id: int,
    request: TranslationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        get_current_user
    ),
):
    # Verify project ownership.
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

    # Limit request size and AI cost.
    if any(
        len(value) > 4000
        for value in request.texts
    ):
        raise HTTPException(
            status_code=400,
            detail="Each text must be at most 4000 characters",
        )

    if sum(
        len(value) for value in request.texts
    ) > 30000:
        raise HTTPException(
            status_code=400,
            detail="Request text is too large",
        )

    translations = [""] * len(request.texts)
    missing_texts = []
    missing_indices = []
    missing_keys = []

    cache_hits = 0

    with open_cache() as connection:
        for index, original_text in enumerate(
            request.texts
        ):
            if not original_text.strip():
                translations[index] = original_text
                continue

            key = create_cache_key(
                current_user.id,
                project_id,
                request.target_language,
                original_text,
            )

            cached = connection.execute(
                """
                SELECT translated_text
                FROM translations
                WHERE cache_key = ?
                """,
                (key,),
            ).fetchone()

            if cached is not None:
                translations[index] = cached[0]
                cache_hits += 1
            else:
                missing_indices.append(index)
                missing_texts.append(original_text)
                missing_keys.append(key)

        # Only send uncached texts to AI.
        if missing_texts:
            try:
                new_translations = (
                    translate_content_with_ai(
                        texts=missing_texts,
                        target_language=(
                            request.target_language
                        ),
                    )
                )
            except Exception as error:
                print(
                    "TRANSLATION ERROR:",
                    type(error).__name__,
                )
                raise HTTPException(
                    status_code=502,
                    detail="AI translation failed",
                ) from error

            if len(new_translations) != len(
                missing_texts
            ):
                raise HTTPException(
                    status_code=502,
                    detail="Invalid translation response",
                )

            for index, key, translated in zip(
                missing_indices,
                missing_keys,
                new_translations,
            ):
                translations[index] = translated

                connection.execute(
                    """
                    INSERT OR REPLACE INTO translations
                    (cache_key, translated_text)
                    VALUES (?, ?)
                    """,
                    (key, translated),
                )

            connection.commit()

    return {
        "project_id": project_id,
        "target_language": request.target_language,
        "translations": translations,
        "cache_hits": cache_hits,
        "translated_count": len(missing_texts),
    }
