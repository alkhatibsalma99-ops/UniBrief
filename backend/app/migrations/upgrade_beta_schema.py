
from getpass import getpass
import argparse

import psycopg
from psycopg import sql


# ==========================================
# LOCAL RESTORE DATABASE ONLY
# ==========================================

HOST = "127.0.0.1"
PORT = 5432
DATABASE = "unibrief_restore_test"
USER = "postgres"


# ==========================================
# PROTECTED TABLES
# ==========================================

TABLES = (
    "ai_active_requests",
    "ai_daily_usage",
    "checklist_items",
    "login_rate_limits",
    "project_files",
    "projects",
    "refresh_tokens",
    "requirements",
    "submission_results",
    "users",
)


# ==========================================
# EXPECTED SCHEMA
# ==========================================

EVIDENCE_COLUMNS = {
    "requirements": {
        "source_page": "INTEGER",
        "source_evidence": "TEXT",
        "evidence_verified": "BOOLEAN",
        "pipeline_version": "VARCHAR(20)",
    },
    "submission_results": {
        "source_page": "INTEGER",
        "source_evidence": "TEXT",
        "evidence_verified": "BOOLEAN",
        "suggested_improvement": "TEXT",
        "pipeline_version": "VARCHAR(20)",
    },
}

EXPECTED_LEGACY_COLUMNS = {
    "project_files": {
        "id", "project_id", "filename",
        "file_path", "uploaded_at",
    },
    "requirements": {
        "id", "project_id", "file_id",
        "title", "description", "priority",
    },
    "submission_results": {
        "id", "project_id", "file_id",
        "requirement_id", "status", "feedback",
    },
}

ROLE_CONSTRAINT = "ck_project_files_file_role"


def qualified_table(table):
    if table not in TABLES:
        raise RuntimeError("Unexpected table.")

    return sql.Identifier("public", table)


# ==========================================
# DATABASE SAFETY
# ==========================================

def verify_database(cursor):

    cursor.execute("""
        SELECT
            current_database(),
            current_user,
           host(inet_server_addr()),
            inet_server_port()
    """)

    database, user, host, port = cursor.fetchone()

    if (
        database != DATABASE
        or user != USER
        or host != HOST
        or port != PORT
    ):
        raise RuntimeError(
            "Migration blocked: unexpected database."
        )

    print("Database:", database)
    print("Host:", host)
    print("Port:", port)
    print("[PASS] Database safety")


# ==========================================
# TABLE METADATA
# ==========================================

def get_columns(cursor, table):

    cursor.execute("""
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """, (table,))

    return {
        row[0]: {
            "type": row[1],
            "length": row[2],
            "nullable": row[3],
            "default": row[4],
        }
        for row in cursor.fetchall()
    }


def get_count(cursor, table):

    cursor.execute(
        sql.SQL("SELECT COUNT(*) FROM {}").format(
            qualified_table(table)
        )
    )

    return cursor.fetchone()[0]


# ==========================================
# DATA SNAPSHOT
# ==========================================

def get_snapshot(cursor, table, columns):

    selected = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in columns
    )

    cursor.execute(
        sql.SQL("""
            SELECT to_jsonb(original_row)::text
            FROM (
                SELECT {}
                FROM {}
            ) AS original_row
            ORDER BY (to_jsonb(original_row)::text)
                COLLATE "C"
        """).format(
            selected,
            qualified_table(table),
        )
    )

    return tuple(
        row[0] for row in cursor.fetchall()
    )
def get_constraints(cursor, table):

    cursor.execute("""
        SELECT
            c.conname,
            c.contype,
            c.convalidated,
            pg_get_constraintdef(c.oid)
        FROM pg_constraint AS c
        JOIN pg_class AS t
          ON t.oid = c.conrelid
        JOIN pg_namespace AS n
          ON n.oid = t.relnamespace
        WHERE n.nspname = 'public'
          AND t.relname = %s
        ORDER BY c.conname
    """, (table,))

    return {
        row[0]: tuple(row[1:])
        for row in cursor.fetchall()
    }


# ==========================================
# FILE ROLE MIGRATION
# ==========================================

