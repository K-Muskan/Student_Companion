"""
virtual_assistant.py
====================

Pipeline:
  1. Wav2Lip  →  real AI lip-sync video  (runs inference.py as subprocess)
  2. FFmpeg   →  Ken Burns animated video (guaranteed fallback)

SETUP — do this once:
─────────────────────
1. pip install edge-tts

2. Add to your settings.py:
       WAV2LIP_DIR        = r"C:\Wav2Lip\Wav2Lip"
       WAV2LIP_CHECKPOINT = r"C:\Wav2Lip\Wav2Lip\checkpoints\wav2lip_gan.pth"
       WAV2LIP_VIDEO      = r"C:\Wav2Lip\Wav2Lip\therapist_video.mp4"

3. FFmpeg must be on PATH (already confirmed working).

Timing log fields returned to the frontend:
  status                    pending | processing | done | error
  method                    wav2lip | ffmpeg_kenburns
  video_url                 /media/therapist_videos/therapist_session_<id>.mp4
  error                     string (only on error)
  audio_generation_seconds  float
  video_generation_seconds  float
  total_seconds             float
  audio_done_at             ISO timestamp
  video_done_at             ISO timestamp
"""

import asyncio
import edge_tts
import os
import json
import shutil
import logging
import subprocess
import time
from datetime import datetime, timezone as dt_timezone

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
VOICE             = "en-US-EmmaNeural"
AUDIO_OUTPUT_NAME = "therapist_voice_{assessment_id}.mp3"
VIDEO_OUTPUT_NAME = "therapist_session_{assessment_id}.mp4"
FFMPEG_PATH       = r"C:\ffmpeg\bin\ffmpeg.exe"
TIMING_LOG_DIR    = os.path.join(settings.BASE_DIR, "media", "therapist_timing")

WAV2LIP_DIR        = getattr(settings, "WAV2LIP_DIR",        r"C:\Wav2Lip\Wav2Lip")
WAV2LIP_CHECKPOINT = getattr(settings, "WAV2LIP_CHECKPOINT", r"C:\Wav2Lip\Wav2Lip\checkpoints\wav2lip_gan.pth")
WAV2LIP_VIDEO      = getattr(settings, "WAV2LIP_VIDEO",      r"C:\Wav2Lip\Wav2Lip\therapist_video.mp4")

# Python interpreter inside the Wav2Lip venv
WAV2LIP_PYTHON = os.path.join(WAV2LIP_DIR, "wav2lip_env", "Scripts", "python.exe")


# ── Timing log ────────────────────────────────────────────────────────────────

def _timing_path(assessment_id):
    os.makedirs(TIMING_LOG_DIR, exist_ok=True)
    return os.path.join(TIMING_LOG_DIR, f"timing_{assessment_id}.json")


def load_timing_log(assessment_id):
    p = _timing_path(assessment_id)
    if os.path.exists(p):
        try:
            with open(p) as f:
                return json.load(f)
        except Exception:
            pass
    return {"assessment_id": assessment_id, "status": "pending"}


def save_timing_log(assessment_id, data):
    with open(_timing_path(assessment_id), "w") as f:
        json.dump(data, f, indent=2)


def _now_iso():
    return datetime.now(dt_timezone.utc).isoformat()


# ── Text-to-Speech ────────────────────────────────────────────────────────────

async def _tts_async(text, path):
    comm = edge_tts.Communicate(text, VOICE, rate="-10%", pitch="-1Hz")
    await comm.save(path)


def _generate_audio(text, path):
    try:
        asyncio.run(_tts_async(text, path))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_tts_async(text, path))
        loop.close()


# ── Therapist video ───────────────────────────────────────────────────────────

def _resolve_video_path():
    if WAV2LIP_VIDEO and os.path.exists(WAV2LIP_VIDEO):
        logger.info(f"[face] Using therapist video: {WAV2LIP_VIDEO}")
        return WAV2LIP_VIDEO

    raise FileNotFoundError(
        f"Therapist video not found.\n"
        f"  Checked: {WAV2LIP_VIDEO}\n"
        f"  Set WAV2LIP_VIDEO in settings.py to the correct path."
    )


# ── FFmpeg helper ─────────────────────────────────────────────────────────────

def _ffmpeg():
    if os.path.exists(FFMPEG_PATH):
        return FFMPEG_PATH
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"


# ── STRATEGY 1: Wav2Lip AI lip-sync ──────────────────────────────────────────

