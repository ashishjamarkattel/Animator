# Animator API

The FastAPI server the web app (`frontend/`) calls to generate videos. Accounts, credits and the list of
videos live in Supabase. This server does the work the browser can't: it checks credits, runs the
storyboard pipeline, uploads the MP4 to storage and updates the video's status.

```bash
pip install -r requirements.txt
python -m animator.api                 # http://127.0.0.1:8000, interactive docs at /api/docs
python -m animator.api --port 9000 --reload
```

## Configuration

Set these in the repo's `.env` file, next to `GEMINI_API_KEY`:

| Variable | Required | What it is |
|---|---|---|
| `GEMINI_API_KEY` | yes | Same key the command line uses |
| `SUPABASE_URL` | yes | `https://<project>.supabase.co` |
| `SUPABASE_SECRET_KEY` | yes | The project's **secret** key (`sb_secret_…`, or the legacy `service_role` key). It bypasses row-level security, so keep it on the server only. The frontend uses the publishable key. |
| `API_ALLOWED_ORIGINS` | no | Comma-separated frontend URLs allowed to call the API. Default `http://localhost:5173` |
| `API_MAX_CONCURRENT_JOBS` | no | Videos rendered at the same time; the rest wait their turn. Default `1` |
| `API_CREDITS_PER_SCENE` | no | Default `2` |
| `API_AUTO_SCENE_ESTIMATE` | no | Scenes charged up front when the scene count is "Auto". Default `6` |

The database needs `frontend/supabase/schema.sql`, which includes the `spend_credits` and `refund_credits` functions this server calls.

## How a video gets made

```
browser                          Supabase                       this API
   │ insert videos row ─────────► status = queued
   │ POST /api/generate ───────────────────────────────────────► check token and owner
   │                                status = generating ◄─────── claim the row (queued only)
   │                                credits − estimate ◄──────── spend_credits
   │ ◄──────────────────────────────────────────── 202 Accepted
   │                                                             render (Gemini + local drawing)
   │                                videos/<user>/<id>.mp4 ◄──── upload
   │ ◄── realtime update ────────── status = ready ◄──────────── finish, refund unused scenes
```

If anything fails after the 202, the video is marked `failed` with a short reason the user can act on, and the full charge is refunded.

## Routes

All routes are under `/api`. Errors are JSON in the form `{"detail": "<message>"}`, worded so the frontend can show them as they are.

### `GET /api/health`

No sign-in needed. Reports whether this server can generate videos.

```json
{ "status": "ok", "ffmpeg": true, "gemini_configured": true, "supabase_configured": true }
```

`status` is `"degraded"` when any check is false.

### `POST /api/generate`

Starts rendering a video the browser has already inserted with `status = 'queued'`.

```
Authorization: Bearer <Supabase access token>
Content-Type: application/json

{ "video_id": "1b0c…" }
```

The prompt, scene count, voice and quality are read from the video's row, not from this request, so they can't be changed after the row is written.

**202 Accepted**

```json
{ "video_id": "1b0c…", "status": "generating", "credits_charged": 12 }
```

Cost is `scenes × 2` credits, or `6 × 2` when scenes is Auto. Unused scenes are refunded when the video finishes.

| Status | When |
|---|---|
| 401 | No token, or the token is invalid or expired |
| 402 | Not enough credits. The video is marked `failed` with the same message |
| 404 | The video doesn't exist or belongs to someone else |
| 409 | The video isn't `queued`; it's already generating, ready or failed. Nothing is charged |
| 422 | The body isn't `{"video_id": "<string>"}` |

### `GET /api/videos/{video_id}`

The video's current row. The web app uses Supabase Realtime instead; this route is for clients that poll.

```
Authorization: Bearer <Supabase access token>
```

**200 OK**

```json
{
  "id": "1b0c…",
  "prompt": "Why is the sky blue?",
  "status": "ready",
  "scenes": null,
  "voice": "Kore",
  "quality": "medium",
  "storage_path": "8f3a…/1b0c….mp4",
  "duration_seconds": 95.5,
  "error": null,
  "created_at": "2026-10-02T10:00:00+00:00"
}
```

`401` without a valid token, `404` if the video isn't yours.

To play or download a finished video, create a signed URL for `storage_path` in the private `videos` bucket. The web app does this with `supabase.storage.from('videos').createSignedUrls(...)`.

## Files

```
api/
  __main__.py       python -m animator.api: loads .env, starts uvicorn
  app.py            builds the app: CORS, then each router under /api
  settings.py       environment variables, read once
  auth.py           Bearer token → Supabase user (dependency for protected routes)
  supabase.py       every call to Supabase: users, video rows, credits, storage
  schemas.py        request and response bodies
  jobs.py           one generation job: wait for a slot → render → upload → finish
  routers/
    health.py       GET  /api/health
    generate.py     POST /api/generate
    videos.py       GET  /api/videos/{video_id}
```
