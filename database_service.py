import sqlite3
import uuid
import os
import json
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

import bcrypt
from dotenv import load_dotenv
from config import get_supabase_desktop_config

load_dotenv()


class DatabaseProvider(ABC):
    @abstractmethod
    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> Any:
        raise NotImplementedError()

    @abstractmethod
    def fetchone(self) -> Optional[Any]:
        raise NotImplementedError()

    @abstractmethod
    def fetchall(self) -> List[Any]:
        raise NotImplementedError()

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    def lastrowid(self) -> int:
        raise NotImplementedError()

    @abstractmethod
    def has_column(self, table: str, column: str) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def table_exists(self, table: str) -> bool:
        raise NotImplementedError()


class SQLiteProvider(DatabaseProvider):
    def __init__(self, database_path: str = "budget.db") -> None:
        self.database_path = database_path
        self.conn = sqlite3.connect(self.database_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> Any:
        try:
            self.cursor.execute(query, params)
            return self.cursor
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite execute error: {exc}\nQuery: {query}\nParams: {params}") from exc

    def fetchone(self) -> Optional[Any]:
        try:
            return self.cursor.fetchone()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite fetchone error: {exc}") from exc

    def fetchall(self) -> List[Any]:
        try:
            return self.cursor.fetchall()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite fetchall error: {exc}") from exc

    def commit(self) -> None:
        try:
            self.conn.commit()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite commit error: {exc}") from exc

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite close error: {exc}") from exc

    def lastrowid(self) -> int:
        try:
            return self.cursor.lastrowid
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite lastrowid error: {exc}") from exc

    def table_exists(self, table: str) -> bool:
        try:
            self.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,))
            return self.fetchone() is not None
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite table_exists error: {exc}") from exc

    def has_column(self, table: str, column: str) -> bool:
        try:
            if not self.table_exists(table):
                return False
            self.execute(f"PRAGMA table_info({table})")
            return any(row["name"] == column for row in self.fetchall())
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"SQLite has_column error: {exc}") from exc


class SupabaseProvider(DatabaseProvider):
    def __init__(self, project_url: str = "", publishable_key: str = "", api_key: str = "") -> None:
        resolved_key = publishable_key or api_key
        if not project_url:
            raise RuntimeError("Supabase konfiguration mangler SUPABASE_URL.")
        if not resolved_key:
            raise RuntimeError("Supabase konfiguration mangler SUPABASE_PUBLISHABLE_KEY.")
        self.project_url = project_url
        self.publishable_key = resolved_key
        self.connected = False

    def _unsupported(self) -> None:
        raise RuntimeError("Supabase support is not configured in this build.")

    def execute(self, query: str, params: Tuple[Any, ...] = ()) -> Any:
        self._unsupported()

    def fetchone(self) -> Optional[Any]:
        self._unsupported()

    def fetchall(self) -> List[Any]:
        self._unsupported()

    def commit(self) -> None:
        self._unsupported()

    def close(self) -> None:
        self._unsupported()

    def lastrowid(self) -> int:
        self._unsupported()

    def has_column(self, table: str, column: str) -> bool:
        self._unsupported()

    def table_exists(self, table: str) -> bool:
        self._unsupported()