def _try_wav2lip(video_path, audio_path, video_dest):
    """
    Converts mp3 → wav into Wav2Lip's own temp/ dir (pre-seeding temp/temp.wav),
    then runs inference.py with all absolute paths.
    Output is written inside Wav2Lip results/ then moved to Django's media folder.
    """
    if not os.path.exists(WAV2LIP_DIR):
        logger.error(f"[wav2lip] WAV2LIP_DIR not found: {WAV2LIP_DIR}")
        return False

    if not os.path.exists(WAV2LIP_CHECKPOINT):
        logger.error(f"[wav2lip] Checkpoint not found: {WAV2LIP_CHECKPOINT}")
        return False

    if os.path.exists(WAV2LIP_PYTHON):
        python_exe = WAV2LIP_PYTHON
    else:
        python_exe = shutil.which("python") or "python"
        logger.warning(f"[wav2lip] Venv python not found, using: {python_exe}")

    ff = _ffmpeg()

    # ── Step 1: Pre-seed temp/temp.wav inside Wav2Lip's directory ────────────
    wav2lip_temp_dir = os.path.join(WAV2LIP_DIR, "temp")
    os.makedirs(wav2lip_temp_dir, exist_ok=True)
    preseeded_wav = os.path.join(wav2lip_temp_dir, "temp.wav")

    logger.info(f"[wav2lip] Converting audio → {preseeded_wav}")
    try:
        conv = subprocess.run(
            [
                ff, "-y",
                "-i", audio_path,
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                preseeded_wav,
            ],
            capture_output=True,
            text=True,
            timeout=1800000,
            cwd=WAV2LIP_DIR,
        )
        if conv.returncode != 0:
            logger.error(f"[wav2lip] Audio conversion failed:\n{conv.stderr[-600:]}")
            return False
        logger.info(f"[wav2lip] Audio ready: {os.path.getsize(preseeded_wav):,} bytes")
    except Exception as e:
        logger.error(f"[wav2lip] Audio conversion error: {e}")
        return False

    # ── Step 2: Prepare output path ───────────────────────────────────────────
    results_dir = os.path.join(WAV2LIP_DIR, "results")
    os.makedirs(results_dir, exist_ok=True)
    wav2lip_outfile = os.path.join(results_dir, f"out_{os.getpid()}.mp4")

    # ── Step 3: Build the command ─────────────────────────────────────────────
    cmd = [
        python_exe,
        "inference.py",
        "--checkpoint_path", WAV2LIP_CHECKPOINT,
        "--face",            video_path,
        "--audio",           preseeded_wav,
        "--outfile",         wav2lip_outfile,
    ]

    logger.info(f"[wav2lip] CMD: {' '.join(cmd)}")
    logger.info(f"[wav2lip] cwd: {WAV2LIP_DIR}")

    # ── Step 4: Run inference.py ──────────────────────────────────────────────
    try:
        proc = subprocess.run(
            cmd,
            cwd=WAV2LIP_DIR,
            capture_output=True,
            text=True,
            timeout=1800000,
        )

        logger.info(f"[wav2lip] exit={proc.returncode}")
        if proc.stdout:
            logger.info(f"[wav2lip] STDOUT:\n{proc.stdout[-1500:]}")
        if proc.stderr:
            logger.info(f"[wav2lip] STDERR:\n{proc.stderr[-1500:]}")

        if proc.returncode != 0:
            logger.error(f"[wav2lip] inference.py failed (exit {proc.returncode})")
            return False

        # ── Step 5a: Check the outfile we requested ───────────────────────────
        if os.path.exists(wav2lip_outfile) and os.path.getsize(wav2lip_outfile) > 10_000:
            shutil.move(wav2lip_outfile, video_dest)
            logger.info(f"[wav2lip] ✓ Moved requested outfile → {video_dest}")
            return True

        # ── Step 5b: Wav2Lip ignored --outfile, check its default location ────
        default_out = os.path.join(WAV2LIP_DIR, "results", "output.mp4")
        if os.path.exists(default_out) and os.path.getsize(default_out) > 10_000:
            shutil.copy2(default_out, video_dest)
            logger.info(f"[wav2lip] ✓ Copied default output.mp4 → {video_dest}")
            return True

        logger.error(
            f"[wav2lip] No usable output found.\n"
            f"  Requested : {wav2lip_outfile} "
            f"(exists={os.path.exists(wav2lip_outfile)})\n"
            f"  Default   : {default_out} "
            f"(exists={os.path.exists(default_out)})"
        )
        return False

    except subprocess.TimeoutExpired:
        logger.error("[wav2lip] Timed out after 10 minutes.")
        return False
    except Exception as e:
        logger.error(f"[wav2lip] Unexpected error: {e}", exc_info=True)
        return False
    finally:
        if os.path.exists(wav2lip_outfile):
            try:
                os.remove(wav2lip_outfile)
            except Exception:
                pass


# ── STRATEGY 2: FFmpeg Ken Burns animated video ───────────────────────────────

