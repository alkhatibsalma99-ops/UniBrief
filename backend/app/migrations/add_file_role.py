
from sqlalchemy import text
from app.database import engine


ALLOWED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "::1",
}

ALLOWED_DATABASE = "unibrief_test_db"


def migrate():

    # Safety: PostgreSQL only
    if engine.dialect.name != "postgresql":
        raise RuntimeError(
            "This migration requires PostgreSQL."
        )

    # Safety: local database only
    if engine.url.host not in ALLOWED_HOSTS:
        raise RuntimeError(
            "Migration blocked: non-local database."
        )

    # Safety: test database only
    if engine.url.database != ALLOWED_DATABASE:
        raise RuntimeError(
            "Migration blocked: use unibrief_test_db."
        )

    print("Starting File Role migration...")
    print(f"Database: {engine.url.database}")

    with engine.begin() as connection:

        # Verify the actual connected database
        current_database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if current_database != ALLOWED_DATABASE:
            raise RuntimeError(
                "Unexpected database connection."
            )

        # Prevent concurrent modifications during migration
        connection.execute(
            text("""
                LOCK TABLE project_files
                IN ACCESS EXCLUSIVE MODE
            """)
        )

        # Count existing files
        before_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM project_files
            """)
        ).scalar_one()

        # Add the new column
        connection.execute(
            text("""
                ALTER TABLE project_files
                ADD COLUMN IF NOT EXISTS
                file_role VARCHAR(20)
                NOT NULL DEFAULT 'unclassified'
            """)
        )

        # Check whether the constraint already exists
        constraint_exists = connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname =
                        'ck_project_files_file_role'
                    AND conrelid =
                        'project_files'::regclass
                )
            """)
        ).scalar_one()

        # Add the constraint only if necessary
        if not constraint_exists:
            connection.execute(
                text("""
                    ALTER TABLE project_files
                    ADD CONSTRAINT
                        ck_project_files_file_role
                    CHECK (
                        file_role IN (
                            'requirements',
                            'submission',
                            'unclassified'
                        )
                    )
                """)
            )

        # Verify that existing files were preserved
        after_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM project_files
            """)
        ).scalar_one()

        if before_count != after_count:
            raise RuntimeError(
                "File count changed. Migration rolled back."
            )

        print(f"Files before: {before_count}")
        print(f"Files after: {after_count}")

    print("Migration completed successfully.")


if __name__ == "__main__":
    migrate()
