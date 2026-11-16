import os
import subprocess
import logging
import json
import uuid
from typing import Dict, Any, Optional
import imageio_ffmpeg
from backend.app.services.audio.validator import validate_audio_file, AudioValidationError
from backend.app.services.storage.local_storage import storage_service

logger = logging.getLogger(__name__)

def get_ffmpeg_bin() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()

class AudioRenderError(Exception):
    pass

class AudioProductionRenderer:
    """
    FFmpeg audio arrangement engine that renders the 5-stage production:
    1. Call Opening: Number & Call sounds FX
    2. Starter: Original Speech + Starter Music BG
    3. Wishes: Original Speech + Wishes Music BG (smooth transition)
    4. Call Ending: Original Speech + Call Ending Music BG
    5. Special Music Outro: Customer's Special Music appended with fade
    """

    def render_production(
        self,
        order_id: str,
        original_recording_path: str,
        special_music_path: str,
        number_call_path: str,
        starter_music_path: str,
        wishes_music_path: str,
        call_ending_path: str,
        wishes_start_seconds: float,
        call_ending_start_seconds: float,
        outro_max_duration: float = 30.0,
        music_volume_db: float = -16.0
    ) -> Dict[str, Any]:
        ffmpeg_bin = get_ffmpeg_bin()

        # Validate all input media files
        meta_orig = validate_audio_file(original_recording_path)
        meta_spec = validate_audio_file(special_music_path)
        meta_intro = validate_audio_file(number_call_path)
        meta_starter = validate_audio_file(starter_music_path)
        meta_wishes = validate_audio_file(wishes_music_path)
        meta_ending = validate_audio_file(call_ending_path)

        speech_dur = meta_orig["duration_seconds"]
        intro_dur = min(meta_intro["duration_seconds"], 4.5) # Cap intro FX to max 4.5s

        # Adjust transition points dynamically to fit speech duration
        wishes_t = min(max(wishes_start_seconds, 1.0), speech_dur - 2.0)
        ending_t = min(max(call_ending_start_seconds, wishes_t + 1.0), speech_dur - 0.5)

        dur_starter = wishes_t
        dur_wishes = max(ending_t - wishes_t, 1.0)
        dur_ending = max(speech_dur - ending_t, 1.0)

        output_path = storage_service.get_output_path(order_id)
        if os.path.exists(output_path):
            os.remove(output_path)

        # Convert music volume db to linear gain
        # -16 dB is approx 0.16
        linear_gain = round(10 ** (music_volume_db / 20.0), 3)

        # Build FFmpeg command with complex filtergraph
        # Inputs:
        # 0: Number & Call FX
        # 1: Original Speech
        # 2: Starter BG
        # 3: Wishes BG
        # 4: Call Ending BG
        # 5: Special Music Outro

        fade_len = 1.0 # 1 second crossfade

        # Filtergraph explanation:
        # [0:a] Intro FX: trim to intro_dur, format to 44.1k stereo [a_intro]
        # [1:a] Speech: format to 44.1k stereo, normalize volume [a_speech]
        # [2:a] Starter BG: volume gain, trim to dur_starter, fade out [a_starter]
        # [3:a] Wishes BG: volume gain, trim to dur_wishes, fade in & out [a_wishes]
        # [4:a] Ending BG: volume gain, trim to dur_ending, fade in [a_ending]
        # Concat starter + wishes + ending -> [a_bg_music]
        # Mix speech + bg_music -> [a_call_mixed]
        # Concat intro + call_mixed -> [a_full_call]
        # [5:a] Special outro: trim to outro_max_duration, fade in & fade out [a_outro]
        # Final concat: full_call + outro -> [out_a]

        filter_complex = (
            f"[0:a]atrim=0:{intro_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo[a_intro];"
            f"[1:a]atrim=0:{speech_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume=1.2[a_speech];"
            f"[2:a]atrim=0:{dur_starter},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},afade=t=out:st={max(0, dur_starter - fade_len)}:d={fade_len}[a_starter];"
            f"[3:a]atrim=0:{dur_wishes},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},afade=t=in:st=0:d={fade_len},afade=t=out:st={max(0, dur_wishes - fade_len)}:d={fade_len}[a_wishes];"
            f"[4:a]atrim=0:{dur_ending},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},afade=t=in:st=0:d={fade_len}[a_ending];"
            f"[a_starter][a_wishes][a_ending]concat=n=3:v=0:a=1[a_bg_music];"
            f"[a_speech][a_bg_music]amix=inputs=2:duration=first:dropout_transition=2[a_call_mixed];"
            f"[a_intro][a_call_mixed]concat=n=2:v=0:a=1[a_full_call];"
            f"[5:a]atrim=0:{outro_max_duration},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume=0.9,afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, outro_max_duration - 2.5)}:d=2.5[a_outro];"
            f"[a_full_call][a_outro]concat=n=2:v=0:a=1[out_a]"
        )

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", number_call_path,
            "-i", original_recording_path,
            "-i", starter_music_path,
            "-i", wishes_music_path,
            "-i", call_ending_path,
            "-i", special_music_path,
            "-filter_complex", filter_complex,
            "-map", "[out_a]",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ar", "44100",
            output_path
        ]

        logger.info(f"Rendering audio order {order_id} using FFmpeg...")
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
            if proc.returncode != 0:
                raise AudioRenderError(f"FFmpeg render failed (code {proc.returncode}): {proc.stderr[:1000]}")
        except subprocess.TimeoutExpired:
            raise AudioRenderError("FFmpeg audio rendering process timed out.")
        except Exception as e:
            if isinstance(e, AudioRenderError):
                raise
            raise AudioRenderError(f"Audio rendering error: {str(e)}")

        out_meta = validate_audio_file(output_path)
        logger.info(f"Audio production rendered successfully: {output_path} ({out_meta['duration_seconds']}s)")

        render_params = {
            "intro_duration": intro_dur,
            "speech_duration": speech_dur,
            "starter_duration": dur_starter,
            "wishes_duration": dur_wishes,
            "ending_duration": dur_ending,
            "outro_duration": min(outro_max_duration, meta_spec["duration_seconds"]),
            "music_volume_db": music_volume_db,
            "total_output_duration": out_meta["duration_seconds"]
        }

        return {
            "output_path": output_path,
            "duration_seconds": out_meta["duration_seconds"],
            "format": out_meta["format"],
            "render_params": render_params
        }

audio_renderer = AudioProductionRenderer()
