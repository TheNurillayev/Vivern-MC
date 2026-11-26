import os
import math
import shutil
import tempfile
import logging
import subprocess
import re
from typing import List, Dict, Any, Optional
import imageio_ffmpeg
from PIL import Image, ImageFilter, ImageOps
from backend.app.services.storage.local_storage import storage_service

logger = logging.getLogger("vivern-video")

def get_ffmpeg_path() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()

def get_media_duration(file_path: str) -> float:
    ffmpeg_bin = get_ffmpeg_path()
    cmd = [ffmpeg_bin, "-i", file_path]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if m:
        h, m_, s = m.groups()
        return float(h) * 3600 + float(m_) * 60 + float(s)
    return 0.0

class VideoRenderer:
    """
    Renders high-quality 9:16 vertical MP4 video greetings (720x1280 @ 25fps)
    from customer photos, production audio, and optional host promo video.
    """

    EFFECTS = [
        # 0: Vertical Pan Up Drift
        "crop=w=iw:h=ih-120:x=0:y='(t/4)*120',scale=720:1280,format=yuv420p",
        # 1: Camera Flash & Soft Dissolve
        "fade=t=in:st=0:d=0.7,eq=brightness='0.22*max(0,1-t*2)':contrast=1.12,scale=720:1280,format=yuv420p",
        # 2: Horizontal Pan Left Drift
        "crop=w=iw-90:h=ih:x='(t/4)*90':y=0,scale=720:1280,format=yuv420p",
        # 3: Warm Golden Glow & Contrast Pulse
        "eq=saturation='1.15+0.35*sin(t*2)':contrast=1.1:gamma=1.05,fade=t=in:st=0:d=0.5,scale=720:1280,format=yuv420p",
        # 4: Vertical Pan Down Drift
        "crop=w=iw:h=ih-120:x=0:y='(1-t/4)*120',scale=720:1280,format=yuv420p",
        # 5: Horizontal Pan Right Drift
        "crop=w=iw-90:h=ih:x='(1-t/4)*90':y=0,scale=720:1280,format=yuv420p",
        # 6: Diagonal Smooth Drift
        "crop=w=iw-70:h=ih-90:x='(t/4)*70':y='(t/4)*90',scale=720:1280,format=yuv420p"
    ]

    def create_photo_composite(
        self,
        photo_path: str,
        output_path: str,
        target_w: int = 720,
        target_h: int = 1280
    ) -> str:
        """
        Creates a high quality 720x1280 composite:
        - Blurred, darkened background fitting canvas
        - Crisp centered foreground photo preserving original aspect ratio
        """
        with Image.open(photo_path) as orig:
            # Handle orientation from smartphone EXIF
            img = ImageOps.exif_transpose(orig).convert("RGB")

            # 1. Background: resize to fill 720x1280, blur, darken
            bg_scale = max(target_w / img.width, target_h / img.height)
            bg_w = int(img.width * bg_scale)
            bg_h = int(img.height * bg_scale)
            bg = img.resize((bg_w, bg_h), Image.Resampling.LANCZOS)

            # Center crop background to target size
            left = (bg_w - target_w) // 2
            top = (bg_h - target_h) // 2
            bg = bg.crop((left, top, left + target_w, top + target_h))

            # Apply soft blur and blend with black to create elegant background
            bg = bg.filter(ImageFilter.GaussianBlur(radius=24))
            dark_overlay = Image.new("RGB", (target_w, target_h), (0, 0, 0))
            bg = Image.blend(bg, dark_overlay, 0.40)

            # 2. Foreground: fit inside 680x1160
            fg_max_w, fg_max_h = target_w - 40, target_h - 100
            fg = img.copy()
            fg.thumbnail((fg_max_w, fg_max_h), Image.Resampling.LANCZOS)

            # 3. Paste fg centered onto bg
            paste_x = (target_w - fg.width) // 2
            paste_y = (target_h - fg.height) // 2
            bg.paste(fg, (paste_x, paste_y))

            bg.save(output_path, "JPEG", quality=92)
            return output_path

    def render_video(
        self,
        order_id: str,
        audio_path: str,
        photo_paths: List[str],
        host_video_path: Optional[str] = None,
        host_video_position: str = "intro"
    ) -> Dict[str, Any]:
        """
        Studio vertical 9:16 video renderer (720x1280 @ 25fps):
        1. Host promo video (muted, -an) plays during the phone dialing / keyboard ringing intro.
        2. Customer photos smoothly loop with rotating effects every 3 photos for the remaining audio duration.
        3. Video stream is assembled and cleanly muxed with the complete continuous master audio.
        """
        if not photo_paths:
            raise ValueError("Video yaratish uchun kamida bitta rasm talab qilinadi.")
        if not os.path.exists(audio_path):
            raise ValueError(f"Audio fayl topilmadi: {audio_path}")

        ffmpeg_bin = get_ffmpeg_path()
        final_video_output = storage_service.get_output_video_path(order_id)
        if os.path.exists(final_video_output):
            os.remove(final_video_output)

        audio_dur = get_media_duration(audio_path)
        if audio_dur <= 0:
            audio_dur = 60.0

        target_w, target_h = 720, 1280
        fps = 25
        clip_dur = 4.0

        with tempfile.TemporaryDirectory() as td:
            video_sequence_files = []

            # Step 1: Process Host Promo Video (Muted, placed at intro)
            host_dur = 0.0
            if host_video_path and os.path.exists(host_video_path) and os.path.getsize(host_video_path) > 0:
                raw_hdur = get_media_duration(host_video_path)
                if raw_hdur > 0:
                    # Cap host promo to between 2s and 12s (or max 20% of total audio)
                    host_dur = round(min(max(raw_hdur, 2.0), min(12.0, max(5.0, audio_dur * 0.20))), 2)
                    norm_host_path = os.path.join(td, "norm_host.mp4")

                    host_vf = (
                        "split[hv_bg][hv_fg];"
                        "[hv_bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=15:5,colorchannelmixer=aa=1:rr=0.4:gg=0.4:bb=0.4[hv_blur];"
                        "[hv_fg]scale=720:1280:force_original_aspect_ratio=decrease[hv_scaled];"
                        "[hv_blur][hv_scaled]overlay=(W-w)/2:(H-h)/2[hv_out]"
                    )
                    cmd_host = [
                        ffmpeg_bin, "-y",
                        "-t", str(host_dur),
                        "-i", host_video_path,
                        "-an",
                        "-filter_complex", host_vf,
                        "-map", "[hv_out]",
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p",
                        "-r", str(fps),
                        norm_host_path
                    ]
                    proc_h = subprocess.run(cmd_host, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    if proc_h.returncode == 0 and os.path.exists(norm_host_path) and os.path.getsize(norm_host_path) > 0:
                        video_sequence_files.append(norm_host_path)
                        logger.info(f"Host promo video normalized (muted, duration={host_dur}s)")
                    else:
                        logger.warning("Host promo normalization failed, skipping host intro.")
                        host_dur = 0.0

            # Step 2: Calculate remaining duration for customer photos slideshow
            slideshow_dur = max(4.0, audio_dur - host_dur)
            num_slots = max(1, math.ceil(slideshow_dur / clip_dur))
            logger.info(
                f"Rendering video for order {order_id}: audio_dur={audio_dur:.1f}s, "
                f"host_dur={host_dur:.1f}s, slideshow_dur={slideshow_dur:.1f}s, "
                f"photos_uploaded={len(photo_paths)}, slots_needed={num_slots}"
            )

            # Step 3: Pre-render composites for each unique photo
            composite_paths = []
            for idx, p_path in enumerate(photo_paths):
                comp_out = os.path.join(td, f"comp_{idx:03d}.jpg")
                self.create_photo_composite(p_path, comp_out, target_w, target_h)
                composite_paths.append(comp_out)

            # Step 4: Render each photo clip
            effect_counter = 0
            for slot_idx in range(num_slots):
                photo_idx = slot_idx % len(composite_paths)
                comp_img = composite_paths[photo_idx]

                if slot_idx == num_slots - 1:
                    this_dur = round(max(1.0, slideshow_dur - (slot_idx * clip_dur)), 2)
                else:
                    this_dur = clip_dur

                is_effect = ((slot_idx + 1) % 3 == 0)
                clip_out = os.path.join(td, f"clip_{slot_idx:04d}.mp4")

                if is_effect:
                    vf = self.EFFECTS[effect_counter % len(self.EFFECTS)]
                    effect_counter += 1
                else:
                    vf = "scale=720:1280,format=yuv420p"

                cmd = [
                    ffmpeg_bin, "-y",
                    "-loop", "1",
                    "-t", str(this_dur),
                    "-i", comp_img,
                    "-vf", vf,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-tune", "stillimage" if not is_effect else "fastdecode",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    clip_out
                ]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    logger.error(f"FFmpeg clip render failed for slot {slot_idx}: {proc.stderr.decode('utf-8', errors='ignore')}")
                    raise RuntimeError("Rasm klipini render qilishda xatolik yuz berdi.")

                video_sequence_files.append(clip_out)

            # Step 5: Concat all video clips (host promo intro + photos)
            full_video_list = os.path.join(td, "full_video_concat.txt")
            with open(full_video_list, "w", encoding="utf-8") as f:
                for c in video_sequence_files:
                    safe_c = c.replace("\\", "/")
                    f.write(f"file '{safe_c}'\n")

            full_video_track = os.path.join(td, "full_video_track.mp4")
            cmd_concat = [
                ffmpeg_bin, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", full_video_list,
                "-c", "copy",
                full_video_track
            ]
            proc_concat = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc_concat.returncode != 0 or not os.path.exists(full_video_track) or os.path.getsize(full_video_track) == 0:
                logger.warning(f"Fast concat copy fallback to re-encoding: {proc_concat.stderr.decode('utf-8', errors='ignore')[-300:]}")
                cmd_concat_fallback = [
                    ffmpeg_bin, "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", full_video_list,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    full_video_track
                ]
                subprocess.run(cmd_concat_fallback, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            # Step 6: Mux full video track with complete birthday audio
            cmd_mux = [
                ffmpeg_bin, "-y",
                "-i", full_video_track,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-shortest",
                "-movflags", "+faststart",
                final_video_output
            ]
            subprocess.run(cmd_mux, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

        final_dur = get_media_duration(final_video_output)
        final_size = os.path.getsize(final_video_output) if os.path.exists(final_video_output) else 0

        logger.info(f"Video render completed for order {order_id}: duration={final_dur:.1f}s, size={final_size} bytes")
        return {
            "output_path": final_video_output,
            "duration_seconds": final_dur,
            "file_size_bytes": final_size
        }

video_renderer = VideoRenderer()