class SupabaseRestSyncTransport:
    def __init__(self, project_url: str, secret_key: Optional[str] = None, access_key: Optional[str] = None) -> None:
        self.project_url = project_url.rstrip("/")
        self.secret_key = secret_key.strip() if secret_key else ""
        self.access_key = access_key.strip() if access_key else ""

    def _headers(self) -> Dict[str, str]:
        key = self.secret_key or self.access_key
        if not self.project_url or not key:
            raise RuntimeError("Supabase sync transport mangler konfiguration.")
        return {
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def sync_item(self, table_name: str, row_id: Optional[str], operation: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.project_url:
            raise RuntimeError("Supabase URL mangler.")

        table = table_name.replace('"', "")
        url = f"{self.project_url}/rest/v1/{table}"
        headers = self._headers()

        def request(method: str, request_url: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
            print("[SYNC] URL:", request_url)
            try:
                data = None if body is None else json.dumps(body).encode("utf-8")
                req = urllib_request.Request(request_url, data=data, headers=headers, method=method)
                with urllib_request.urlopen(req, timeout=20) as response:
                    response_body = response.read().decode("utf-8", errors="replace")
                    print("[SYNC] Status:", response.status)
                    print("[SYNC] Body:", response_body)
                if not response_body.strip():
                    return {}
                parsed_body = json.loads(response_body)
                if isinstance(parsed_body, list):
                    return parsed_body[0] if parsed_body else {}
                if isinstance(parsed_body, dict):
                    return parsed_body
                return {}
            except urllib_error.HTTPError as exc:
                response_text = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
                print("[SYNC] Status:", exc.code)
                print("[SYNC] Body:", response_text)
                print("[SYNC ERROR]", str(exc))
                raise RuntimeError(f"Supabase sync request failed for {table_name}: {exc.code} {exc.reason}") from exc
            except urllib_error.URLError as exc:
                print("[SYNC] Body:", "")
                print("[SYNC ERROR]", str(exc))
                raise RuntimeError(f"Supabase sync request failed for {table_name}: {exc.reason}") from exc

        if operation == "insert":
            return request("POST", f"{url}?select=id", payload)
        elif operation == "update":
            if row_id is None:
                raise RuntimeError(f"Sync update mangler row_id for {table_name}.")
            return request("PATCH", f"{url}?id=eq.{row_id}&select=id", payload)
        elif operation == "delete":
            if row_id is None:
                raise RuntimeError(f"Sync delete mangler row_id for {table_name}.")
            return request("DELETE", f"{url}?id=eq.{row_id}&select=id")
        else:
            raise RuntimeError(f"Ukendt sync operation: {operation}")


class DatabaseService:
    SYNC_PRIORITY = {
        "users": 10,
        "households": 20,
        "household_members": 30,
        "transactions": 40,
        "subscriptions": 50,
        "savings_goals": 60,
        "notifications": 70,
    }
    SUPABASE_ALLOWED_COLUMNS = {
        "users": {"full_name", "email", "password_hash", "created_at", "role", "avatar_url"},
        "households": {"name", "owner_id", "invite_code", "created_at"},
        "household_members": {"household_id", "user_id", "role", "created_at"},
        "transactions": {"user_id", "household_id", "dato", "kategori", "beloeb", "type", "note", "created_at"},
        "notifications": {"user_id", "household_id", "title", "message", "kind", "read", "created_at"},
        "subscriptions": {"user_id", "household_id", "name", "amount", "billing_date", "active", "created_at"},
        "savings_goals": {"user_id", "household_id", "title", "target_amount", "current_amount", "due_date", "created_at"},
    }
    SUPABASE_FOREIGN_KEYS = {
        "households": {"owner_id": "users"},
        "household_members": {"household_id": "households", "user_id": "users"},
        "transactions": {"user_id": "users", "household_id": "households"},
        "notifications": {"user_id": "users", "household_id": "households"},
        "subscriptions": {"user_id": "users", "household_id": "households"},
        "savings_goals": {"user_id": "users", "household_id": "households"},
    }

    def __init__(
        self,
        database_path: str = "budget.db",
        provider_name: str = "sqlite",
        provider_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        print("[ENV] Current working directory:", os.getcwd())
        print("[ENV] .env exists:", Path(".env").exists())
        print("[ENV] SUPABASE_URL:", bool(os.getenv("SUPABASE_URL")))
        provider_config = provider_config or {}
        self.provider_name = provider_name
        if provider_name == "sqlite":
            self.provider = SQLiteProvider(database_path)
        elif provider_name == "supabase":
            if not provider_config:
                provider_config = get_supabase_desktop_config()
            if "secret_key" in provider_config or "SUPABASE_SECRET_KEY" in provider_config:
                raise RuntimeError(
                    "Desktop app må ikke bruge SUPABASE_SECRET_KEY. Brug kun SUPABASE_URL og SUPABASE_PUBLISHABLE_KEY."
                )
            self.provider = SupabaseProvider(**provider_config)
        else:
            raise ValueError(f"Unsupported provider: {provider_name}")

        supabase_url_loaded = bool(os.getenv("SUPABASE_URL", "").strip())
        current_provider = provider_name
        print("[DB] Provider:", current_provider)
        print("[DB] Supabase URL loaded:", supabase_url_loaded)
        self._sync_transport = None

        supabase_url = os.getenv("SUPABASE_URL", "").strip()
        publishable_key = os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        allow_secret_sync = os.getenv("SUPABASE_SYNC_ALLOW_SECRET", "").strip() == "1"
        secret_key = os.getenv("SUPABASE_SECRET_KEY", "").strip() if allow_secret_sync else ""
        if supabase_url and publishable_key:
            self._sync_transport = SupabaseRestSyncTransport(
                supabase_url,
                secret_key=secret_key,
                access_key=publishable_key,
            )
        print("[DB] Sync transport enabled:", self._sync_transport is not None)

        self.init_db()

    def _ensure_column(self, table: str, column_name: str, definition: str) -> None:
        if self.provider.has_column(table, column_name):
            return
        self.provider.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
        self.provider.commit()

    def _now(self) -> str:
        return datetime.now().isoformat(sep=" ", timespec="seconds")

    def init_db(self) -> None:
        self.provider.execute("PRAGMA foreign_keys = ON")

        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                avatar_url TEXT
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS households (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                owner_id INTEGER,
                invite_code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY(owner_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS household_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                household_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                dato TEXT,
                kategori TEXT,
                beloeb REAL,
                type TEXT
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                message TEXT,
                kind TEXT,
                read INTEGER DEFAULT 0,
                created_at TEXT
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS savings_goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                household_id INTEGER,
                title TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL NOT NULL DEFAULT 0,
                due_date TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
                FOREIGN KEY(household_id) REFERENCES households(id) ON DELETE CASCADE
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                amount REAL NOT NULL,
                billing_date TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                table_name TEXT NOT NULL,
                row_id INTEGER,
                operation TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                synced INTEGER NOT NULL DEFAULT 0,
                synced_at TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                last_error TEXT
            )
            """
        )
        self.provider.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_id_map (
                table_name TEXT NOT NULL,
                local_id INTEGER NOT NULL,
                remote_uuid TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (table_name, local_id)
            )
            """
        )

        self._ensure_column("transactions", "user_id", "user_id INTEGER")
        self._ensure_column("transactions", "household_id", "household_id INTEGER")
        self._ensure_column("notifications", "user_id", "user_id INTEGER")
        self._ensure_column("notifications", "household_id", "household_id INTEGER")
        self._ensure_column("subscriptions", "household_id", "household_id INTEGER")
        self._ensure_column("savings_goals", "household_id", "household_id INTEGER")
        self.provider.commit()

    def set_sync_transport(self, transport: Any) -> None:
        self._sync_transport = transport

    def enqueue_sync(self, table_name: str, row_id: Optional[int], operation: str, payload: Dict[str, Any]) -> int:
        self.provider.execute(
            "INSERT INTO sync_queue (table_name, row_id, operation, payload, created_at, synced) VALUES (?, ?, ?, ?, ?, 0)",
            (table_name, row_id, operation, json.dumps(payload, ensure_ascii=True), self._now()),
        )
        self.provider.commit()
        return int(self.provider.lastrowid())

    def _row_to_payload(self, row: Optional[sqlite3.Row]) -> Dict[str, Any]:
        if row is None:
            return {}
        return {key: row[key] for key in row.keys()}

    def _get_remote_uuid(self, table_name: str, local_id: Optional[int]) -> str:
        if local_id is None:
            return ""
        self.provider.execute(
            "SELECT remote_uuid FROM sync_id_map WHERE table_name = ? AND local_id = ?",
            (table_name, local_id),
        )
        row = self.provider.fetchone()
        return row["remote_uuid"] if row is not None else ""

    def _set_remote_uuid(self, table_name: str, local_id: Optional[int], remote_uuid: str) -> None:
        if local_id is None or not remote_uuid:
            return
        self.provider.execute(
            """
            INSERT INTO sync_id_map (table_name, local_id, remote_uuid, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(table_name, local_id)
            DO UPDATE SET remote_uuid = excluded.remote_uuid
            """,
            (table_name, local_id, remote_uuid, self._now()),
        )
        self.provider.commit()

    def _normalize_supabase_value(self, column_name: str, value: Any) -> Any:
        if value in ("", None):
            return None if value == "" else value
        if column_name in {"read", "active"}:
            return bool(value)
        return value

    def _map_supabase_foreign_key(self, table_name: str, column_name: str, value: Any) -> Any:
        if value in (None, ""):
            return None
        target_table = self.SUPABASE_FOREIGN_KEYS.get(table_name, {}).get(column_name)
        if target_table is None:
            return value
        remote_uuid = self._get_remote_uuid(target_table, int(value))
        if not remote_uuid:
            raise RuntimeError(
                f"Mangler remote UUID for {target_table}.{value} referenced by {table_name}.{column_name}"
            )
        return remote_uuid

    def _build_supabase_sync_item(
        self,
        table_name: str,
        row_id: Optional[int],
        operation: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        allowed_columns = self.SUPABASE_ALLOWED_COLUMNS.get(table_name)
        if allowed_columns is None:
            raise RuntimeError(f"Sync mapping mangler for tabel {table_name}")

        remote_row_id = self._get_remote_uuid(table_name, row_id)
        if operation == "delete" and not remote_row_id:
            return {"skip": True, "reason": "No remote UUID for delete", "operation": operation, "payload": {}, "remote_row_id": ""}

        mapped_payload: Dict[str, Any] = {}
        for column_name, raw_value in payload.items():
            if column_name not in allowed_columns:
                continue
            normalized_value = self._normalize_supabase_value(column_name, raw_value)
            mapped_payload[column_name] = self._map_supabase_foreign_key(table_name, column_name, normalized_value)

        if operation == "update" and not remote_row_id:
            operation = "insert"

        print("[SYNC] Payload after mapping:", json.dumps(mapped_payload, ensure_ascii=True, default=str))
        return {
            "skip": False,
            "operation": operation,
            "payload": mapped_payload,
            "remote_row_id": remote_row_id,
        }

    def get_sync_status(self) -> Dict[str, Any]:
        self.provider.execute("SELECT COUNT(*) as count FROM sync_queue WHERE synced = 0")
        pending_row = self.provider.fetchone()
        pending = int(pending_row["count"]) if pending_row is not None else 0

        self.provider.execute(
            "SELECT synced_at FROM sync_queue WHERE synced = 1 ORDER BY synced_at DESC, id DESC LIMIT 1"
        )
        last_row = self.provider.fetchone()
        return {
            "pending": pending,
            "last_synced_at": last_row["synced_at"] if last_row is not None else "",
            "has_transport": self._sync_transport is not None,
        }

    def _fetch_pending_sync_items(self, limit: int = 25) -> List[sqlite3.Row]:
        self.provider.execute(
            "SELECT * FROM sync_queue WHERE synced = 0 ORDER BY id ASC LIMIT ?",
            (limit,),
        )
        return list(self.provider.fetchall())

    def get_sync_debug_report(self, limit: int = 50) -> Dict[str, Any]:
        self.provider.execute("SELECT COUNT(*) as count FROM sync_queue WHERE synced = 0")
        pending_row = self.provider.fetchone()
        pending_count = int(pending_row["count"]) if pending_row is not None else 0

        self.provider.execute("SELECT COUNT(*) as count FROM sync_queue WHERE synced = 1")
        synced_row = self.provider.fetchone()
        synced_count = int(synced_row["count"]) if synced_row is not None else 0

        self.provider.execute("SELECT COUNT(*) as count FROM sync_queue WHERE synced = 0 AND retry_count > 0")
        failed_row = self.provider.fetchone()
        failed_count = int(failed_row["count"]) if failed_row is not None else 0

        self.provider.execute(
            "SELECT synced_at FROM sync_queue WHERE synced = 1 ORDER BY synced_at DESC, id DESC LIMIT 1"
        )
        last_synced_row = self.provider.fetchone()
        last_sync_time = last_synced_row["synced_at"] if last_synced_row is not None else ""

        self.provider.execute(
            "SELECT last_error FROM sync_queue WHERE last_error IS NOT NULL AND last_error != '' ORDER BY id DESC LIMIT 1"
        )
        last_error_row = self.provider.fetchone()
        last_error = last_error_row["last_error"] if last_error_row is not None else ""

        self.provider.execute(
            "SELECT * FROM sync_queue ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        items = []
        for row in self.provider.fetchall():
            payload = row["payload"] if "payload" in row.keys() else ""
            items.append(
                {
                    "id": int(row["id"]),
                    "table_name": row["table_name"],
                    "row_id": row["row_id"],
                    "operation": row["operation"],
                    "synced": int(row["synced"]),
                    "retry_count": int(row["retry_count"]) if "retry_count" in row.keys() else 0,
                    "last_error": row["last_error"] if "last_error" in row.keys() else "",
                    "created_at": row["created_at"],
                    "synced_at": row["synced_at"] if "synced_at" in row.keys() else "",
                    "payload": payload,
                }
            )

        return {
            "pending_count": pending_count,
            "synced_count": synced_count,
            "failed_count": failed_count,
            "last_sync_time": last_sync_time,
            "last_error": last_error,
            "items": items,
        }

    def mark_sync_item_synced(self, queue_id: int) -> None:
        self.provider.execute(
            "UPDATE sync_queue SET synced = 1, synced_at = ?, last_error = NULL WHERE id = ?",
            (self._now(), queue_id),
        )
        self.provider.commit()

    def mark_sync_item_failed(self, queue_id: int, error_message: str) -> None:
        self.provider.execute(
            "UPDATE sync_queue SET retry_count = retry_count + 1, last_error = ? WHERE id = ?",
            (error_message[:500], queue_id),
        )
        self.provider.commit()

    def process_sync_queue(self, limit: int = 25) -> Dict[str, Any]:
        items = self._fetch_pending_sync_items(limit=limit)
        items.sort(key=lambda row: (self.SYNC_PRIORITY.get(row["table_name"], 999), int(row["id"])))
        pending_count = len(items)
        print("[SYNC] Pending:", pending_count)
        if not items:
            return {"processed": 0, "synced": 0, "failed": 0, "last_error": "", "last_synced_at": self.get_sync_status()["last_synced_at"], "pending_count": pending_count}

        if self._sync_transport is None:
            error_text = "No sync transport configured"
            print("[SYNC ERROR]", error_text)
            return {"processed": len(items), "synced": 0, "failed": len(items), "last_error": error_text, "last_synced_at": self.get_sync_status()["last_synced_at"], "pending_count": pending_count}

        processed = 0
        synced = 0
        failed = 0
        last_error = ""
        last_synced_at = self.get_sync_status()["last_synced_at"]

        for item in items:
            processed += 1
            try:
                print("[SYNC] Table:", item["table_name"])
                print("[SYNC] Row:", item["row_id"])
                payload = json.loads(item["payload"])
                sync_item = self._build_supabase_sync_item(
                    table_name=item["table_name"],
                    row_id=item["row_id"],
                    operation=item["operation"],
                    payload=payload,
                )
                if sync_item["skip"]:
                    self.mark_sync_item_synced(int(item["id"]))
                    synced += 1
                    continue
                response_payload = self._sync_transport.sync_item(
                    table_name=item["table_name"],
                    row_id=sync_item["remote_row_id"] or None,
                    operation=sync_item["operation"],
                    payload=sync_item["payload"],
                )
                remote_uuid = response_payload.get("id", "") if isinstance(response_payload, dict) else ""
                if remote_uuid:
                    self._set_remote_uuid(item["table_name"], item["row_id"], str(remote_uuid))
                self.mark_sync_item_synced(int(item["id"]))
                synced += 1
                last_synced_at = self._now()
            except Exception as exc:
                failed += 1
                last_error = str(exc)
                print("[SYNC ERROR]", str(exc))
                self.mark_sync_item_failed(int(item["id"]), last_error)
        print("[SYNC] Synced:", synced)
        print("[SYNC] Last error:", last_error)
        return {
            "processed": processed,
            "synced": synced,
            "failed": failed,
            "last_error": last_error,
            "last_synced_at": last_synced_at,
            "pending_count": pending_count,
        }

    def get_setting(self, key: str, default: str = "") -> str:
        self.provider.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = self.provider.fetchone()
        return row["value"] if row else default

    def save_setting(self, key: str, value: str) -> None:
        self.provider.execute(
            "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.provider.commit()

    def _hash_password(self, password: str) -> str:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return hashed.decode("utf-8")

    def _verify_password(self, password: str, password_hash: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

    def get_user_by_email(self, email: str) -> Optional[sqlite3.Row]:
        self.provider.execute("SELECT * FROM users WHERE email = ?", (email.lower().strip(),))
        return self.provider.fetchone()

    def get_user_by_id(self, user_id: int) -> Optional[sqlite3.Row]:
        self.provider.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return self.provider.fetchone()

    def count_users(self) -> int:
        self.provider.execute("SELECT COUNT(*) as count FROM users")
        row = self.provider.fetchone()
        return int(row["count"]) if row else 0

    def create_user(self, full_name: str, email: str, password: str, role: str = "user") -> int:
        print(f"[DB] create_user called via {self.provider.__class__.__name__}")
        password_hash = self._hash_password(password)
        created_at = self._now()
        self.provider.execute(
            "INSERT INTO users (full_name, email, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?)",
            (full_name.strip(), email.lower().strip(), password_hash, created_at, role),
        )
        self.provider.commit()
        user_id = int(self.provider.lastrowid())
        self.enqueue_sync("users", user_id, "insert", self._row_to_payload(self.get_user_by_id(user_id)))
        return user_id

    def login_user(self, email: str, password: str) -> Optional[sqlite3.Row]:
        user = self.get_user_by_email(email)
        if user is None:
            return None
        if not self._verify_password(password, user["password_hash"]):
            return None
        self.provider.execute(
            "UPDATE users SET last_login = ? WHERE id = ?",
            (self._now(), user["id"]),
        )
        self.provider.commit()
        self.enqueue_sync("users", int(user["id"]), "update", self._row_to_payload(self.get_user_by_id(int(user["id"]))))
        return self.get_user_by_id(user["id"])

    def create_session(self, user_id: int, expires_in_hours: int = 30) -> str:
        token = uuid.uuid4().hex
        created_at = self._now()
        expires_at = (datetime.now() + timedelta(hours=expires_in_hours)).isoformat(sep=" ", timespec="seconds")
        self.provider.execute(
            "INSERT INTO sessions (user_id, token, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (user_id, token, created_at, expires_at),
        )
        self.provider.commit()
        return token

    def validate_session(self, token: str) -> Optional[sqlite3.Row]:
        if not token:
            return None
        self.provider.execute(
            "SELECT sessions.user_id FROM sessions WHERE token = ? AND expires_at > ?",
            (token, self._now()),
        )
        row = self.provider.fetchone()
        if row is None:
            return None
        user_id = row["user_id"]
        return self.get_user_by_id(user_id)

    def logout_session(self, token: str) -> None:
        self.provider.execute("DELETE FROM sessions WHERE token = ?", (token,))
        self.provider.commit()

    def logout_user(self, token: str) -> None:
        self.logout_session(token)

    def update_user_email(self, user_id: int, email: str) -> None:
        self.provider.execute("UPDATE users SET email = ? WHERE id = ?", (email.lower().strip(), user_id))
        self.provider.commit()
        self.enqueue_sync("users", user_id, "update", self._row_to_payload(self.get_user_by_id(user_id)))

    def update_user_avatar(self, user_id: int, avatar_url: str) -> None:
        self.provider.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, user_id))
        self.provider.commit()
        self.enqueue_sync("users", user_id, "update", self._row_to_payload(self.get_user_by_id(user_id)))

    def _generate_invite_code(self) -> str:
        return uuid.uuid4().hex[:8].upper()

    def create_household(self, name: str, owner_id: int) -> Tuple[int, str]:
        invite_code = self._generate_invite_code()
        created_at = self._now()
        self.provider.execute(
            "INSERT INTO households (name, owner_id, invite_code, created_at) VALUES (?, ?, ?, ?)",
            (name.strip(), owner_id, invite_code, created_at),
        )
        household_id = int(self.provider.lastrowid())
        self.add_household_member(household_id, owner_id, "owner")
        self.provider.commit()
        self.enqueue_sync("households", household_id, "insert", self._row_to_payload(self.get_household_by_code(invite_code)))
        return household_id, invite_code

    def add_household_member(self, household_id: int, user_id: int, role: str = "member") -> None:
        self.provider.execute(
            "SELECT id FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, user_id),
        )
        if self.provider.fetchone() is not None:
            return
        self.provider.execute(
            "INSERT INTO household_members (household_id, user_id, role) VALUES (?, ?, ?)",
            (household_id, user_id, role),
        )
        self.provider.commit()
        self.provider.execute(
            "SELECT * FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, user_id),
        )
        member_row = self.provider.fetchone()
        self.enqueue_sync("household_members", int(member_row["id"]) if member_row is not None else None, "insert", self._row_to_payload(member_row))

    def get_household_by_code(self, invite_code: str) -> Optional[sqlite3.Row]:
        self.provider.execute("SELECT * FROM households WHERE invite_code = ?", (invite_code.strip().upper(),))
        return self.provider.fetchone()

    def regenerate_household_invite_code(self, household_id: int) -> str:
        invite_code = self._generate_invite_code()
        self.provider.execute(
            "UPDATE households SET invite_code = ? WHERE id = ?",
            (invite_code, household_id),
        )
        self.provider.commit()
        self.enqueue_sync("households", household_id, "update", self._row_to_payload(self.get_household_by_code(invite_code)))
        return invite_code

    def join_household(self, user_id: int, invite_code: str) -> bool:
        household = self.get_household_by_code(invite_code)
        if household is None:
            return False
        self.add_household_member(household["id"], user_id, "member")
        return True

    def get_household_for_user(self, user_id: int) -> Optional[sqlite3.Row]:
        self.provider.execute(
            "SELECT households.* FROM households JOIN household_members ON household_members.household_id = households.id WHERE household_members.user_id = ? LIMIT 1",
            (user_id,),
        )
        return self.provider.fetchone()

    def is_user_in_household(self, user_id: int) -> bool:
        return self.get_household_for_user(user_id) is not None

    def get_households_for_user(self, user_id: int) -> List[sqlite3.Row]:
        self.provider.execute(
            "SELECT households.* FROM households JOIN household_members ON household_members.household_id = households.id WHERE household_members.user_id = ?",
            (user_id,),
        )
        return list(self.provider.fetchall())

    def get_household_members(self, household_id: int) -> List[sqlite3.Row]:
        self.provider.execute(
            "SELECT users.id as user_id, users.full_name, users.email, household_members.role FROM household_members JOIN users ON users.id = household_members.user_id WHERE household_members.household_id = ?",
            (household_id,),
        )
        return list(self.provider.fetchall())

    def get_household_member_role(self, household_id: int, user_id: int) -> Optional[str]:
        self.provider.execute(
            "SELECT role FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, user_id),
        )
        row = self.provider.fetchone()
        return str(row["role"]) if row is not None else None

    def is_household_admin(self, household_id: int, user_id: int) -> bool:
        role = self.get_household_member_role(household_id, user_id)
        return role in ("owner", "admin")

    def change_household_member_role(self, household_id: int, target_user_id: int, new_role: str) -> None:
        self.provider.execute(
            "UPDATE household_members SET role = ? WHERE household_id = ? AND user_id = ?",
            (new_role, household_id, target_user_id),
        )
        self.provider.commit()
        self.provider.execute(
            "SELECT * FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, target_user_id),
        )
        member_row = self.provider.fetchone()
        self.enqueue_sync("household_members", int(member_row["id"]) if member_row is not None else None, "update", self._row_to_payload(member_row))

    def remove_household_member(self, household_id: int, target_user_id: int) -> None:
        self.provider.execute(
            "SELECT * FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, target_user_id),
        )
        payload_row = self.provider.fetchone()
        self.provider.execute(
            "DELETE FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, target_user_id),
        )
        self.provider.commit()
        self.enqueue_sync("household_members", None, "delete", self._row_to_payload(payload_row))

    def leave_household(self, household_id: int, user_id: int) -> None:
        self.provider.execute("SELECT owner_id FROM households WHERE id = ?", (household_id,))
        household = self.provider.fetchone()
        if household is None:
            return

        owner_id = household["owner_id"]
        self.remove_household_member(household_id, user_id)
        if owner_id != user_id:
            return

        self.provider.execute(
            "SELECT user_id FROM household_members WHERE household_id = ? ORDER BY id ASC LIMIT 1",
            (household_id,),
        )
        next_owner = self.provider.fetchone()
        if next_owner is None:
            self.delete_household(household_id)
            return

        new_owner_id = next_owner["user_id"]
        self.provider.execute(
            "UPDATE households SET owner_id = ? WHERE id = ?",
            (new_owner_id, household_id),
        )
        self.provider.execute(
            "UPDATE household_members SET role = 'owner' WHERE household_id = ? AND user_id = ?",
            (household_id, new_owner_id),
        )
        self.provider.commit()
        self.provider.execute("SELECT * FROM households WHERE id = ?", (household_id,))
        self.enqueue_sync("households", household_id, "update", self._row_to_payload(self.provider.fetchone()))
        self.provider.execute(
            "SELECT * FROM household_members WHERE household_id = ? AND user_id = ?",
            (household_id, new_owner_id),
        )
        owner_member_row = self.provider.fetchone()
        self.enqueue_sync("household_members", int(owner_member_row["id"]) if owner_member_row is not None else None, "update", self._row_to_payload(owner_member_row))

    def delete_household(self, household_id: int) -> None:
        self.provider.execute("SELECT * FROM households WHERE id = ?", (household_id,))
        payload_row = self.provider.fetchone()
        self.provider.execute("DELETE FROM households WHERE id = ?", (household_id,))
        self.provider.commit()
        self.enqueue_sync("households", household_id, "delete", self._row_to_payload(payload_row))

    def get_household_financial_summary(self, household_id: int) -> Dict[str, Any]:
        self.provider.execute(
            "SELECT user_id FROM household_members WHERE household_id = ?",
            (household_id,),
        )
        member_rows = list(self.provider.fetchall())
        member_ids = [int(row["user_id"]) for row in member_rows]
        member_placeholders = ",".join("?" for _ in member_ids)
        member_clause = f"user_id IN ({member_placeholders})" if member_ids else "0=1"

        self.provider.execute(
            f"SELECT type, beloeb FROM transactions WHERE household_id = ? OR {member_clause}",
            (household_id, *member_ids),
        )
        tx_rows = list(self.provider.fetchall())
        income = sum(float(row["beloeb"]) for row in tx_rows if row["type"] == "Indtægt")
        expense = sum(float(row["beloeb"]) for row in tx_rows if row["type"] != "Indtægt")
        balance = income - expense

        self.provider.execute(
            f"SELECT current_amount FROM savings_goals WHERE household_id = ? OR {member_clause}",
            (household_id, *member_ids),
        )
        savings_rows = list(self.provider.fetchall())
        household_savings = sum(float(row["current_amount"]) for row in savings_rows)

        self.provider.execute(
            f"SELECT amount FROM subscriptions WHERE active = 1 AND (household_id = ? OR {member_clause})",
            (household_id, *member_ids),
        )
        sub_rows = list(self.provider.fetchall())
        household_subscriptions = sum(float(row["amount"]) for row in sub_rows)

        self.provider.execute(
            "SELECT COUNT(*) as count FROM household_members WHERE household_id = ?",
            (household_id,),
        )
        count_row = self.provider.fetchone()
        member_count = int(count_row["count"]) if count_row is not None else 0

        return {
            "balance": balance,
            "income": income,
            "expense": expense,
            "savings": household_savings,
            "subscriptions": household_subscriptions,
            "member_count": member_count,
        }

    def get_household_family_analysis(self, household_id: int) -> Dict[str, Any]:
        self.provider.execute(
            "SELECT user_id FROM household_members WHERE household_id = ?",
            (household_id,),
        )
        member_rows = list(self.provider.fetchall())
        member_ids = [int(row["user_id"]) for row in member_rows]
        member_placeholders = ",".join("?" for _ in member_ids)
        member_clause = f"user_id IN ({member_placeholders})" if member_ids else "0=1"

        self.provider.execute(
            f"SELECT kategori, type, beloeb FROM transactions WHERE household_id = ? OR {member_clause}",
            (household_id, *member_ids),
        )
        tx_rows = list(self.provider.fetchall())
        expense_totals: Dict[str, float] = {}
        for row in tx_rows:
            if row["type"] == "Indtægt":
                continue
            kategori = str(row["kategori"])
            expense_totals[kategori] = expense_totals.get(kategori, 0.0) + float(row["beloeb"])

        largest_category = "Ingen kategori"
        if expense_totals:
            largest_category = max(expense_totals.items(), key=lambda item: item[1])[0]

        self.provider.execute(
            f"SELECT name, amount FROM subscriptions WHERE active = 1 AND (household_id = ? OR {member_clause})",
            (household_id, *member_ids),
        )
        sub_rows = list(self.provider.fetchall())
        largest_subscription_name = "Ingen abonnement"
        largest_subscription_amount = 0.0
        if sub_rows:
            largest_sub = max(sub_rows, key=lambda row: float(row["amount"]))
            largest_subscription_name = str(largest_sub["name"])
            largest_subscription_amount = float(largest_sub["amount"])

        summary = self.get_household_financial_summary(household_id)
        health_score = int(
            max(
                0,
                min(
                    100,
                    round(
                        100
                        * (
                            0.55 * (1.0 - (summary["expense"] / max(summary["income"], 1.0)))
                            + 0.25 * (summary["savings"] / max(summary["income"], 1.0))
                            + 0.20 * (1.0 - (summary["subscriptions"] / max(summary["income"], 1.0)))
                            + (0.15 if summary["balance"] > 0 else 0.0)
                        )
                    ),
                ),
            )
        )

        return {
            "largest_category": largest_category,
            "largest_subscription_name": largest_subscription_name,
            "largest_subscription_amount": largest_subscription_amount,
            "potential_savings": summary["subscriptions"] * 0.25,
            "health_score": health_score,
        }

    def save_transaction(
        self,
        user_id: Optional[int],
        dato: str,
        kategori: str,
        beloeb: float,
        type_: str,
        household_id: Optional[int] = None,
    ) -> int:
        has_user = self.provider.has_column("transactions", "user_id")
        has_household = self.provider.has_column("transactions", "household_id")
        if has_user and has_household:
            self.provider.execute(
                "INSERT INTO transactions (user_id, household_id, dato, kategori, beloeb, type) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, household_id, dato, kategori.strip(), beloeb, type_.strip()),
            )
        elif has_user:
            self.provider.execute(
                "INSERT INTO transactions (user_id, dato, kategori, beloeb, type) VALUES (?, ?, ?, ?, ?)",
                (user_id, dato, kategori.strip(), beloeb, type_.strip()),
            )
        else:
            self.provider.execute(
                "INSERT INTO transactions (dato, kategori, beloeb, type) VALUES (?, ?, ?, ?)",
                (dato, kategori.strip(), beloeb, type_.strip()),
            )
        self.provider.commit()
        row_id = int(self.provider.lastrowid())
        self.provider.execute("SELECT * FROM transactions WHERE id = ?", (row_id,))
        self.enqueue_sync("transactions", row_id, "insert", self._row_to_payload(self.provider.fetchone()))
        return row_id

    def get_transactions(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        has_user = self.provider.has_column("transactions", "user_id")
        has_household = self.provider.has_column("transactions", "household_id")
        if has_user:
            if user_id is None:
                self.provider.execute("SELECT * FROM transactions ORDER BY id DESC")
            elif has_household:
                household = self.get_household_for_user(user_id)
                if household is None:
                    self.provider.execute(
                        "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC",
                        (user_id,),
                    )
                else:
                    self.provider.execute(
                        "SELECT * FROM transactions WHERE user_id = ? OR household_id = ? ORDER BY id DESC",
                        (user_id, household["id"]),
                    )
            else:
                self.provider.execute(
                    "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC",
                    (user_id,),
                )
        else:
            self.provider.execute("SELECT * FROM transactions ORDER BY id DESC")
        return list(self.provider.fetchall())

    def load_transactions(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        return self.get_transactions(user_id)

    def update_transaction(
        self,
        transaction_id: int,
        dato: str,
        kategori: str,
        beloeb: float,
        type_: str,
        household_id: Optional[int] = None,
    ) -> None:
        if self.provider.has_column("transactions", "household_id"):
            self.provider.execute(
                "UPDATE transactions SET dato = ?, kategori = ?, beloeb = ?, type = ?, household_id = ? WHERE id = ?",
                (dato, kategori.strip(), beloeb, type_.strip(), household_id, transaction_id),
            )
        else:
            self.provider.execute(
                "UPDATE transactions SET dato = ?, kategori = ?, beloeb = ?, type = ? WHERE id = ?",
                (dato, kategori.strip(), beloeb, type_.strip(), transaction_id),
            )
        self.provider.commit()
        self.provider.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        self.enqueue_sync("transactions", transaction_id, "update", self._row_to_payload(self.provider.fetchone()))

    def delete_transaction(self, transaction_id: int) -> None:
        self.provider.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        payload_row = self.provider.fetchone()
        self.provider.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        self.provider.commit()
        self.enqueue_sync("transactions", transaction_id, "delete", self._row_to_payload(payload_row))

    def get_notifications(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        has_user = self.provider.has_column("notifications", "user_id")
        has_household = self.provider.has_column("notifications", "household_id")
        if has_user and user_id is not None:
            if has_household:
                household = self.get_household_for_user(user_id)
                if household is None:
                    self.provider.execute(
                        "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 8",
                        (user_id,),
                    )
                else:
                    self.provider.execute(
                        "SELECT * FROM notifications WHERE user_id = ? OR household_id = ? ORDER BY id DESC LIMIT 8",
                        (user_id, household["id"]),
                    )
            else:
                self.provider.execute(
                    "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 8",
                    (user_id,),
                )
        else:
            self.provider.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 8")
        return list(self.provider.fetchall())

    def save_notification(
        self,
        user_id: Optional[int],
        title: str,
        message: str,
        kind: str,
        household_id: Optional[int] = None,
    ) -> None:
        has_user = self.provider.has_column("notifications", "user_id")
        has_household = self.provider.has_column("notifications", "household_id")
        if has_user and has_household:
            self.provider.execute(
                "SELECT id FROM notifications WHERE user_id = ? AND ((household_id = ?) OR (household_id IS NULL AND ? IS NULL)) AND title = ? AND message = ?",
                (user_id, household_id, household_id, title, message),
            )
            exists = self.provider.fetchone() is not None
        elif has_user:
            self.provider.execute(
                "SELECT id FROM notifications WHERE user_id = ? AND title = ? AND message = ?",
                (user_id, title, message),
            )
            exists = self.provider.fetchone() is not None
        else:
            self.provider.execute(
                "SELECT id FROM notifications WHERE title = ? AND message = ?",
                (title, message),
            )
            exists = self.provider.fetchone() is not None

        if not exists:
            if has_user and has_household:
                self.provider.execute(
                    "INSERT INTO notifications (user_id, household_id, title, message, kind, read, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, household_id, title, message, kind, 0, self._now()),
                )
            elif has_user:
                self.provider.execute(
                    "INSERT INTO notifications (user_id, title, message, kind, read, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, title, message, kind, 0, self._now()),
                )
            else:
                self.provider.execute(
                    "INSERT INTO notifications (title, message, kind, read, created_at) VALUES (?, ?, ?, ?, ?)",
                    (title, message, kind, 0, self._now()),
                )
            self.provider.commit()
            if has_user and user_id is not None:
                self.provider.execute(
                    "SELECT * FROM notifications WHERE user_id = ? AND title = ? AND message = ? ORDER BY id DESC LIMIT 1",
                    (user_id, title, message),
                )
                notif_row = self.provider.fetchone()
                self.enqueue_sync("notifications", int(notif_row["id"]) if notif_row is not None else None, "insert", self._row_to_payload(notif_row))

    def mark_all_notifications_read(self, user_id: Optional[int] = None) -> None:
        if self.provider.has_column("notifications", "user_id") and user_id is not None:
            self.provider.execute("SELECT * FROM notifications WHERE user_id = ? AND read = 0", (user_id,))
            unread_rows = list(self.provider.fetchall())
            self.provider.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))
            for unread_row in unread_rows:
                self.enqueue_sync("notifications", int(unread_row["id"]), "update", {**self._row_to_payload(unread_row), "read": 1})
        else:
            self.provider.execute("UPDATE notifications SET read = 1")
        self.provider.commit()

    def update_user_profile(self, user_id: int, full_name: str) -> None:
        self.provider.execute("UPDATE users SET full_name = ? WHERE id = ?", (full_name.strip(), user_id))
        self.provider.commit()
        self.enqueue_sync("users", user_id, "update", self._row_to_payload(self.get_user_by_id(user_id)))

    def change_password(self, user_id: int, new_password: str) -> None:
        password_hash = self._hash_password(new_password)
        self.provider.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        self.provider.commit()
        self.enqueue_sync("users", user_id, "update", self._row_to_payload(self.get_user_by_id(user_id)))

    def create_savings_goal(
        self,
        user_id: Optional[int],
        title: str,
        target_amount: float,
        due_date: Optional[str] = None,
        household_id: Optional[int] = None,
    ) -> int:
        self.provider.execute(
            "INSERT INTO savings_goals (user_id, household_id, title, target_amount, current_amount, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, household_id, title.strip(), target_amount, 0.0, due_date, self._now()),
        )
        self.provider.commit()
        goal_id = int(self.provider.lastrowid())
        self.provider.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        self.enqueue_sync("savings_goals", goal_id, "insert", self._row_to_payload(self.provider.fetchone()))
        return goal_id

    def get_savings_goals(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        if user_id is not None:
            household = self.get_household_for_user(user_id)
            if household is None:
                self.provider.execute("SELECT * FROM savings_goals WHERE user_id = ? ORDER BY id DESC", (user_id,))
            else:
                self.provider.execute(
                    "SELECT * FROM savings_goals WHERE user_id = ? OR household_id = ? ORDER BY id DESC",
                    (user_id, household["id"]),
                )
        else:
            self.provider.execute("SELECT * FROM savings_goals ORDER BY id DESC")
        return list(self.provider.fetchall())

    def update_savings_goal(
        self,
        goal_id: int,
        title: str,
        target_amount: float,
        current_amount: float,
        due_date: Optional[str] = None,
        household_id: Optional[int] = None,
    ) -> None:
        self.provider.execute(
            "UPDATE savings_goals SET title = ?, target_amount = ?, current_amount = ?, due_date = ?, household_id = ? WHERE id = ?",
            (title.strip(), target_amount, current_amount, due_date, household_id, goal_id),
        )
        self.provider.commit()
        self.provider.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        self.enqueue_sync("savings_goals", goal_id, "update", self._row_to_payload(self.provider.fetchone()))

    def delete_savings_goal(self, goal_id: int) -> None:
        self.provider.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        payload_row = self.provider.fetchone()
        self.provider.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
        self.provider.commit()
        self.enqueue_sync("savings_goals", goal_id, "delete", self._row_to_payload(payload_row))

    def create_subscription(
        self,
        user_id: Optional[int],
        name: str,
        amount: float,
        billing_date: Optional[str] = None,
        active: bool = True,
        household_id: Optional[int] = None,
    ) -> int:
        if self.provider.has_column("subscriptions", "household_id"):
            self.provider.execute(
                "INSERT INTO subscriptions (user_id, household_id, name, amount, billing_date, active, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, household_id, name.strip(), amount, billing_date, 1 if active else 0, self._now()),
            )
        else:
            self.provider.execute(
                "INSERT INTO subscriptions (user_id, name, amount, billing_date, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, name.strip(), amount, billing_date, 1 if active else 0, self._now()),
            )
        self.provider.commit()
        subscription_id = int(self.provider.lastrowid())
        self.provider.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,))
        self.enqueue_sync("subscriptions", subscription_id, "insert", self._row_to_payload(self.provider.fetchone()))
        return subscription_id

    def get_subscriptions(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        has_household = self.provider.has_column("subscriptions", "household_id")
        if user_id is not None:
            if has_household:
                household = self.get_household_for_user(user_id)
                if household is None:
                    self.provider.execute("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC", (user_id,))
                else:
                    self.provider.execute(
                        "SELECT * FROM subscriptions WHERE user_id = ? OR household_id = ? ORDER BY id DESC",
                        (user_id, household["id"]),
                    )
            else:
                self.provider.execute("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC", (user_id,))
        else:
            self.provider.execute("SELECT * FROM subscriptions ORDER BY id DESC")
        return list(self.provider.fetchall())

    def update_subscription(
        self,
        subscription_id: int,
        name: str,
        amount: float,
        billing_date: Optional[str] = None,
        active: bool = True,
        household_id: Optional[int] = None,
    ) -> None:
        if self.provider.has_column("subscriptions", "household_id"):
            self.provider.execute(
                "UPDATE subscriptions SET name = ?, amount = ?, billing_date = ?, active = ?, household_id = ? WHERE id = ?",
                (name.strip(), amount, billing_date, 1 if active else 0, household_id, subscription_id),
            )
        else:
            self.provider.execute(
                "UPDATE subscriptions SET name = ?, amount = ?, billing_date = ?, active = ? WHERE id = ?",
                (name.strip(), amount, billing_date, 1 if active else 0, subscription_id),
            )
        self.provider.commit()
        self.provider.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,))
        self.enqueue_sync("subscriptions", subscription_id, "update", self._row_to_payload(self.provider.fetchone()))

    def delete_subscription(self, subscription_id: int) -> None:
        self.provider.execute("SELECT * FROM subscriptions WHERE id = ?", (subscription_id,))
        payload_row = self.provider.fetchone()
        self.provider.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
        self.provider.commit()
        self.enqueue_sync("subscriptions", subscription_id, "delete", self._row_to_payload(payload_row))

    def close(self) -> None:
        self.provider.close()
