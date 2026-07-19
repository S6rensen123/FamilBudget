import argparse
import json
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from database_service import DatabaseService


UUID_TABLES = (
    "users",
    "households",
    "household_members",
    "transactions",
    "subscriptions",
    "savings_goals",
    "notifications",
    "sessions",
)

FK_RELATIONS: Tuple[Tuple[str, str, str, bool], ...] = (
    ("sessions", "user_id", "users", True),
    ("households", "owner_id", "users", False),
    ("household_members", "user_id", "users", True),
    ("household_members", "household_id", "households", True),
    ("transactions", "user_id", "users", False),
    ("transactions", "household_id", "households", False),
    ("subscriptions", "user_id", "users", False),
    ("subscriptions", "household_id", "households", False),
    ("savings_goals", "user_id", "users", False),
    ("savings_goals", "household_id", "households", False),
    ("notifications", "user_id", "users", False),
    ("notifications", "household_id", "households", False),
)


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    if not table_exists(conn, table_name):
        return []
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(row["name"]) for row in rows]


def row_count(conn: sqlite3.Connection, table_name: str) -> int:
    if not table_exists(conn, table_name):
        return 0
    row = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}").fetchone()
    return int(row["count"]) if row is not None else 0


def backup_database(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = database_path.with_name(f"{database_path.stem}.manual_uuid_backup_{timestamp}{database_path.suffix}")
    shutil.copy2(database_path, backup_path)
    return backup_path


def collect_orphaned_references(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    orphaned: List[Dict[str, Any]] = []
    parent_ids: Dict[str, set[str]] = {}
    for table_name in ("users", "households"):
        if not table_exists(conn, table_name):
            parent_ids[table_name] = set()
            continue
        rows = conn.execute(f"SELECT id FROM {table_name}").fetchall()
        parent_ids[table_name] = {str(row["id"]) for row in rows if row["id"] is not None}

    for table_name, column_name, parent_table, required in FK_RELATIONS:
        columns = table_columns(conn, table_name)
        if column_name not in columns:
            continue
        rows = conn.execute(f"SELECT id, {column_name} FROM {table_name}").fetchall()
        for row in rows:
            value = row[column_name]
            if value in (None, ""):
                continue
            if str(value) not in parent_ids[parent_table]:
                orphaned.append(
                    {
                        "table": table_name,
                        "row_id": str(row["id"]),
                        "column": column_name,
                        "missing_parent_table": parent_table,
                        "missing_parent_id": str(value),
                        "required": required,
                    }
                )
    return orphaned


def validate_uuid_columns(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    invalid_rows: List[Dict[str, Any]] = []
    for table_name in UUID_TABLES:
        if not table_exists(conn, table_name):
            continue
        columns = table_columns(conn, table_name)
        uuid_columns = ["id"]
        if "user_id" in columns:
            uuid_columns.append("user_id")
        if "household_id" in columns:
            uuid_columns.append("household_id")
        if "owner_id" in columns:
            uuid_columns.append("owner_id")
        select_columns = ", ".join(uuid_columns)
        for row in conn.execute(f"SELECT {select_columns} FROM {table_name}"):
            for column_name in uuid_columns:
                value = row[column_name]
                if value in (None, ""):
                    continue
                try:
                    uuid.UUID(str(value))
                except (ValueError, TypeError):
                    invalid_rows.append(
                        {
                            "table": table_name,
                            "column": column_name,
                            "value": str(value),
                        }
                    )
    return invalid_rows


def build_report(database_path: Path, backup_path: Path, pre_counts: Dict[str, int], orphaned_references: List[Dict[str, Any]]) -> Dict[str, Any]:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        migrated_rows: Dict[str, int] = {}
        if table_exists(conn, "id_migration_map"):
            rows = conn.execute(
                "SELECT table_name, COUNT(*) as count FROM id_migration_map GROUP BY table_name ORDER BY table_name"
            ).fetchall()
            migrated_rows = {str(row["table_name"]): int(row["count"]) for row in rows}

        failed_mappings: List[Dict[str, Any]] = []
        for table_name in UUID_TABLES:
            expected = pre_counts.get(table_name, 0)
            actual = migrated_rows.get(table_name, 0)
            if expected != actual:
                failed_mappings.append(
                    {
                        "table": table_name,
                        "expected_rows": expected,
                        "mapped_rows": actual,
                    }
                )

        invalid_uuid_values = validate_uuid_columns(conn)
        for invalid in invalid_uuid_values:
            failed_mappings.append(
                {
                    "table": invalid["table"],
                    "column": invalid["column"],
                    "invalid_uuid": invalid["value"],
                }
            )

        return {
            "database_path": str(database_path),
            "backup_path": str(backup_path),
            "migrated_rows": migrated_rows,
            "orphaned_references": orphaned_references,
            "failed_mappings": failed_mappings,
        }
    finally:
        conn.close()


def run_migration(database_path: Path) -> Dict[str, Any]:
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        pre_counts = {table_name: row_count(conn, table_name) for table_name in UUID_TABLES}
        orphaned_references = collect_orphaned_references(conn)
    finally:
        conn.close()

    backup_path = backup_database(database_path)
    service = DatabaseService(database_path=str(database_path))
    try:
        service_report = service.get_uuid_migration_report()
    finally:
        service.close()

    report = build_report(database_path, backup_path, pre_counts, orphaned_references)
    if service_report.get("backup_path") and not report["backup_path"]:
        report["backup_path"] = service_report["backup_path"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a FamilBudget SQLite database from INTEGER ids to UUID ids.")
    parser.add_argument("database", nargs="?", default="budget.db", help="Path to the SQLite database file.")
    parser.add_argument("--report", dest="report_path", default="", help="Optional path to write the JSON report.")
    args = parser.parse_args()

    database_path = Path(args.database).resolve()
    report = run_migration(database_path)
    report_json = json.dumps(report, indent=2, ensure_ascii=True)
    print(report_json)

    if args.report_path:
        report_path = Path(args.report_path).resolve()
        report_path.write_text(report_json + "\n", encoding="utf-8")

    return 0 if not report["failed_mappings"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
