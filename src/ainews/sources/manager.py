"""YAML round-trip read/write for source management."""

import os
from pathlib import Path

from ruamel.yaml import YAML

# Source type -> required fields mapping
SOURCE_FIELDS = {
    "twitter": {"required": ["handle"], "optional": ["tags"]},
    "youtube": {"required": ["channel_id", "name"], "optional": ["tags"]},
    "arxiv": {"required": ["url", "name"], "optional": ["tags"]},
    "rss": {"required": ["url", "name"], "optional": ["tags"]},
    "rsshub": {"required": ["route", "name"], "optional": ["source_type", "tags"]},
    "xiaohongshu": {"required": ["user_id", "name"], "optional": ["tags"]},
    "luma": {"required": ["handle"], "optional": ["tags"]},
    "leaderboard": {"required": ["url", "name"], "optional": ["tags"]},
    "arxiv_queries": {"required": ["query", "name"], "optional": ["tags"]},
}

# All source types live under the top-level `sources` key in sources.yml
NESTED_TYPES = set(SOURCE_FIELDS)

yaml = YAML()
yaml.preserve_quotes = True


def _sources_path(config_dir: Path) -> Path:
    return config_dir / "sources.yml"


def load_sources_roundtrip(config_dir: Path):
    """Load sources.yml preserving comments and formatting."""
    with open(_sources_path(config_dir)) as f:
        return yaml.load(f)


def save_sources(config_dir: Path, data):
    """Atomic write: write to .tmp then rename."""
    path = _sources_path(config_dir)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        yaml.dump(data, f)
    os.replace(tmp, path)


def validate_source(source_type: str, source_data: dict):
    """Validate source data against schema. Raises ValueError on failure."""
    if source_type not in SOURCE_FIELDS:
        raise ValueError(f"Unknown source type: {source_type}")
    schema = SOURCE_FIELDS[source_type]
    for field in schema["required"]:
        if field not in source_data or not source_data[field]:
            raise ValueError(f"Missing required field '{field}' for type '{source_type}'")


def _get_source_list(data, source_type: str):
    """Get the list for a source type, creating it if needed."""
    if "sources" not in data:
        data["sources"] = {}
    sources = data["sources"]
    if source_type not in sources:
        sources[source_type] = []
    return sources[source_type]


def add_source(config_dir: Path, source_type: str, source_data: dict):
    """Validate and append a new source."""
    validate_source(source_type, source_data)
    data = load_sources_roundtrip(config_dir)
    source_list = _get_source_list(data, source_type)
    source_list.append(source_data)
    save_sources(config_dir, data)


def update_source(config_dir: Path, source_type: str, index: int, source_data: dict):
    """Replace source entry at index."""
    validate_source(source_type, source_data)
    data = load_sources_roundtrip(config_dir)
    source_list = _get_source_list(data, source_type)
    if index < 0 or index >= len(source_list):
        raise IndexError(f"Index {index} out of range for {source_type}")
    source_list[index] = source_data
    save_sources(config_dir, data)


def delete_source(config_dir: Path, source_type: str, index: int):
    """Remove source entry at index."""
    data = load_sources_roundtrip(config_dir)
    source_list = _get_source_list(data, source_type)
    if index < 0 or index >= len(source_list):
        raise IndexError(f"Index {index} out of range for {source_type}")
    source_list.pop(index)
    save_sources(config_dir, data)


def toggle_source(config_dir: Path, source_type: str, index: int):
    """Toggle disabled field on a source."""
    data = load_sources_roundtrip(config_dir)
    source_list = _get_source_list(data, source_type)
    if index < 0 or index >= len(source_list):
        raise IndexError(f"Index {index} out of range for {source_type}")
    entry = source_list[index]
    if entry.get("disabled"):
        del entry["disabled"]
    else:
        entry["disabled"] = True
    save_sources(config_dir, data)


def get_source_display_name(source_type: str, entry: dict) -> str:
    """Get a display name for a source entry."""
    if source_type == "twitter":
        return f"@{entry['handle']}"
    if source_type == "luma":
        return f"Luma: {entry['handle']}"
    return entry.get("name", str(entry))


def get_all_sources_flat(config_dir: Path) -> list[dict]:
    """Return a flat list of all sources with type, index, and config."""
    data = load_sources_roundtrip(config_dir)
    result = []

    sources = data.get("sources", {})
    for stype in NESTED_TYPES:
        for i, entry in enumerate(sources.get(stype, []) or []):
            result.append(
                {
                    "type": stype,
                    "index": i,
                    "name": get_source_display_name(stype, entry),
                    "config": dict(entry),
                    "disabled": bool(entry.get("disabled")),
                }
            )

    return result
