"""Vercel serverless entry point — exposes the FastAPI app as a handler."""

from ainews.api.app import app  # noqa: F401 — Vercel discovers this by name

# Vercel's Python runtime looks for `app` in the handler module.
# The FastAPI app detects Vercel via VERCEL env var and disables the scheduler.
