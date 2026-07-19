import sqlite3
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import bcrypt


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
    def __init__(self, project_url: str = "", api_key: str = "") -> None:
        self.project_url = project_url
        self.api_key = api_key
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


class DatabaseService:
    def __init__(
        self,
        database_path: str = "budget.db",
        provider_name: str = "sqlite",
        provider_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        provider_config = provider_config or {}
        if provider_name == "sqlite":
            self.provider = SQLiteProvider(database_path)
        elif provider_name == "supabase":
            self.provider = SupabaseProvider(**provider_config)
        else:
            raise ValueError(f"Unsupported provider: {provider_name}")

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

        self._ensure_column("transactions", "user_id", "user_id INTEGER")
        self._ensure_column("notifications", "user_id", "user_id INTEGER")
        self.provider.commit()

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
        password_hash = self._hash_password(password)
        created_at = self._now()
        self.provider.execute(
            "INSERT INTO users (full_name, email, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?)",
            (full_name.strip(), email.lower().strip(), password_hash, created_at, role),
        )
        self.provider.commit()
        return int(self.provider.lastrowid())

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

    def update_user_avatar(self, user_id: int, avatar_url: str) -> None:
        self.provider.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (avatar_url, user_id))
        self.provider.commit()

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
            "SELECT users.full_name, users.email, household_members.role FROM household_members JOIN users ON users.id = household_members.user_id WHERE household_members.household_id = ?",
            (household_id,),
        )
        return list(self.provider.fetchall())

    def save_transaction(
        self,
        user_id: Optional[int],
        dato: str,
        kategori: str,
        beloeb: float,
        type_: str,
    ) -> int:
        if self.provider.has_column("transactions", "user_id"):
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
        return int(self.provider.lastrowid())

    def get_transactions(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        if self.provider.has_column("transactions", "user_id"):
            if user_id is None:
                self.provider.execute("SELECT * FROM transactions ORDER BY id DESC")
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

    def get_notifications(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        if self.provider.has_column("notifications", "user_id") and user_id is not None:
            self.provider.execute(
                "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT 8",
                (user_id,),
            )
        else:
            self.provider.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 8")
        return list(self.provider.fetchall())

    def save_notification(self, user_id: Optional[int], title: str, message: str, kind: str) -> None:
        if self.provider.has_column("notifications", "user_id"):
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
            if self.provider.has_column("notifications", "user_id"):
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

    def mark_all_notifications_read(self, user_id: Optional[int] = None) -> None:
        if self.provider.has_column("notifications", "user_id") and user_id is not None:
            self.provider.execute("UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))
        else:
            self.provider.execute("UPDATE notifications SET read = 1")
        self.provider.commit()

    def update_user_profile(self, user_id: int, full_name: str) -> None:
        self.provider.execute("UPDATE users SET full_name = ? WHERE id = ?", (full_name.strip(), user_id))
        self.provider.commit()

    def change_password(self, user_id: int, new_password: str) -> None:
        password_hash = self._hash_password(new_password)
        self.provider.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
        self.provider.commit()

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
        return int(self.provider.lastrowid())

    def get_savings_goals(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        if user_id is not None:
            self.provider.execute("SELECT * FROM savings_goals WHERE user_id = ? ORDER BY id DESC", (user_id,))
        else:
            self.provider.execute("SELECT * FROM savings_goals ORDER BY id DESC")
        return list(self.provider.fetchall())

    def create_subscription(
        self,
        user_id: Optional[int],
        name: str,
        amount: float,
        billing_date: Optional[str] = None,
        active: bool = True,
    ) -> int:
        self.provider.execute(
            "INSERT INTO subscriptions (user_id, name, amount, billing_date, active, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name.strip(), amount, billing_date, 1 if active else 0, self._now()),
        )
        self.provider.commit()
        return int(self.provider.lastrowid())

    def get_subscriptions(self, user_id: Optional[int] = None) -> List[sqlite3.Row]:
        if user_id is not None:
            self.provider.execute("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC", (user_id,))
        else:
            self.provider.execute("SELECT * FROM subscriptions ORDER BY id DESC")
        return list(self.provider.fetchall())

    def close(self) -> None:
        self.provider.close()
