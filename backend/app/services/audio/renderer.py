import os
import subprocess
import logging
from typing import Dict, Any
from backend.app.services.audio.validator import validate_audio_file, get_ffmpeg_path
from backend.app.services.storage.local_storage import storage_service

logger = logging.getLogger(__name__)

class AudioRenderError(Exception):
    pass

class AudioProductionRenderer:
    """
    Studio-grade FFmpeg audio rendering engine for Vivern MC.
    Seamlessly assembles:
    1. Number & Call Sound FX: Full natural duration
    2. Original Call Audio: Clean vocal filter, speech loudness normalization
    3. Starter Music BG: Plays until birthday wishes begin, seamless crossfade
    4. Wishes Music BG: Plays during birthday wishes, seamless crossfade
    5. Call Ending BG: Plays until call concludes, seamless crossfade
    6. Special Music Outro: Birthday owner's special song played in 100% full length
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
        music_volume_db: float = -20.0
    ) -> Dict[str, Any]:
        ffmpeg_bin = get_ffmpeg_path()

        # Validate all input media files
        meta_orig = validate_audio_file(original_recording_path)
        meta_spec = validate_audio_file(special_music_path)
        meta_intro = validate_audio_file(number_call_path)
        meta_starter = validate_audio_file(starter_music_path)
        meta_wishes = validate_audio_file(wishes_music_path)
        meta_ending = validate_audio_file(call_ending_path)

        speech_dur = meta_orig["duration_seconds"]
        intro_dur = meta_intro["duration_seconds"]

        # Bound transition points cleanly to speech duration
        wishes_t = min(max(wishes_start_seconds, 1.0), max(1.5, speech_dur - 3.0))
        ending_t = min(max(call_ending_start_seconds, wishes_t + 1.0), max(wishes_t + 1.5, speech_dur - 0.5))

        # Full duration of special music
        outro_dur = meta_spec["duration_seconds"]

        output_path = storage_service.get_output_path(order_id)
        if os.path.exists(output_path):
            os.remove(output_path)

        # Convert music volume db to linear gain (-20 dB is approx 0.100 for audible background)
        linear_gain = round(10 ** (music_volume_db / 20.0), 4)

        # 2-second seamless crossfade between background music sections
        cf_dur = 2.0
        cf_half = cf_dur / 2.0

        dur1 = wishes_t + cf_half
        dur2 = (ending_t - wishes_t) + cf_dur
        dur3 = (speech_dur - ending_t) + cf_half

        delay2_ms = int(max(0, wishes_t - cf_half) * 1000)
        delay3_ms = int(max(0, ending_t - cf_half) * 1000)

        # Filtergraph explanation:
        # [0:a] Number & Call FX: full length, formatted to 44.1k stereo [a_intro]
        # [1:a] Speech: Studio gentle denoise + vocal clarity EQ + dynaudnorm loudness leveler [a_speech]
        # [2:a] Starter BG: plays until wishes_t with 2s crossfade out [bg1]
        # [3:a] Wishes BG: delayed to wishes_t - 1s, fades in 2s, plays until ending_t, fades out 2s [bg2]
        # [4:a] Ending BG: delayed to ending_t - 1s, fades in 2s, plays until speech ends [bg3]
        # Mix bg1 + bg2 + bg3 with normalize=0 -> [a_bg_music]
        # Mix speech + bg_music with normalize=0 -> [a_call_mixed]
        # Concat intro + call_mixed -> [a_full_call]
        # [5:a] Special Music: 100% full duration, 1s fade-in, smooth 1.5s natural decay [a_outro]
        # Concat full_call + outro -> [out_a]

        filter_complex = (
            f"[0:a]atrim=0:{intro_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo[a_intro];"
            f"[1:a]atrim=0:{speech_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,"
            f"highpass=f=80,lowpass=f=8500,afftdn=nf=-20,equalizer=f=2800:t=q:w=1.2:g=1.5,dynaudnorm=f=200:m=6:p=0.85[a_speech];"
            f"[2:a]atrim=0:{dur1},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},"
            f"afade=t=out:st={wishes_t - cf_half}:d={cf_dur}[bg1];"
            f"[3:a]atrim=0:{dur2},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},"
            f"afade=t=in:st=0:d={cf_dur},afade=t=out:st={dur2 - cf_dur}:d={cf_dur},adelay={delay2_ms}|{delay2_ms}[bg2];"
            f"[4:a]atrim=0:{dur3},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume={linear_gain},"
            f"afade=t=in:st=0:d={cf_dur},adelay={delay3_ms}|{delay3_ms}[bg3];"
            f"[bg1][bg2][bg3]amix=inputs=3:normalize=0:duration=longest[a_bg_music];"
            f"[a_speech][a_bg_music]amix=inputs=2:normalize=0:duration=first[a_call_mixed];"
            f"[a_intro][a_call_mixed]concat=n=2:v=0:a=1[a_full_call];"
            f"[5:a]atrim=0:{outro_dur},asetpts=PTS-STARTPTS,aformat=sample_rates=44100:channel_layouts=stereo,volume=0.95,"
            f"afade=t=in:st=0:d=1.0,afade=t=out:st={max(0, outro_dur - 1.5)}:d=1.5[a_outro];"
            f"[a_full_call][a_outro]concat=n=2:v=0:a=1[out_a]"
        )

        cmd = [
            ffmpeg_bin,
            "-y",
            "-threads", "0",
            "-t", str(intro_dur + 1.0), "-i", number_call_path,
            "-t", str(speech_dur + 1.0), "-i", original_recording_path,
            "-t", str(dur1 + 2.0), "-i", starter_music_path,
            "-t", str(dur2 + 2.0), "-i", wishes_music_path,
            "-t", str(dur3 + 2.0), "-i", call_ending_path,
            "-t", str(outro_dur + 1.0), "-i", special_music_path,
            "-filter_complex", filter_complex,
            "-map", "[out_a]",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            "-ar", "44100",
            output_path
        ]

        logger.info(f"Rendering audio order {order_id} using FFmpeg with seamless crossfades...")
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
            "starter_duration": dur1,
            "wishes_duration": dur2,
            "ending_duration": dur3,
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
