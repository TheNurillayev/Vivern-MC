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
        "crop=w=iw:h=ih-120:x=0:y='(t/4)*120',scale=720:1280",
        # 1: Camera Flash & Soft Dissolve
        "fade=t=in:st=0:d=0.7,eq=brightness='0.22*max(0,1-t*2)':contrast=1.12",
        # 2: Horizontal Pan Left Drift
        "crop=w=iw-90:h=ih:x='(t/4)*90':y=0,scale=720:1280",
        # 3: Warm Golden Glow & Contrast Pulse
        "eq=saturation='1.15+0.35*sin(t*2)':contrast=1.1:gamma=1.05,fade=t=in:st=0:d=0.5",
        # 4: Vertical Pan Down Drift
        "crop=w=iw:h=ih-120:x=0:y='(1-t/4)*120',scale=720:1280",
        # 5: Horizontal Pan Right Drift
        "crop=w=iw-90:h=ih:x='(1-t/4)*90':y=0,scale=720:1280",
        # 6: Diagonal Smooth Drift
        "crop=w=iw-70:h=ih-90:x='(t/4)*70':y='(t/4)*90',scale=720:1280"
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
        Full video rendering pipeline:
        1. Prepares photo composites with blur background
        2. Generates 4s clips (with rotating effects on every 3rd photo)
        3. Loops photos if audio duration exceeds photo duration
        4. Merges with birthday audio
        5. Concatenates with host promo video (at intro or outro)
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

        # Number of photo slots required to match audio length
        num_slots = max(1, math.ceil(audio_dur / clip_dur))
        logger.info(
            f"Rendering video for order {order_id}: audio_dur={audio_dur:.1f}s, "
            f"photos_uploaded={len(photo_paths)}, slots_needed={num_slots}"
        )

        with tempfile.TemporaryDirectory() as td:
            # Step 1: Pre-render composites for each unique photo
            composite_paths = []
            for idx, p_path in enumerate(photo_paths):
                comp_out = os.path.join(td, f"comp_{idx:03d}.jpg")
                self.create_photo_composite(p_path, comp_out, target_w, target_h)
                composite_paths.append(comp_out)

            # Step 2: Render each slot clip
            clip_files = []
            effect_counter = 0

            for slot_idx in range(num_slots):
                photo_idx = slot_idx % len(composite_paths)
                comp_img = composite_paths[photo_idx]

                # Determine duration: last clip matches exact audio duration
                if slot_idx == num_slots - 1:
                    this_dur = round(max(1.0, audio_dur - (slot_idx * clip_dur)), 2)
                else:
                    this_dur = clip_dur

                is_effect = ((slot_idx + 1) % 3 == 0)
                clip_out = os.path.join(td, f"clip_{slot_idx:04d}.mp4")

                if is_effect:
                    vf = self.EFFECTS[effect_counter % len(self.EFFECTS)]
                    effect_counter += 1
                else:
                    vf = "scale=720:1280"

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

                clip_files.append(clip_out)

            # Step 3: Concat video-only slideshow clips
            slideshow_list = os.path.join(td, "slideshow_concat.txt")
            with open(slideshow_list, "w", encoding="utf-8") as f:
                for c in clip_files:
                    safe_c = c.replace("\\", "/")
                    f.write(f"file '{safe_c}'\n")

            slideshow_video = os.path.join(td, "slideshow_video.mp4")
            cmd_concat_slideshow = [
                ffmpeg_bin, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", slideshow_list,
                "-c", "copy",
                slideshow_video
            ]
            subprocess.run(cmd_concat_slideshow, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            # Step 4: Mux slideshow video with birthday audio
            slideshow_with_audio = os.path.join(td, "slideshow_with_audio.mp4")
            cmd_mux = [
                ffmpeg_bin, "-y",
                "-i", slideshow_video,
                "-i", audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
                "-shortest",
                slideshow_with_audio
            ]
            subprocess.run(cmd_mux, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            # Step 5: Incorporate host promo video if available
            if host_video_path and os.path.exists(host_video_path) and os.path.getsize(host_video_path) > 0:
                normalized_host = os.path.join(td, "host_normalized.mp4")
                # Normalize host video: 720x1280, 25fps, 44.1k stereo aac
                host_vf = (
                    "split[hv_bg][hv_fg];"
                    "[hv_bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=15:5,colorchannelmixer=aa=1:rr=0.4:gg=0.4:bb=0.4[hv_blur];"
                    "[hv_fg]scale=720:1280:force_original_aspect_ratio=decrease[hv_scaled];"
                    "[hv_blur][hv_scaled]overlay=(W-w)/2:(H-h)/2[hv_out]"
                )
                cmd_norm_host = [
                    ffmpeg_bin, "-y",
                    "-i", host_video_path,
                    "-filter_complex", host_vf,
                    "-map", "[hv_out]",
                    "-map", "0:a?",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-ar", "44100",
                    "-ac", "2",
                    normalized_host
                ]
                proc_h = subprocess.run(cmd_norm_host, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if proc_h.returncode == 0 and os.path.exists(normalized_host):
                    # Combine normalized host video and slideshow
                    final_concat_list = os.path.join(td, "final_concat.txt")
                    p1 = normalized_host if host_video_position == "intro" else slideshow_with_audio
                    p2 = slideshow_with_audio if host_video_position == "intro" else normalized_host

                    with open(final_concat_list, "w", encoding="utf-8") as f:
                        f.write(f"file '{p1.replace('\\', '/')}'\n")
                        f.write(f"file '{p2.replace('\\', '/')}'\n")

                    cmd_final = [
                        ffmpeg_bin, "-y",
                        "-f", "concat",
                        "-safe", "0",
                        "-i", final_concat_list,
                        "-c", "copy",
                        "-movflags", "+faststart",
                        final_video_output
                    ]
                    subprocess.run(cmd_final, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                else:
                    logger.warning("Failed to normalize host video, falling back to slideshow alone.")
                    shutil.copy2(slideshow_with_audio, final_video_output)
            else:
                shutil.copy2(slideshow_with_audio, final_video_output)

        final_dur = get_media_duration(final_video_output)
        final_size = os.path.getsize(final_video_output) if os.path.exists(final_video_output) else 0

        logger.info(f"Video render completed for order {order_id}: duration={final_dur:.1f}s, size={final_size} bytes")
        return {
            "output_path": final_video_output,
            "duration_seconds": final_dur,
            "file_size_bytes": final_size
        }

video_renderer = VideoRenderer()
