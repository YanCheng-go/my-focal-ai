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
    turso_url: str = ""  # Turso database URL (when set, enables cloud sync)
    turso_auth_token: str = ""  # Turso auth token
    admin_password: str = ""  # Password for static site admin page (hashed in config.json)
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
