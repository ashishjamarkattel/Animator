"""HTTP API for the web app: python -m animator.api

Read in this order:
    app.py        builds the FastAPI app and mounts the routers
    routers/      one file per route group (health, generate, videos)
    auth.py       turns the caller's Supabase token into a user id
    jobs.py       one generation job, step by step
    supabase.py   every read and write to Supabase
"""

from .app import create_app

__all__ = ["create_app"]
