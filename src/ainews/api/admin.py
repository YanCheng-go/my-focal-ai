"""Admin UI for source management."""

import hashlib
import logging
import secrets

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
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

logger = logging.getLogger(__name__)

settings = Settings()
templates = Jinja2Templates(directory=str(settings.config_dir.parent / "templates"))

_password_hash = (
    hashlib.sha256(settings.admin_password.encode()).hexdigest() if settings.admin_password else ""
)


def _check_admin_auth(admin_token: str | None) -> None:
    """Verify admin session token. No-op when password is not configured."""
    if not settings.admin_password:
        return
    if not admin_token:
        raise HTTPException(status_code=401, detail="Login required")
    if not secrets.compare_digest(admin_token, _password_hash):
        raise HTTPException(status_code=401, detail="Invalid session")


def _require_admin(admin_token: str | None = Cookie(None)) -> None:
    """FastAPI dependency that enforces admin auth on protected routes."""
    _check_admin_auth(admin_token)


def _get_backend():
    from ainews.api.app import _backend

    return _backend()


def _normalize_tags(data: dict) -> None:
    """Convert comma-separated tags string to list in-place."""
    if "tags" in data and isinstance(data["tags"], str):
        data["tags"] = [t.strip() for t in data["tags"].split(",") if t.strip()]


# Public routes (login/logout/page) — no dependency
router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/login")
def admin_login(body: dict, response: Response):
    """Authenticate admin and set session cookie."""
    if not settings.admin_password:
        raise HTTPException(status_code=400, detail="Admin password not configured")
    password = body.get("password", "")
    if not secrets.compare_digest(password, settings.admin_password):
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(
        "admin_token", _password_hash, httponly=True, samesite="strict", max_age=86400
    )
    return {"status": "ok"}


@router.post("/logout")
def admin_logout(response: Response):
    response.delete_cookie("admin_token")
    return {"status": "ok"}


@router.get("", response_class=HTMLResponse)
def admin_page(request: Request, admin_token: str | None = Cookie(None)):
    needs_auth = bool(settings.admin_password)
    is_authed = False
    if needs_auth:
        try:
            _check_admin_auth(admin_token)
            is_authed = True
        except HTTPException:
            pass
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "needs_auth": needs_auth, "is_authed": is_authed},
    )


# Protected API routes — auth enforced via router dependency
_api = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_require_admin)])


@_api.get("/api/sources")
def list_sources():
    sources = get_all_sources_flat(settings.config_dir)
    backend = _get_backend()
    try:
        health = backend.get_source_health()
    finally:
        backend.close()

    for src in sources:
        name = src["name"]
        h = health.get(name, {})
        src["item_count"] = h.get("item_count", 0)
        src["last_fetched"] = h.get("last_fetched")
        src["last_run"] = h.get("last_run")

    return {"sources": sources, "source_fields": SOURCE_FIELDS}


@_api.post("/api/resolve-url")
async def resolve_url_endpoint(body: dict):
    """Accept a URL and return auto-extracted source fields."""
    from ainews.sources.url_resolver import resolve_url

    url = body.get("url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        result = await resolve_url(url)
        return {
            "source_type": result.source_type,
            "fields": result.fields,
            "suggested_tags": result.suggested_tags,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@_api.post("/api/sources")
def create_source(body: dict):
    source_type = body.get("type", "")
    source_data = {k: v for k, v in body.items() if k != "type"}
    _normalize_tags(source_data)
    try:
        validate_source(source_type, source_data)
        add_source(settings.config_dir, source_type, source_data)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "created"}


@_api.put("/api/sources/{source_type}/{index}")
def edit_source(source_type: str, index: int, body: dict):
    source_data = {k: v for k, v in body.items() if k != "type"}
    _normalize_tags(source_data)
    try:
        update_source(settings.config_dir, source_type, index, source_data)
    except (ValueError, IndexError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "updated"}


@_api.delete("/api/sources/{source_type}/{index}")
def remove_source(source_type: str, index: int):
    try:
        delete_source(settings.config_dir, source_type, index)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "deleted"}


@_api.delete("/api/sources/content")
def delete_source_content_endpoint(source_name: str):
    """Delete all items from a given source name."""
    backend = _get_backend()
    try:
        deleted = backend.delete_source_content(source_name)
        return {"status": "deleted", "deleted": deleted}
    finally:
        backend.close()


@_api.post("/api/sources/{source_type}/{index}/toggle")
def toggle_source_endpoint(source_type: str, index: int):
    try:
        toggle_source(settings.config_dir, source_type, index)
    except IndexError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "toggled"}


@_api.post("/api/sources/{source_type}/{index}/fetch")
async def fetch_source_endpoint(source_type: str, index: int):
    sources = get_all_sources_flat(settings.config_dir)
    target = None
    for s in sources:
        if s["type"] == source_type and s["index"] == index:
            target = s
            break
    if not target:
        raise HTTPException(status_code=404, detail="Source not found")

    backend = _get_backend()
    try:
        sources_config = load_sources(settings.config_dir)
        result = await fetch_single_source(backend, sources_config, target["name"])
        return {"status": "fetched", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        backend.close()