def migrate_file_roles(cursor):

    cursor.execute("""
        ALTER TABLE public.project_files
        ADD COLUMN IF NOT EXISTS
            file_role VARCHAR(20)
            NOT NULL DEFAULT 'unclassified'
    """)

    columns = get_columns(cursor, "project_files")
    role = columns["file_role"]

    if (
        role["type"] != "character varying"
        or role["length"] != 20
        or role["nullable"] != "NO"
        or role["default"]
           != "'unclassified'::character varying"
    ):
        raise RuntimeError(
            "Unexpected file_role schema."
        )

    constraints = get_constraints(
        cursor, "project_files"
    )

    if ROLE_CONSTRAINT not in constraints:

        cursor.execute("""
            ALTER TABLE public.project_files
            ADD CONSTRAINT ck_project_files_file_role
            CHECK (
                file_role IN (
                    'requirements',
                    'submission',
                    'unclassified'
                )
            )
        """)

    # Compare the actual constraint with a reference
    # constraint generated by PostgreSQL itself.

    cursor.execute("""
        CREATE TEMP TABLE beta_role_reference (
            file_role VARCHAR(20),
            CONSTRAINT beta_role_reference_check
            CHECK (
                file_role IN (
                    'requirements',
                    'submission',
                    'unclassified'
                )
            )
        ) ON COMMIT DROP
    """)

    cursor.execute("""
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid =
            'pg_temp.beta_role_reference'::regclass
          AND conname = 'beta_role_reference_check'
    """)

    expected_definition = cursor.fetchone()[0]

    actual = get_constraints(
        cursor, "project_files"
    )[ROLE_CONSTRAINT]

    if actual != (
        "c",
        True,
        expected_definition,
    ):
        raise RuntimeError(
            "Unexpected file_role constraint."
        )

    cursor.execute("""
        SELECT COUNT(*)
        FROM public.project_files
        WHERE file_role IS NULL
           OR file_role NOT IN (
               'requirements',
               'submission',
               'unclassified'
           )
    """)

    if cursor.fetchone()[0] != 0:
        raise RuntimeError(
            "Invalid file roles detected."
        )

    print("[PASS] File role schema")


# ==========================================
# EVIDENCE MIGRATIONS
# ==========================================

def migrate_evidence(cursor):

    expected_types = {
        "INTEGER": ("integer", None),
        "TEXT": ("text", None),
        "BOOLEAN": ("boolean", None),
        "VARCHAR(20)": ("character varying", 20),
    }

    for table, definitions in EVIDENCE_COLUMNS.items():

        for column, column_type in definitions.items():

            cursor.execute(
                sql.SQL("""
                    ALTER TABLE {}
                    ADD COLUMN IF NOT EXISTS {} {}
                """).format(
                    qualified_table(table),
                    sql.Identifier(column),
                    sql.SQL(column_type),
                )
            )

        actual_columns = get_columns(cursor, table)

        for column, column_type in definitions.items():

            actual = actual_columns[column]

            expected_type, expected_length = (
                expected_types[column_type]
            )

            if (
                actual["type"] != expected_type
                or actual["length"] != expected_length
                or actual["nullable"] != "YES"
                or actual["default"] is not None
            ):
                raise RuntimeError(
                    f"Unexpected schema: "
                    f"{table}.{column}"
                )

            print(f"[PASS] {table}.{column}")


# ==========================================
# VERIFY NEW COLUMN VALUES
# ==========================================

def verify_new_values(cursor, original_columns):

    if "file_role" not in original_columns["project_files"]:

        cursor.execute("""
            SELECT COUNT(*)
            FROM public.project_files
            WHERE file_role IS DISTINCT FROM
                'unclassified'
        """)

        if cursor.fetchone()[0] != 0:
            raise RuntimeError(
                "Unexpected legacy file roles."
            )

        print("[PASS] Legacy files: unclassified")

    for table, definitions in EVIDENCE_COLUMNS.items():

        for column in definitions:

            if column in original_columns[table]:
                continue

            cursor.execute(
                sql.SQL("""
                    SELECT COUNT(*)
                    FROM {}
                    WHERE {} IS NOT NULL
                """).format(
                    qualified_table(table),
                    sql.Identifier(column),
                )
            )

            if cursor.fetchone()[0] != 0:
                raise RuntimeError(
                    f"Unexpected legacy evidence: "
                    f"{table}.{column}"
                )

    print("[PASS] New evidence fields remain NULL")


