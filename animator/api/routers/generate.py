"""POST /api/generate: start rendering a video the browser has already queued in Supabase."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from .. import supabase
from ..auth import User, current_user
from ..jobs import run_job
from ..schemas import GenerateRequest, GenerateResponse
from ..settings import get_settings

router = APIRouter(tags=["generate"])

ERRORS = {
    401: {"description": "Missing, invalid or expired Supabase access token"},
    402: {"description": "Not enough credits; the video is marked failed"},
    404: {"description": "No such video, or it belongs to someone else"},
    409: {"description": "The video isn't queued (already generating, ready or failed)"},
}


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED, responses=ERRORS)
def generate(request: GenerateRequest, background: BackgroundTasks, user: User = Depends(current_user)) -> GenerateResponse:
    video = supabase.get_video(request.video_id)
    if video is None or video["user_id"] != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")

    # claiming the row (queued -> generating) first means a repeated request can't charge twice
    claimed = supabase.update_video(video["id"], {"status": "generating"}, only_if_status="queued")
    if claimed is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This video is already {video['status']}.")

    settings = get_settings()
    cost = (video["scenes"] or settings.auto_scene_estimate) * settings.credits_per_scene
    if not supabase.spend_credits(user.id, cost):
        supabase.update_video(video["id"], {"status": "failed", "error": f"Not enough credits: this video needs {cost}."})
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, f"Not enough credits: this video needs {cost}.")

    background.add_task(run_job, claimed, cost)
    return GenerateResponse(video_id=video["id"], status="generating", credits_charged=cost)
