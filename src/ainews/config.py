"""Configuration loading."""

from pathlib import Path

import yaml
from pydantic_settings import BaseSettings

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


class Settings(BaseSettings):
    config_dir: Path = CONFIG_DIR
    db_path: Path = Path("data/ainews.db")
    rsshub_base: str = "http://localhost:1200"
    fetch_interval_minutes: int = 30
    ollama_model: str = "qwen3:4b"
    ollama_base_url: str = "http://localhost:11434"
    scoring: bool = True
    show_scores: bool = False  # Feature flag: show "Top Only" & "By Score" filters in UI
    admin_password: str = ""  # When set, admin routes require authentication
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""
    retention_days: int = 30  # Delete items older than this from the local DB (0 = keep forever)
    export_hours: int = 168  # Export window for data.json (default: 7 days = 168 hours)
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_prefix": "AINEWS_", "env_file": ".env"}


def load_sources(config_dir: Path | None = None) -> dict:
    path = (config_dir or CONFIG_DIR) / "sources.yml"
    with open(path) as f:
        return yaml.safe_load(f)


def load_principles(config_dir: Path | None = None) -> dict:
    path = (config_dir or CONFIG_DIR) / "principles.yml"
    with open(path) as f:
        return yaml.safe_load(f)