# ==========================================
# MAIN MIGRATION
# ==========================================

def migrate(rollback_test=False):

    password = getpass(
        "Local PostgreSQL password: "
    )

    connection = psycopg.connect(
        host=HOST,
        port=PORT,
        dbname=DATABASE,
        user=USER,
        password=password,
        connect_timeout=10,
        sslmode="disable",
    )

    del password

    try:

        with connection.cursor() as cursor:

            verify_database(cursor)

            cursor.execute("""
                SET LOCAL lock_timeout = '5s'
            """)

            cursor.execute("""
                SET LOCAL statement_timeout = '60s'
            """)

            cursor.execute(
                sql.SQL("""
                    LOCK TABLE {}
                    IN ACCESS EXCLUSIVE MODE
                """).format(
                    sql.SQL(", ").join(
                        qualified_table(table)
                        for table in TABLES
                    )
                )
            )

            print("[PASS] Table locks acquired")

            original_columns = {}
            before_counts = {}
            before_snapshots = {}
            before_constraints = {}

            print("\nRECORDS BEFORE MIGRATION")

            for table in TABLES:

                columns = get_columns(cursor, table)

                if not columns:
                    raise RuntimeError(
                        f"Missing table: {table}"
                    )

                original_columns[table] = list(columns)

                required = EXPECTED_LEGACY_COLUMNS.get(
                    table, set()
                )

                if not required.issubset(columns):
                    raise RuntimeError(
                        f"Unexpected legacy schema: {table}"
                    )

                before_counts[table] = get_count(
                    cursor, table
                )

                before_snapshots[table] = get_snapshot(
                    cursor,
                    table,
                    original_columns[table],
                )

                before_constraints[table] = (
                    get_constraints(cursor, table)
                )

                print(
                    f"{table}: {before_counts[table]}"
                )

            new_column_count = (
                int(
                    "file_role"
                    not in original_columns["project_files"]
                )
                + sum(
                    column not in original_columns[table]
                    for table, definitions
                    in EVIDENCE_COLUMNS.items()
                    for column in definitions
                )
            )

            print(
                "\nColumns to add:",
                new_column_count,
            )

            # All three migrations share one transaction.

            migrate_file_roles(cursor)
            migrate_evidence(cursor)

            print("\nDATA PRESERVATION")

            for table in TABLES:

                after_count = get_count(cursor, table)

                after_snapshot = get_snapshot(
                    cursor,
                    table,
                    original_columns[table],
                )

                if after_count != before_counts[table]:
                    raise RuntimeError(
                        f"Record count changed: {table}"
                    )

                if after_snapshot != before_snapshots[table]:
                    raise RuntimeError(
                        f"Original data changed: {table}"
                    )

                current_constraints = get_constraints(
                    cursor, table
                )

                for name, definition in (
                    before_constraints[table].items()
                ):

                    if current_constraints.get(name) != definition:
                        raise RuntimeError(
                            f"Constraint changed: {name}"
                        )

                print(
                    f"[PASS] {table}: "
                    f"{after_count} records unchanged"
                )

            verify_new_values(
                cursor, original_columns
            )

        if rollback_test:

            connection.rollback()

            print("\n" + "=" * 60)
            print("ROLLBACK TEST COMPLETED")
            print("All migration changes rolled back.")
            print("=" * 60)

        else:

            connection.commit()

            print("\n" + "=" * 60)
            print("MIGRATION COMPLETED SUCCESSFULLY")
            print("=" * 60)

        print("Database safety: PASSED")
        print("Schema verification: PASSED")
        print("Data preservation: PASSED")
        print("Constraint preservation: PASSED")
        print("AI requests: 0")
        print("R2 requests: 0")

    except BaseException:

        connection.rollback()

        print("\nMIGRATION FAILED")
        print("Transaction rolled back.")

        raise

    finally:

        connection.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--rollback-test",
        action="store_true",
        help="Test migration without saving changes.",
    )

    args = parser.parse_args()

    migrate(
        rollback_test=args.rollback_test
    )
