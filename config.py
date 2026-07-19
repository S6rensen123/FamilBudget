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


def get_supabase_url() -> str:
    return _require_env("SUPABASE_URL")


def get_supabase_publishable_key() -> str:
    return _require_env("SUPABASE_PUBLISHABLE_KEY")


def get_supabase_secret_key() -> str:
    return _require_env("SUPABASE_SECRET_KEY")


def get_supabase_desktop_config() -> Dict[str, str]:
    return {
        "project_url": get_supabase_url(),
        "publishable_key": get_supabase_publishable_key(),
    }


def get_supabase_admin_config() -> Dict[str, str]:
    return {
        "project_url": get_supabase_url(),
        "publishable_key": get_supabase_publishable_key(),
        "secret_key": get_supabase_secret_key(),
    }
