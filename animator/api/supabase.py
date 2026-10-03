"""Every call the server makes to Supabase, using the secret key (bypasses row-level security)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from .settings import get_settings

BUCKET = "videos"


def _client() -> httpx.Client:
    settings = get_settings()
    # only `apikey`: Supabase's gateway accepts both legacy service-role JWTs and new sb_secret_ keys here
    return httpx.Client(base_url=settings.supabase_url, headers={"apikey": settings.supabase_secret_key}, timeout=30)


def get_user(access_token: str) -> dict[str, Any] | None:
    """The user a browser access token belongs to, or None if it's invalid or expired."""
    with _client() as client:
        response = client.get("/auth/v1/user", headers={"Authorization": f"Bearer {access_token}"})
    return response.json() if response.status_code == 200 else None


def get_video(video_id: str) -> dict[str, Any] | None:
    with _client() as client:
        response = client.get("/rest/v1/videos", params={"id": f"eq.{video_id}", "select": "*"})
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def update_video(video_id: str, fields: dict[str, Any], *, only_if_status: str | None = None) -> dict[str, Any] | None:
    """Updates a video and returns the new row; None if no row matched (e.g. its status already moved on)."""
    params = {"id": f"eq.{video_id}"}
    if only_if_status:
        params["status"] = f"eq.{only_if_status}"
    with _client() as client:
        response = client.patch(
            "/rest/v1/videos", params=params, json=fields, headers={"Prefer": "return=representation"}
        )
    response.raise_for_status()
    rows = response.json()
    return rows[0] if rows else None


def spend_credits(user_id: str, amount: int) -> bool:
    """Atomically takes `amount` credits; False if the user doesn't have enough."""
    with _client() as client:
        response = client.post("/rest/v1/rpc/spend_credits", json={"p_user": user_id, "p_amount": amount})
    response.raise_for_status()
    return bool(response.json())


def refund_credits(user_id: str, amount: int) -> None:
    if amount <= 0:
        return
    with _client() as client:
        response = client.post("/rest/v1/rpc/refund_credits", json={"p_user": user_id, "p_amount": amount})
    response.raise_for_status()


def upload_video(storage_path: str, file: Path) -> None:
    with _client() as client, file.open("rb") as body:
        response = client.post(
            f"/storage/v1/object/{BUCKET}/{storage_path}",
            content=body.read(),
            headers={"Content-Type": "video/mp4", "x-upsert": "true"},
            timeout=300,
        )
    response.raise_for_status()
