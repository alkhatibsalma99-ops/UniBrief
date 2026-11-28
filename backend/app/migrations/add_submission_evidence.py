
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
    "suggested_improvement": "TEXT",
    "pipeline_version": "VARCHAR(20)",
}

PROTECTED_TABLES = (
    "requirements",
    "checklist_items",
    "submission_results",
)

LEGACY_SUBMISSION_COLUMNS = (
    "id",
    "project_id",
    "file_id",
    "requirement_id",
    "status",
    "feedback",
)


# ==========================================
# DATABASE SAFETY
# ==========================================

def validate_database():

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


# ==========================================
# RECORD COUNTS
# ==========================================

def get_record_counts(connection):

    return {
        table: connection.execute(
            text(f"SELECT COUNT(*) FROM {table}")
        ).scalar_one()

        for table in PROTECTED_TABLES
    }


# ==========================================
# DATA SNAPSHOT
# ==========================================

def get_data_snapshot(
    connection,
    table,
    columns,
):

    if table not in PROTECTED_TABLES:

        raise ValueError(
            "Invalid protected table."
        )

    preparer = connection.dialect.identifier_preparer

    selected_columns = ", ".join(
        preparer.quote(column)
        for column in columns
    )

    quoted_table = preparer.quote(table)

    rows = connection.execute(
        text(
            f"SELECT {selected_columns} "
            f"FROM {quoted_table} "
            f"ORDER BY id"
        )
    ).fetchall()

    return [
        tuple(row)
        for row in rows
    ]


# ==========================================
# SCHEMA VERIFICATION
# ==========================================

def verify_schema(connection):

    columns = {
        column["name"]: column

        for column in inspect(
            connection
        ).get_columns("submission_results")
    }

    print("\nSchema verification:")

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


# ==========================================
# MAIN MIGRATION
# ==========================================

def migrate():

    validate_database()

    print("=" * 65)
    print("UNIBRIEF SUBMISSION EVIDENCE MIGRATION")
    print("=" * 65)

    with engine.begin() as connection:

        # ==================================
        # STEP 1: VERIFY ACTIVE DATABASE
        # ==================================

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
        # STEP 2: LOCK PROTECTED TABLES
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

        print("Table locks: ACQUIRED")

        # ==================================
        # STEP 3: RECORD COUNTS
        # ==================================

        before_counts = get_record_counts(
            connection
        )

        print("\nRecords before migration:")

        for table, count in before_counts.items():

            print(f"{table}: {count}")

        # ==================================
        # STEP 4: SNAPSHOT EXISTING DATA
        # ==================================

        inspector = inspect(connection)

        original_columns = {}

        before_snapshots = {}

        for table in PROTECTED_TABLES:

            original_columns[table] = [
                column["name"]

                for column in inspector.get_columns(
                    table
                )
            ]

            before_snapshots[table] = (
                get_data_snapshot(
                    connection,
                    table,
                    original_columns[table],
                )
            )

        existing_submission_columns = set(
            original_columns["submission_results"]
        )

        if not set(
            LEGACY_SUBMISSION_COLUMNS
        ).issubset(existing_submission_columns):

            raise RuntimeError(
                "Unexpected legacy submission schema."
            )

        new_columns = [
            name
            for name in EXPECTED_COLUMNS
            if name not in existing_submission_columns
        ]

        print("\nExisting data snapshots: CREATED")

        print(
            "Columns to add:",
            len(new_columns),
        )

        # ==================================
        # STEP 5: ADD EVIDENCE COLUMNS
        # ==================================

        print("\nAdding submission evidence columns...")

        for name, column_type in (
            EXPECTED_COLUMNS.items()
        ):

            connection.execute(
                text(
                    "ALTER TABLE submission_results "
                    f"ADD COLUMN IF NOT EXISTS "
                    f"{name} {column_type}"
                )
            )

        # ==================================
        # STEP 6: VERIFY SCHEMA
        # ==================================

        verify_schema(connection)

        # ==================================
        # STEP 7: VERIFY RECORD COUNTS
        # ==================================

        after_counts = get_record_counts(
            connection
        )

        print("\nRecords after migration:")

        for table, count in after_counts.items():

            print(f"{table}: {count}")

        if before_counts != after_counts:

            raise RuntimeError(
                "Record count mismatch. "
                "Migration rolled back."
            )

        print("\n[PASS] Record counts preserved.")

        # ==================================
        # STEP 8: VERIFY ORIGINAL CONTENT
        # ==================================

        print("\nData preservation verification:")

        for table in PROTECTED_TABLES:

            after_snapshot = get_data_snapshot(
                connection,
                table,
                original_columns[table],
            )

            if (
                before_snapshots[table]
                != after_snapshot
            ):

                raise RuntimeError(
                    f"Existing data changed: {table}. "
                    "Migration rolled back."
                )

            print(
                f"[PASS] {table}: "
                "original data unchanged."
            )

        # ==================================
        # STEP 9: VERIFY NEW COLUMN VALUES
        # ==================================

        for name in new_columns:

            non_null_count = connection.execute(
                text(
                    "SELECT COUNT(*) "
                    "FROM submission_results "
                    f"WHERE {name} IS NOT NULL"
                )
            ).scalar_one()

            if non_null_count != 0:

                raise RuntimeError(
                    f"Unexpected existing values: {name}"
                )

            print(
                f"[PASS] {name}: "
                "existing rows remain NULL."
            )

        # ==================================
        # STEP 10: LEGACY SUBMISSION REPORTS
        # ==================================

        legacy_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM submission_results
                WHERE source_page IS NULL
                  AND source_evidence IS NULL
                  AND evidence_verified IS NULL
                  AND suggested_improvement IS NULL
                  AND pipeline_version IS NULL
            """)
        ).scalar_one()

        print(
            "\nSubmission results without evidence:",
            legacy_count,
        )

        if before_counts["submission_results"] == 0:

            print(
                "[NOTICE] No existing submission results."
            )

            print(
                "A separate legacy-data test is required."
            )

        if not new_columns:

            print(
                "[PASS] Schema already migrated."
            )

    # Transaction committed successfully.

    print("\n" + "=" * 65)
    print("MIGRATION COMPLETED SUCCESSFULLY")
    print("=" * 65)

    print("Database safety: PASSED")
    print("Schema verification: PASSED")
    print("Record count verification: PASSED")
    print("Data preservation: PASSED")
    print("AI requests: 0")
    print("R2 requests: 0")


if __name__ == "__main__":

    migrate()
