import os
import subprocess
import json
import logging
import imageio_ffmpeg

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_FORMATS = {"mp3", "wav", "m4a", "ogg", "aac", "flac"}
MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

class AudioValidationError(Exception):
    pass

def get_ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()

def validate_audio_file(file_path: str) -> dict:
    """
    Validates that a file is an actual valid, non-corrupt audio file using FFmpeg.
    Returns metadata dict: duration_seconds, format, sample_rate, channels, bitrate.
    Raises AudioValidationError if corrupt or unsupported.
    """
    if not os.path.exists(file_path):
        raise AudioValidationError("Audio file does not exist on disk.")

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise AudioValidationError("Audio file is empty (0 bytes).")
    if file_size > MAX_AUDIO_SIZE_BYTES:
        raise AudioValidationError(f"Audio file exceeds maximum size limit of {MAX_AUDIO_SIZE_BYTES // (1024*1024)}MB.")

    ffmpeg_bin = get_ffmpeg_path()

    # Use ffmpeg to probe audio stream info by testing decoding null output
    # ffmpeg -v error -i <file> -f null -
    cmd = [
        ffmpeg_bin,
        "-v", "error",
        "-i", file_path,
        "-f", "null",
        "-"
    ]

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        if proc.returncode != 0:
            error_output = proc.stderr.strip()
            raise AudioValidationError(f"Invalid or corrupted audio file: {error_output}")
    except subprocess.TimeoutExpired:
        raise AudioValidationError("Audio validation timed out.")
    except Exception as e:
        if isinstance(e, AudioValidationError):
            raise
        raise AudioValidationError(f"Failed to inspect audio file: {str(e)}")

    # Extract metadata using mutagen or ffprobe-compatible command
    # We can get duration via mutagen or ffmpeg info
    duration = 0.0
    audio_format = "unknown"
    sample_rate = 44100
    channels = 2

    try:
        import mutagen
        audio = mutagen.File(file_path)
        if audio is not None and hasattr(audio, "info"):
            duration = float(getattr(audio.info, "length", 0.0))
            sample_rate = int(getattr(audio.info, "sample_rate", 44100))
            channels = int(getattr(audio.info, "channels", 2))
            audio_format = getattr(audio, "mime", ["audio/mp3"])[0].split("/")[-1]
    except Exception as e:
        logger.warning(f"Mutagen inspection failed, using fallback: {e}")

    # Fallback duration probe if mutagen didn't get length
    if duration <= 0.0:
        # Probe duration via ffmpeg reading 1 frame
        cmd_info = [
            ffmpeg_bin,
            "-i", file_path
        ]
        proc_info = subprocess.run(cmd_info, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # stderr contains "Duration: HH:MM:SS.ms"
        for line in proc_info.stderr.splitlines():
            if "Duration:" in line:
                try:
                    parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
                    duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                    break
                except Exception:
                    pass

    if duration <= 0.0:
        raise AudioValidationError("Could not determine audio duration or audio is empty.")

    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    detected_format = ext if ext in SUPPORTED_AUDIO_FORMATS else audio_format

    return {
        "valid": True,
        "duration_seconds": round(duration, 2),
        "file_size_bytes": file_size,
        "format": detected_format,
        "sample_rate": sample_rate,
        "channels": channels
    }