def _ffmpeg_kenburns(video_path, audio_path, video_dest):
    """
    Re-encodes the therapist video with the new audio track.
    Falls back to a simple re-mux if re-encode fails.
    No AI — guaranteed to work as long as ffmpeg is installed.
    """
    ff = _ffmpeg()
    logger.info(f"[ffmpeg] binary: {ff}")

    if not os.path.exists(video_path):
        logger.error(f"[ffmpeg] Video not found: {video_path}")
        return False
    if not os.path.exists(audio_path):
        logger.error(f"[ffmpeg] Audio not found: {audio_path}")
        return False

    try:
        logger.info("[ffmpeg] Re-encoding therapist video with new audio …")
        cmd = [
            ff, "-y",
            "-stream_loop", "-1", "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264", "-tune", "film",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-pix_fmt", "yuv420p",
            video_dest,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800000)

        if proc.returncode == 0 and os.path.getsize(video_dest) > 10_000:
            logger.info(f"[ffmpeg] Re-encode OK — {os.path.getsize(video_dest):,} bytes")
            return True

        logger.warning(
            f"[ffmpeg] Re-encode failed (code {proc.returncode}), "
            f"trying simple remux …\n{proc.stderr[-800:]}"
        )

        # Simple remux fallback — replace audio stream, copy video as-is
        cmd_remux = [
            ff, "-y",
            "-stream_loop", "-1", "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            video_dest,
        ]
        proc2 = subprocess.run(cmd_remux, capture_output=True, text=True, timeout=1800000)
        if proc2.returncode == 0:
            logger.info("[ffmpeg] Simple remux OK")
            return True

        logger.error(f"[ffmpeg] Simple remux also failed:\n{proc2.stderr[-800:]}")
        return False

    except FileNotFoundError:
        logger.error(
            "[ffmpeg] ffmpeg.exe not found!\n"
            "  Download from: https://www.gyan.dev/ffmpeg/builds/\n"
            "  Place ffmpeg.exe at: C:\\ffmpeg\\bin\\ffmpeg.exe"
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error("[ffmpeg] Process timed out.")
        return False
    except Exception as e:
        logger.error(f"[ffmpeg] Unexpected error: {e}", exc_info=True)
        return False


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_therapist_video(assessment_id: int, therapist_script: str) -> dict:
    timing = load_timing_log(assessment_id)
    timing["status"] = "processing"
    save_timing_log(assessment_id, timing)

    media_dir = os.path.join(settings.BASE_DIR, "media", "therapist_videos")
    os.makedirs(media_dir, exist_ok=True)

    audio_path = os.path.join(
        media_dir, AUDIO_OUTPUT_NAME.format(assessment_id=assessment_id)
    )
    video_dest = os.path.join(
        media_dir, VIDEO_OUTPUT_NAME.format(assessment_id=assessment_id)
    )

    # ── 1. Generate audio via edge-tts ────────────────────────────────────────
    logger.info(f"[TTS] Generating audio for assessment {assessment_id} …")
    t0 = time.time()
    try:
        _generate_audio(therapist_script, audio_path)
        audio_seconds = round(time.time() - t0, 1)
        logger.info(f"[TTS] Done in {audio_seconds}s → {audio_path}")
    except Exception as e:
        logger.error(f"[TTS] Failed: {e}")
        timing.update({"status": "error", "error": f"TTS failed: {e}"})
        save_timing_log(assessment_id, timing)
        return timing

    timing["audio_generation_seconds"] = audio_seconds
    timing["audio_done_at"] = _now_iso()
    save_timing_log(assessment_id, timing)

    # ── 2. Resolve therapist video ────────────────────────────────────────────
    try:
        video_path = _resolve_video_path()
    except FileNotFoundError as e:
        logger.error(str(e))
        timing.update({"status": "error", "error": str(e)})
        save_timing_log(assessment_id, timing)
        return timing

    # ── 3. Wav2Lip AI lip-sync ────────────────────────────────────────────────
    logger.info("[video] Attempting Wav2Lip …")
    t1 = time.time()

    if _try_wav2lip(video_path, audio_path, video_dest):
        video_seconds = round(time.time() - t1, 1)
        timing.update({
            "status":                   "done",
            "method":                   "wav2lip",
            "video_generation_seconds": video_seconds,
            "video_done_at":            _now_iso(),
            "total_seconds":            round(audio_seconds + video_seconds, 1),
        })
        logger.info(f"[video] ✓ Wav2Lip succeeded in {video_seconds}s")

    # ── 4. FFmpeg fallback ────────────────────────────────────────────────────
    else:
        logger.info("[video] Wav2Lip failed — falling back to FFmpeg re-encode …")
        t1 = time.time()

        if _ffmpeg_kenburns(video_path, audio_path, video_dest):
            video_seconds = round(time.time() - t1, 1)
            timing.update({
                "status":                   "done",
                "method":                   "ffmpeg_kenburns",
                "video_generation_seconds": video_seconds,
                "video_done_at":            _now_iso(),
                "total_seconds":            round(audio_seconds + video_seconds, 1),
            })
            logger.info(f"[video] ✓ FFmpeg fallback OK in {video_seconds}s")
        else:
            timing.update({
                "status": "error",
                "error": (
                    "All video methods failed.\n\n"
                    "Wav2Lip: check WAV2LIP_DIR, WAV2LIP_CHECKPOINT, "
                    "WAV2LIP_VIDEO in settings.py\n"
                    "FFmpeg:  ensure ffmpeg is installed and on PATH"
                ),
            })
            logger.error("[video] ✗ All methods failed.")

    timing["video_url"] = (
        f"/media/therapist_videos/"
        f"{VIDEO_OUTPUT_NAME.format(assessment_id=assessment_id)}"
    )
    save_timing_log(assessment_id, timing)
    return timing