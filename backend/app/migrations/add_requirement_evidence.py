from sqlalchemy import inspect, text

from app.database import engine


EXPECTED_DATABASE = "unibrief_test_db"

ALLOWED_HOSTS = {
    "127.0.0.1",
    "localhost",
    "::1",
}

EXPECTED_COLUMNS = {
    "source_page": "INTEGER",
    "source_evidence": "TEXT",
    "evidence_verified": "BOOLEAN",
    "pipeline_version": "VARCHAR(20)",
}


def migrate():

    # ======================================
    # STEP 1: DATABASE SAFETY CHECK
    # ======================================

    if engine.dialect.name != "postgresql":

        raise RuntimeError(
            "PostgreSQL database required."
        )

    if engine.url.host not in ALLOWED_HOSTS:

        raise RuntimeError(
            "Migration blocked: non-local database."
        )

    if engine.url.database != EXPECTED_DATABASE:

        raise RuntimeError(
            "Migration blocked: unsafe database."
        )

    print("=" * 60)
    print("UNIBRIEF REQUIREMENT EVIDENCE MIGRATION")
    print("=" * 60)

    with engine.begin() as connection:

        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database_name != EXPECTED_DATABASE:

            raise RuntimeError(
                "Unexpected database connection."
            )

        print("Database:", database_name)
        print("Safety check: PASSED")

        # ==================================
        # STEP 2: LOCK TABLES
        # ==================================

        connection.execute(
            text("SET LOCAL lock_timeout = '5s'")
        )

        connection.execute(
            text("""
                LOCK TABLE
                    requirements,
                    checklist_items,
                    submission_results
                IN ACCESS EXCLUSIVE MODE
            """)
        )

        # ==================================
        # STEP 3: PRESERVE EXISTING DATA
        # ==================================

        tables = (
            "requirements",
            "checklist_items",
            "submission_results",
        )

        before_counts = {}

        for table in tables:

            before_counts[table] = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

        print()
        print("Records before migration:")

        for table, count in before_counts.items():

            print(f"{table}: {count}")

        # ==================================
        # STEP 4: ADD NEW COLUMNS
        # ==================================

        print()
        print("Adding evidence columns...")

        connection.execute(
            text("""
                ALTER TABLE requirements
                ADD COLUMN IF NOT EXISTS
                    source_page INTEGER
            """)
        )

        connection.execute(
            text("""
                ALTER TABLE requirements
                ADD COLUMN IF NOT EXISTS
                    source_evidence TEXT
            """)
        )

        connection.execute(
            text("""
                ALTER TABLE requirements
                ADD COLUMN IF NOT EXISTS
                    evidence_verified BOOLEAN
            """)
        )

        connection.execute(
            text("""
                ALTER TABLE requirements
                ADD COLUMN IF NOT EXISTS
                    pipeline_version VARCHAR(20)
            """)
        )

        # ==================================
        # STEP 5: VERIFY DATABASE SCHEMA
        # ==================================

        columns = {
            column["name"]: column

            for column in inspect(
                connection
            ).get_columns("requirements")
        }

        print()
        print("Schema verification:")

        for name, expected_type in (
            EXPECTED_COLUMNS.items()
        ):

            if name not in columns:

                raise RuntimeError(
                    f"Missing column: {name}"
                )

            column = columns[name]

            actual_type = str(
                column["type"]
            ).upper()

            if actual_type != expected_type:

                raise RuntimeError(
                    f"Invalid column type: {name}. "
                    f"Expected {expected_type}, "
                    f"found {actual_type}"
                )

            if not column["nullable"]:

                raise RuntimeError(
                    f"Column must be nullable: {name}"
                )

            if column.get("default") is not None:

                raise RuntimeError(
                    f"Unexpected default: {name}"
                )

            print(
                f"[PASS] {name}: "
                f"{actual_type}, nullable=True"
            )

        # ==================================
        # STEP 6: VERIFY RECORD COUNTS
        # ==================================

        after_counts = {}

        for table in tables:

            after_counts[table] = connection.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()

        print()
        print("Records after migration:")

        for table, count in after_counts.items():

            print(f"{table}: {count}")

        if before_counts != after_counts:

            raise RuntimeError(
                "Record count mismatch. "
                "Migration rolled back."
            )

        print()
        print("[PASS] Record counts preserved.")

        # ==================================
        # STEP 7: LEGACY REQUIREMENTS
        # ==================================

        legacy_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM requirements
                WHERE source_page IS NULL
                  AND source_evidence IS NULL
                  AND evidence_verified IS NULL
                  AND pipeline_version IS NULL
            """)
        ).scalar_one()

        print(
            "Requirements without evidence:",
            legacy_count,
        )

    # Transaction committed successfully

    print()
    print("=" * 60)
    print("MIGRATION COMPLETED SUCCESSFULLY")
    print("=" * 60)

    print("Schema verification: PASSED")
    print("Record count verification: PASSED")
    print("AI requests: 0")


if __name__ == "__main__":

    migrate()