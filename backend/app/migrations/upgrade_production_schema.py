
import argparse
import re
from getpass import getpass

import certifi
import psycopg
from psycopg import sql

from app.migrations.upgrade_beta_schema import (
    TABLES,
    EVIDENCE_COLUMNS,
    EXPECTED_LEGACY_COLUMNS,
    qualified_table,
    get_columns,
    get_count,
    get_snapshot,
    get_constraints,
    migrate_file_roles,
    migrate_evidence,
    verify_new_values,
)


# ==========================================
# PRODUCTION DATABASE CONFIGURATION
# ==========================================

DATABASE = "unibrief"
USER = "unibrief_user"
PORT = 5432


# ==========================================
# PRODUCTION CONNECTION SAFETY
# ==========================================

def get_production_host():

    host = input(
        "Render External Database Host: "
    ).strip().lower()

    if not re.fullmatch(
        r"dpg-[a-z0-9-]+\.[a-z0-9-]+"
        r"-postgres\.render\.com",
        host,
    ):
        raise RuntimeError(
            "Invalid Render PostgreSQL hostname. "
            "Use the external hostname only."
        )

    return host


def verify_production_database(cursor):

    cursor.execute("""
        SELECT
            current_database(),
            current_user,
            host(inet_server_addr()),
            inet_server_port(),
            pg_is_in_recovery(),
            current_setting('transaction_read_only')
    """)

    (
        database,
        user,
        server_address,
        port,
        in_recovery,
        read_only,
    ) = cursor.fetchone()

    if (
        database != DATABASE
        or user != USER
        or port != PORT
        or not server_address
        or in_recovery
        or read_only != "off"
    ):
        raise RuntimeError(
            "Unexpected production database."
        )

    cursor.execute("""
        SELECT ssl
        FROM pg_stat_ssl
        WHERE pid = pg_backend_pid()
    """)

    ssl_status = cursor.fetchone()

    if not ssl_status or ssl_status[0] is not True:
        raise RuntimeError(
            "SSL connection is required."
        )

    print("Database:", database)
    print("User:", user)
    print("Port:", port)
    print("[PASS] Production database identity")
    print("[PASS] SSL connection")
    print("[PASS] Writable primary database")


# ==========================================
# PRODUCTION MIGRATION
# ==========================================

def migrate(apply=False):

    print("=" * 60)
    print("UNIBRIEF PRODUCTION MIGRATION")
    print("=" * 60)

    print(
        "Mode:",
        "COMMIT" if apply else "ROLLBACK TEST",
    )

    print("Database:", DATABASE)
    print("AI requests: DISABLED")
    print("R2 requests: DISABLED")

    backup_confirmation = input(
        "Fresh verified production backup available? "
        "Type BACKUP VERIFIED: "
    ).strip()

    if backup_confirmation != "BACKUP VERIFIED":
        raise RuntimeError(
            "Migration blocked: backup not confirmed."
        )

    host = get_production_host()

    print("\nTarget host:", host)
    print("Target database:", DATABASE)
    print("Target user:", USER)

    expected_confirmation = (
        f"APPLY {DATABASE} {host}"
        if apply
        else f"TEST {DATABASE} {host}"
    )

    print("\nType exactly:")
    print(expected_confirmation)

    confirmation = input(
        "Confirmation: "
    ).strip()

    if confirmation != expected_confirmation:
        raise RuntimeError(
            "Migration cancelled."
        )

    password = getpass(
        "Render PostgreSQL password: "
    )

    connection = psycopg.connect(
        host=host,
        port=PORT,
        dbname=DATABASE,
        user=USER,
        password=password,
        connect_timeout=10,
        sslmode="verify-full",
        sslrootcert=certifi.where(),
        application_name="unibrief_production_migration",
    )

    del password

    try:

        with connection.cursor() as cursor:

            verify_production_database(cursor)

            cursor.execute("""
                SET LOCAL lock_timeout = '5s'
            """)

            cursor.execute("""
                SET LOCAL statement_timeout = '60s'
            """)

            cursor.execute("""
                SET LOCAL
                    idle_in_transaction_session_timeout = '60s'
            """)

            # Protect all tables from concurrent
            # changes during migration verification.

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
            original_metadata = {}
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
                original_metadata[table] = columns

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

            total_records = sum(
                before_counts.values()
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

            print("\nTotal records:", total_records)
            print("Columns to add:", new_column_count)

            # ======================================
            # RUN VERIFIED MIGRATION FUNCTIONS
            # ======================================

            migrate_file_roles(cursor)
            migrate_evidence(cursor)

            # ======================================
            # VERIFY DATA AND SCHEMA PRESERVATION
            # ======================================

            print("\nDATA PRESERVATION")

            for table in TABLES:

                after_count = get_count(
                    cursor, table
                )

                if after_count != before_counts[table]:
                    raise RuntimeError(
                        f"Record count changed: {table}"
                    )

                after_snapshot = get_snapshot(
                    cursor,
                    table,
                    original_columns[table],
                )

                if after_snapshot != before_snapshots[table]:
                    raise RuntimeError(
                        f"Original data changed: {table}"
                    )

                current_columns = get_columns(
                    cursor, table
                )

                for column, metadata in (
                    original_metadata[table].items()
                ):

                    if current_columns.get(column) != metadata:
                        raise RuntimeError(
                            f"Original column changed: "
                            f"{table}.{column}"
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

            print("[PASS] Original column metadata")
            print("[PASS] Original constraints")

        # ==========================================
        # FINAL TRANSACTION DECISION
        # ==========================================

        if apply:

            connection.commit()

            print("\n" + "=" * 60)
            print("PRODUCTION MIGRATION COMPLETED")
            print("=" * 60)

        else:

            connection.rollback()

            print("\n" + "=" * 60)
            print("PRODUCTION ROLLBACK TEST COMPLETED")
            print("No migration changes saved.")
            print("=" * 60)

        print("Database safety: PASSED")
        print("SSL verification: PASSED")
        print("Schema verification: PASSED")
        print("Data preservation: PASSED")
        print("Constraint preservation: PASSED")
        print("Total records:", total_records)
        print("AI requests: 0")
        print("R2 requests: 0")

    except BaseException:

        try:

            connection.rollback()
            print("\nTransaction rollback requested.")

        except Exception:

            print(
                "\nRollback could not be confirmed. "
                "Verify database state before retrying."
            )

        print("MIGRATION FAILED")

        raise

    finally:

        connection.close()


# ==========================================
# COMMAND LINE INTERFACE
# ==========================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="UniBrief production migration"
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--rollback-test",
        action="store_true",
        help="Test migration without saving changes.",
    )

    mode.add_argument(
        "--apply",
        action="store_true",
        help="Commit production schema changes.",
    )

    args = parser.parse_args()

    migrate(apply=args.apply)
