"""Video encoding backend.

Converts the animator's per-pixel reveal-time map into an MP4 by streaming
raw frames to ffmpeg.

Performance:
- Frame rendering uses sorted-pixel bucketing: only the narrow band of
  actively-fading pixels is blended each frame; fully-revealed pixels are
  committed once to a persistent buffer.  ~50-100x fewer pixel ops per frame.
- Pre-allocated frame buffer eliminates per-frame array allocation.
- The hold phase is generated with ffmpeg tpad instead of piping duplicate
  frames through stdin.
"""

import logging
import subprocess
import tempfile
import time
from contextlib import contextmanager

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@contextmanager
def ffmpeg_pipe(cmd):
    """Drain diagnostics to disk so ffmpeg cannot block on a full stderr pipe."""
    with tempfile.TemporaryFile() as errors:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errors,
        )
        try:
            yield proc.stdin
            proc.stdin.close()
            proc.wait()
        except BrokenPipeError:
            # An encoder failure may happen while writing or flushing stdin.
            try:
                proc.stdin.close()
            except BrokenPipeError:
                pass
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if not proc.stdin.closed:
                try:
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
        if proc.returncode != 0:
            errors.seek(0)
            detail = errors.read().decode(errors="replace").strip()
            raise RuntimeError(
                f"ffmpeg failed (exit {proc.returncode}). Check the output path and "
                f"that your FFmpeg build includes libx264.\n{detail}"
            )


def ffmpeg_cmd(w, h, fps, bitrate, preset, output_path):
    return [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "rgb24",
        "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", preset, "-b:v", bitrate, "-an",
        output_path,
    ]


def ffmpeg_cmd_tpad(w, h, fps, bitrate, preset, output_path, hold_dur):
    """Build ffmpeg command that clones the last frame for hold_dur seconds."""
    stop_frames = int(hold_dur * fps)
    return [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{w}x{h}", "-pix_fmt", "rgb24",
        "-r", str(fps), "-i", "-",
        "-vf", f"tpad=stop_mode=clone:stop={stop_frames}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", preset, "-b:v", bitrate, "-an",
        output_path,
    ]


def encode_blank_video(out_w, out_h, total_duration, output_path, fps, bitrate, preset):
    white = np.ones((out_h, out_w, 3), dtype=np.uint8) * 255
    white_bytes = white.tobytes()

    cmd = ffmpeg_cmd(out_w, out_h, fps, bitrate, preset, output_path)
    total_frames = int(total_duration * fps)
    with ffmpeg_pipe(cmd) as pipe:
        for _ in range(total_frames):
            pipe.write(white_bytes)


def encode_timing_video(
        img_array, timing, draw_end, total_duration, fade_dur,
        output_path, fps, bitrate, preset,
):
    """Stream a timed pixel-reveal of img_array to an MP4.

    timing holds each pixel's reveal time in seconds (inf = background).
    Only the narrow band of actively-fading pixels is blended per frame;
    fully-revealed pixels are committed once to a persistent buffer.
    """
    t2 = time.monotonic()
    h, w = img_array.shape[:2]
    out_h, out_w = h + (h % 2), w + (w % 2)

    # ── Gather content pixels ──
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    cy, cx = np.where(gray < 240)
    ct_timing = timing[cy, cx]
    ct_colors_f = img_array[cy, cx].astype(np.float32)
    ct_colors_u = img_array[cy, cx]  # uint8, for final commit

    # ── Sort pixels by reveal time ──
    order = np.argsort(ct_timing, kind="quicksort")
    s_timing = ct_timing[order]
    s_cy = cy[order]
    s_cx = cx[order]
    s_colors_f = ct_colors_f[order]
    s_colors_u = ct_colors_u[order]
    del ct_timing, ct_colors_f, ct_colors_u, cy, cx, order

    # ── Persistent frame buffer — fully-revealed pixels accumulate here ──
    frame_buf = np.full((out_h, out_w, 3), 255, dtype=np.uint8)
    committed = 0  # everything below this index is baked into frame_buf

    t3 = time.monotonic()
    logger.info("frame prep + sort: %.2fs", t3 - t2)

    # ── Encode ──
    # Render only the draw portion + a small buffer, then use ffmpeg
    # tpad to clone the last frame for the hold phase.  This avoids
    # piping gigabytes of identical hold frames through stdin.
    hold_dur = max(total_duration - draw_end - fade_dur, 0)
    draw_frames = int((draw_end + fade_dur) * fps) + 1

    use_tpad = hold_dur > 0.5  # worth it if > ~12 duplicate frames

    if use_tpad:
        cmd = ffmpeg_cmd_tpad(
            out_w, out_h, fps, bitrate, preset, output_path, hold_dur
        )
    else:
        draw_frames = int(total_duration * fps)
        cmd = ffmpeg_cmd(out_w, out_h, fps, bitrate, preset, output_path)

    frame_view = memoryview(frame_buf).cast("B")

    with ffmpeg_pipe(cmd) as pipe:
        for i in range(draw_frames):
            t_now = i / fps

            # 1. Commit newly fully-revealed pixels (their fade is done)
            full_cutoff = t_now - fade_dur
            new_committed = int(np.searchsorted(s_timing, full_cutoff, side="right"))
            if new_committed > committed:
                sl = slice(committed, new_committed)
                frame_buf[s_cy[sl], s_cx[sl]] = s_colors_u[sl]
                committed = new_committed

            # 2. Blend the narrow band of actively-fading pixels
            active_end = int(np.searchsorted(s_timing, t_now, side="right"))

            if active_end > committed:
                sl = slice(committed, active_end)
                a = np.clip((t_now - s_timing[sl]) / fade_dur, 0, 1)
                np.sqrt(a, out=a)
                a3 = a[:, np.newaxis]
                frame_buf[s_cy[sl], s_cx[sl]] = (
                        255.0 + (s_colors_f[sl] - 255.0) * a3
                ).astype(np.uint8)

            # Reuse the same buffer view instead of allocating a multi-megabyte
            # bytes object for every frame.
            pipe.write(frame_view)

    t4 = time.monotonic()
    logger.info("frame pipe + encode: %.2fs (%d frames piped)", t4 - t3, draw_frames)
