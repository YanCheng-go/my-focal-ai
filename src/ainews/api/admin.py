"""Admin UI for source management."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ainews.config import Settings, load_sources
from ainews.ingest.runner import fetch_single_source
from ainews.sources.manager import (
    SOURCE_FIELDS,
    add_source,
    delete_source,
    get_all_sources_flat,
    toggle_source,
    update_source,
    validate_source,
)
from ainews.storage.db import get_db, get_source_health

logger = logging.getLogger(__name__)

settings = Settings()
templates = Jinja2Templates(directory=str(settings.config_dir.parent / "templates"))

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@router.get("/api/sources")
def list_sources():
    sources = get_all_sources_flat(settings.config_dir)
    conn = get_db(settings.db_path)
    try:
        health = get_source_health(conn)
    finally:
        conn.close()

    for src in sources:
        name = src["name"]
        h = health.get(name, {})
        src["item_count"] = h.get("item_count", 0)
        src["last_fetched"] = h.get("last_fetched")
        src["last_run"] = h.get("last_run")

    return {"sources": sources, "source_fields": SOURCE_FIELDS}


@router.post("/api/sources")
def create_source(body: dict):
    source_type = body.get("type", "")
    source_data = {k: v for k, v in body.items() if k != "type"}
    # Convert tags from comma-separated string to list
    if "tags" in source_data and isinstance(source_data["tags"], str):
        source_data["tags"] = [t.strip() for t in source_data["tags"].split(",") if t.strip()]
    try:
        validate_source(source_type, source_data)
        add_source(settings.config_dir, source_type, source_data)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "created"}


@router.put("/api/sources/{source_type}/{index}")
def edit_source(source_type: str, index: int, body: dict):
    source_data = {k: v for k, v in body.items() if k != "type"}
    if "tags" in source_data and isinstance(source_data["tags"], str):
        source_data["tags"] = [t.strip() for t in source_data["tags"].split(",") if t.strip()]
    try:
        update_source(settings.config_dir, source_type, index, source_data)
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "updated"}


@router.delete("/api/sources/{source_type}/{index}")
def remove_source(source_type: str, index: int):
    try:
        delete_source(settings.config_dir, source_type, index)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted"}


@router.post("/api/sources/{source_type}/{index}/toggle")
def toggle_source_endpoint(source_type: str, index: int):
    try:
        toggle_source(settings.config_dir, source_type, index)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "toggled"}


@router.post("/api/sources/{source_type}/{index}/fetch")
async def fetch_source_endpoint(source_type: str, index: int):
    sources = get_all_sources_flat(settings.config_dir)
    target = None
    for s in sources:
        if s["type"] == source_type and s["index"] == index:
            target = s
            break
    if not target:
        raise HTTPException(status_code=404, detail="Source not found")

    conn = get_db(settings.db_path)
    try:
        sources_config = load_sources(settings.config_dir)
        result = await fetch_single_source(conn, sources_config, target["name"])
        return {"status": "fetched", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
