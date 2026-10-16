"""POST /api/generate: start rendering a video the browser has already queued in Supabase."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from .. import supabase
from ..auth import User, current_user
from ..gemini_key import KeyCheckFailed, check_key
from ..jobs import run_job
from ..schemas import GenerateRequest, GenerateResponse

router = APIRouter(tags=["generate"])

ERRORS = {
    400: {"description": "Gemini rejected the API key; the video is marked failed"},
    401: {"description": "Missing, invalid or expired Supabase access token"},
    404: {"description": "No such video, or it belongs to someone else"},
    409: {"description": "The video isn't queued (already generating, ready or failed)"},
}


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED, responses=ERRORS)
def generate(request: GenerateRequest, background: BackgroundTasks, user: User = Depends(current_user)) -> GenerateResponse:
    video = supabase.get_video(request.video_id)
    if video is None or video["user_id"] != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    if video["status"] != "queued":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This video is already {video['status']}.")

    # check the key before starting, so a typo fails in a second instead of after the storyboard step
    api_key = request.gemini_api_key.get_secret_value()
    try:
        check_key(api_key)
    except KeyCheckFailed as exc:
        supabase.update_video(video["id"], {"status": "failed", "error": str(exc)}, only_if_status="queued")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    # claiming the row (queued -> generating) means a repeated request can't start it twice
    claimed = supabase.update_video(video["id"], {"status": "generating"}, only_if_status="queued")
    if claimed is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This video has already started.")

    background.add_task(run_job, claimed, api_key)
    return GenerateResponse(video_id=video["id"], status="generating")
