"""Optional Gemini features. Requires the `gemini` extra.

Read order for --prompt (see pipeline.py):
    STEP 1  storyboard.py      idea -> scenes of narrated beats
    STEP 2  images.py          scene -> whiteboard image
    STEP 3  narration.py       beats -> one audio take + per-beat windows
            beat_timing.py     find each beat inside that take
    STEP 4  detect_regions.py  image + beats -> region plan
    STEP 5  pipeline.py        render every scene into one video

settings.py holds model defaults, client.py the shared call/retry plumbing,
schemas.py the structured-output models. Prompt text is in ../prompts/.
"""
