import os
from typing import Dict


class ConfigError(RuntimeError):
    pass


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(
            f"Manglende miljøvariabel: {name}. "
            "Opret en .env fil baseret på .env.example eller sæt variablen i miljøet."
        )
    return value


def get_turso_database_url() -> str:
    return _require_env("TURSO_DATABASE_URL")


def get_turso_auth_token() -> str:
    return _require_env("TURSO_AUTH_TOKEN")


def get_turso_config() -> Dict[str, str]:
    return {
        "database_url": get_turso_database_url(),
        "auth_token": get_turso_auth_token(),
    }
