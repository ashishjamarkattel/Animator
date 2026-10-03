"""GET /api/videos/{video_id}: a video's status, for clients that poll instead of using Supabase Realtime."""

from fastapi import APIRouter, Depends, HTTPException, status

from .. import supabase
from ..auth import User, current_user
from ..schemas import VideoResponse

router = APIRouter(tags=["videos"])


@router.get(
    "/videos/{video_id}",
    response_model=VideoResponse,
    responses={401: {"description": "Not signed in"}, 404: {"description": "No such video, or not yours"}},
)
def get_video(video_id: str, user: User = Depends(current_user)) -> VideoResponse:
    video = supabase.get_video(video_id)
    if video is None or video["user_id"] != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found.")
    return VideoResponse.model_validate(video)
