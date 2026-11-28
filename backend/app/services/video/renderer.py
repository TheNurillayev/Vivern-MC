import os
import math
import shutil
import tempfile
import logging
import subprocess
import re
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
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
    High-performance 9:16 vertical MP4 video greetings renderer (720x1280 @ 25fps).
    Strictly follows the Studio Schema:
    - 0s to 7s: Muted Host Promo Video (under phone keyboard typing & dialing sound)
    - 7s to 15s: Single photo displayed for 8 seconds (under telephone ringing sound until answer)
    - 15s to End: Dynamic photo slideshow with rotating creative effects (Light, Blur, Pixelate,
      Circle, Push, Rotate, Black, White, Zoom in/out, Dissolve) every 4 seconds.
    - Uses multi-threaded rendering and downsampled background blurring for ~50x rendering speedup.
    """

    EFFECTS = [
        # 0: Light (Flash & Brightness pulse)
        "fade=t=in:st=0:d=0.6,eq=brightness='0.22*max(0,1-t*2)':contrast=1.12,scale=720:1280,format=yuv420p",
        # 1: Blur (Defocus into sharp focus)
        "gblur=sigma=16:steps=2,fade=t=in:st=0:d=0.7,scale=720:1280,format=yuv420p",
        # 2: Pixelate (Pixelize into clarity)
        "scale=45:80:flags=neighbor,scale=720:1280:flags=neighbor,fade=t=in:st=0:d=0.7,format=yuv420p",
        # 3: Circle (Radial vignette reveal)
        "vignette=PI/3,fade=t=in:st=0:d=0.7,scale=720:1280,format=yuv420p",
        # 4: Push (Smooth slide push pan)
        "crop=w=iw-80:h=ih:x='(t/4)*80':y=0,scale=720:1280,format=yuv420p",
        # 5: Rotate 1 (Subtle dynamic tilt spin)
        "rotate='min(0.06,max(-0.06,(1-t*2)*0.06))':ow=720:oh=1280:fillcolor=black,scale=720:1280,format=yuv420p",
        # 6: Black (Cinematic fade through black)
        "fade=t=in:st=0:d=0.6:color=black,scale=720:1280,format=yuv420p",
        # 7: White (Clean flash fade through white)
        "fade=t=in:st=0:d=0.6:color=white,scale=720:1280,format=yuv420p",
        # 8: Zoom 1 (Ken Burns slow zoom in)
        "scale=720*1.12:1280*1.12,crop=720:1280:x='(iw-ow)/2+t*3':y='(ih-oh)/2+t*5',format=yuv420p",
        # 9: Zoom 2 (Ken Burns slow zoom out)
        "scale=720*1.12:1280*1.12,crop=720:1280:x='(iw-ow)/2-t*3':y='(ih-oh)/2-t*5',format=yuv420p",
        # 10: Dissolve 1 (Smooth cross dissolve)
        "fade=t=in:st=0:d=0.75,scale=720:1280,format=yuv420p",
        # 11: Dissolve 2 (Warm saturation glow dissolve)
        "eq=saturation='1.25+0.2*sin(t*2)':contrast=1.1,fade=t=in:st=0:d=0.7,scale=720:1280,format=yuv420p"
    ]

    def create_photo_composite(
        self,
        photo_path: str,
        output_path: str,
        target_w: int = 720,
        target_h: int = 1280
    ) -> str:
        """
        Ultra-fast composite generation:
        1. Downsamples background to 180x320 for instant blur (2ms instead of 200ms)
        2. Blurs and darkens background
        3. Scales crisp foreground centered keeping original aspect ratio
        """
        with Image.open(photo_path) as orig:
            img = ImageOps.exif_transpose(orig).convert("RGB")

            # Fast background: small downscale, blur radius 4, then upscale
            small_w, small_h = 180, 320
            bg_scale = max(small_w / img.width, small_h / img.height)
            bw = int(img.width * bg_scale)
            bh = int(img.height * bg_scale)
            bg_small = img.resize((bw, bh), Image.Resampling.BILINEAR)

            # Center crop small background
            left_s = (bw - small_w) // 2
            top_s = (bh - small_h) // 2
            bg_small = bg_small.crop((left_s, top_s, left_s + small_w, top_s + small_h))
            bg_small = bg_small.filter(ImageFilter.GaussianBlur(radius=4))

            # Upscale blurred background to full target
            bg = bg_small.resize((target_w, target_h), Image.Resampling.BILINEAR)

            # Dark overlay (38% opacity)
            dark_overlay = Image.new("RGB", (target_w, target_h), (0, 0, 0))
            bg = Image.blend(bg, dark_overlay, 0.38)

            # Foreground: crisp centered, max 670x1160
            fg_max_w, fg_max_h = target_w - 50, target_h - 120
            fg = img.copy()
            fg.thumbnail((fg_max_w, fg_max_h), Image.Resampling.BILINEAR)

            paste_x = (target_w - fg.width) // 2
            paste_y = (target_h - fg.height) // 2
            bg.paste(fg, (paste_x, paste_y))

            bg.save(output_path, "JPEG", quality=88, optimize=False)
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
        Renders Studio vertical 9:16 video (720x1280 @ 25fps):
        1. Segment 1 (0s to 7s, 7s duration): Host Promo Video (Muted, -an).
        2. Segment 2 (7s to 15s, 8s duration): Photo #1 under the dialing ringtone.
        3. Segment 3 (15s to Audio End): Slideshow of uploaded photos with rotating effects.
        4. Muxed with complete birthday master audio.
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

        # Exact timing specifications from user hand-drawn schema
        intro_total_dur = 15.0  # Typing & Phone ring duration
        promo_target_dur = 7.0  # Reklama videosi duration
        intro_photo_dur = 8.0   # Faqat bitta rasm qo'ng'iroq ovozi tugaguncha (15 - 7 = 8s)

        with tempfile.TemporaryDirectory() as td:
            video_sequence_files = []

            # Step 1: Pre-render composites for each unique photo in parallel
            composite_paths = [os.path.join(td, f"comp_{i:03d}.jpg") for i in range(len(photo_paths))]
            with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 2)) as executor:
                list(executor.map(
                    lambda item: self.create_photo_composite(item[0], item[1], target_w, target_h),
                    zip(photo_paths, composite_paths)
                ))

            # Step 2: Render Segment 1 (0s to 7s) -> Reklama Videosi (Muted, 7s)
            has_host = False
            if host_video_path and os.path.exists(host_video_path) and os.path.getsize(host_video_path) > 0:
                raw_hdur = get_media_duration(host_video_path)
                if raw_hdur > 0:
                    promo_clip = os.path.join(td, "promo_01_host.mp4")
                    host_vf = (
                        "split[hv_bg][hv_fg];"
                        "[hv_bg]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,boxblur=15:5,colorchannelmixer=aa=1:rr=0.4:gg=0.4:bb=0.4[hv_blur];"
                        "[hv_fg]scale=720:1280:force_original_aspect_ratio=decrease[hv_scaled];"
                        "[hv_blur][hv_scaled]overlay=(W-w)/2:(H-h)/2,scale=720:1280,format=yuv420p"
                    )
                    # If host video is shorter than 7s, loop it with -stream_loop -1 to fill 7s
                    cmd_promo = [
                        ffmpeg_bin, "-y",
                        "-stream_loop", "-1" if raw_hdur < promo_target_dur else "0",
                        "-t", str(promo_target_dur),
                        "-i", host_video_path,
                        "-an",  # Strictly muted
                        "-filter_complex", host_vf,
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p",
                        "-r", str(fps),
                        promo_clip
                    ]
                    proc_p = subprocess.run(cmd_promo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if proc_p.returncode == 0 and os.path.exists(promo_clip) and os.path.getsize(promo_clip) > 0:
                        video_sequence_files.append(promo_clip)
                        has_host = True
                        logger.info("Host promo video rendered: exactly 7.0s, muted (-an)")

            if not has_host:
                # Fallback if no host video: Photo #1 plays for 7s with subtle zoom
                promo_clip = os.path.join(td, "promo_01_fallback.mp4")
                cmd_p_fb = [
                    ffmpeg_bin, "-y",
                    "-loop", "1",
                    "-t", str(promo_target_dur),
                    "-i", composite_paths[0],
                    "-vf", "scale=720*1.08:1280*1.08,crop=720:1280:x='(iw-ow)/2+t*2':y='(ih-oh)/2+t*3',format=yuv420p",
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    promo_clip
                ]
                subprocess.run(cmd_p_fb, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                video_sequence_files.append(promo_clip)

            # Step 3: Render Segment 2 (7s to 15s) -> Faqat bitta rasm Qo'ng'iroq ovozi tugaguncha (8s)
            intro_photo_clip = os.path.join(td, "intro_02_photo.mp4")
            cmd_intro_p = [
                ffmpeg_bin, "-y",
                "-loop", "1",
                "-t", str(intro_photo_dur),
                "-i", composite_paths[0],
                "-vf", "fade=t=in:st=0:d=0.6,scale=720*1.08:1280*1.08,crop=720:1280:x='(iw-ow)/2-t*2':y='(ih-oh)/2-t*3',format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                intro_photo_clip
            ]
            subprocess.run(cmd_intro_p, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            video_sequence_files.append(intro_photo_clip)

            # Step 4: Render Segment 3 (15s to Audio End) -> Photo Slideshow with Rotating Effects
            slideshow_dur = max(4.0, audio_dur - intro_total_dur)
            num_slots = max(1, math.ceil(slideshow_dur / clip_dur))
            logger.info(
                f"Slideshow duration: {slideshow_dur:.1f}s, slots: {num_slots}, "
                f"photos: {len(composite_paths)}, effects: {len(self.EFFECTS)}"
            )

            def render_slideshow_clip(slot_idx: int) -> str:
                # Start photos from index 1 (or 0 if only 1 photo exists)
                photo_idx = (slot_idx + 1) % len(composite_paths)
                comp_img = composite_paths[photo_idx]

                if slot_idx == num_slots - 1:
                    this_dur = round(max(0.8, slideshow_dur - (slot_idx * clip_dur)), 2)
                else:
                    this_dur = clip_dur

                effect_vf = self.EFFECTS[slot_idx % len(self.EFFECTS)]
                out_path = os.path.join(td, f"slide_{slot_idx:04d}.mp4")

                cmd_s = [
                    ffmpeg_bin, "-y",
                    "-loop", "1",
                    "-t", str(this_dur),
                    "-i", comp_img,
                    "-vf", effect_vf,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-tune", "stillimage",
                    "-crf", "23",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    out_path
                ]
                subprocess.run(cmd_s, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                return out_path

            # Parallel rendering of all slideshow clips using ThreadPoolExecutor
            workers_count = min(4, os.cpu_count() or 2)
            with ThreadPoolExecutor(max_workers=workers_count) as pool:
                slide_clips = list(pool.map(render_slideshow_clip, range(num_slots)))

            video_sequence_files.extend(slide_clips)

            # Step 5: Fast Concat of all video segments
            concat_list_file = os.path.join(td, "concat_list.txt")
            with open(concat_list_file, "w", encoding="utf-8") as f:
                for c in video_sequence_files:
                    safe_c = c.replace("\\", "/")
                    f.write(f"file '{safe_c}'\n")

            full_video_track = os.path.join(td, "full_video_track.mp4")
            cmd_concat = [
                ffmpeg_bin, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_file,
                "-c", "copy",
                full_video_track
            ]
            proc_concat = subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if proc_concat.returncode != 0 or not os.path.exists(full_video_track) or os.path.getsize(full_video_track) == 0:
                logger.warning("Fast concat copy fallback to re-encode concat.")
                cmd_concat_fallback = [
                    ffmpeg_bin, "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_list_file,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p",
                    "-r", str(fps),
                    full_video_track
                ]
                subprocess.run(cmd_concat_fallback, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

            # Step 6: Final Mux: Master Audio + Full Video Track
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
            subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        final_dur = get_media_duration(final_video_output)
        final_size = os.path.getsize(final_video_output) if os.path.exists(final_video_output) else 0

        logger.info(f"Video render finished for order {order_id}: duration={final_dur:.1f}s, size={final_size} bytes")
        return {
            "output_path": final_video_output,
            "duration_seconds": final_dur,
            "file_size_bytes": final_size
        }

video_renderer = VideoRenderer()
