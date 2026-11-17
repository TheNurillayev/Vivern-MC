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
        intro_dur = meta_intro["duration_seconds"] # Full natural duration of Number & Call FX

        # Adjust transition points dynamically to fit speech duration
        wishes_t = min(max(wishes_start_seconds, 0.5), max(0.6, speech_dur - 2.0))
        ending_t = min(max(call_ending_start_seconds, wishes_t + 0.5), max(wishes_t + 0.6, speech_dur - 0.2))

        dur_starter = wishes_t
        dur_wishes = max(ending_t - wishes_t, 0.5)
        dur_ending = max(speech_dur - ending_t, 0.5)

        # Full duration of special music with silence handling
        outro_dur = meta_spec["duration_seconds"]

        output_path = storage_service.get_output_path(order_id)
        if os.path.exists(output_path):
            os.remove(output_path)

        # Convert music volume db to linear gain (-16 dB is approx 0.16)
        linear_gain = round(10 ** (music_volume_db / 20.0), 3)

        fade_len = min(1.0, dur_starter / 2.0, dur_wishes / 2.0, dur_ending / 2.0)
        outro_fade = min(3.0, outro_dur / 3.0)

        # Filtergraph explanation:
        # [0:a] Number & Call FX: full length, format to 44.1k stereo [a_intro]
        # [1:a] Speech: Highpass + Lowpass + Denoise (afftdn) + Vocal EQ + Speech Normalizer [a_speech]
        # [2:a] Starter BG: volume gain, plays until wishes_t, fade out [a_starter]
        # [3:a] Wishes BG: volume gain, plays during wishes, fade in & out [a_wishes]
        # [4:a] Ending BG: volume gain, plays until call ends, fade in [a_ending]
        # Concat starter + wishes + ending -> [a_bg_music]
        # Mix speech + bg_music with speech priority -> [a_call_mixed]
        # Concat intro + call_mixed -> [a_full_call]
        # [5:a] Special Music: full length, clean fade-in and smooth fade-out [a_outro]
        # Concat full_call + outro -> [out_a]

        filter_complex = (
            f"[0:a]atrim=0:{intro_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo[a_intro];"
            f"[1:a]atrim=0:{speech_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,"
            f"highpass=f=120,lowpass=f=7500,afftdn=nf=-25,equalizer=f=3000:t=q:w=1.2:g=3.5,speechnorm=e=4:r=0.0001:l=1[a_speech];"
            f"[2:a]atrim=0:{dur_starter},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},"
            f"afade=t=out:st={max(0, dur_starter - fade_len)}:d={fade_len}[a_starter];"
            f"[3:a]atrim=0:{dur_wishes},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},"
            f"afade=t=in:st=0:d={fade_len},afade=t=out:st={max(0, dur_wishes - fade_len)}:d={fade_len}[a_wishes];"
            f"[4:a]atrim=0:{dur_ending},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},"
            f"afade=t=in:st=0:d={fade_len}[a_ending];"
            f"[a_starter][a_wishes][a_ending]concat=n=3:v=0:a=1[a_bg_music];"
            f"[a_speech][a_bg_music]amix=inputs=2:duration=first:dropout_transition=2[a_call_mixed];"
            f"[a_intro][a_call_mixed]concat=n=2:v=0:a=1[a_full_call];"
            f"[5:a]atrim=0:{outro_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume=0.95,"
            f"afade=t=in:st=0:d=1.0,afade=t=out:st={max(0, outro_dur - outro_fade)}:d={outro_fade}[a_outro];"
            f"[a_full_call][a_outro]concat=n=2:v=0:a=1[out_a]"
        )

        cmd = [
            ffmpeg_bin,
            "-y",
            "-threads", "0",
            "-t", str(intro_dur + 1.0), "-i", number_call_path,
            "-t", str(speech_dur + 1.0), "-i", original_recording_path,
            "-t", str(dur_starter + 2.0), "-i", starter_music_path,
            "-t", str(dur_wishes + 2.0), "-i", wishes_music_path,
            "-t", str(dur_ending + 2.0), "-i", call_ending_path,
            "-t", str(outro_dur + 1.0), "-i", special_music_path,
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
            "outro_duration": outro_dur,
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
