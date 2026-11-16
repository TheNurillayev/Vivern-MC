import os
import tempfile
from backend.app.services.audio.renderer import audio_renderer
from backend.app.services.audio.validator import validate_audio_file
from backend.tests.test_phase1_admin_library import generate_test_wav

def test_audio_renderer_5_stages_at_08_09():
    """AT-08, AT-09: 5-stage audio mixing (Intro, Speech + 3 BG tracks, Special Outro)."""
    # Create temporary files for all 6 inputs
    intro_bytes = generate_test_wav(duration_seconds=3.0, freq=300.0)
    speech_bytes = generate_test_wav(duration_seconds=15.0, freq=440.0)
    starter_bytes = generate_test_wav(duration_seconds=10.0, freq=520.0)
    wishes_bytes = generate_test_wav(duration_seconds=10.0, freq=660.0)
    ending_bytes = generate_test_wav(duration_seconds=10.0, freq=580.0)
    special_bytes = generate_test_wav(duration_seconds=8.0, freq=800.0)

    files_map = {}
    temp_files = []

    for name, data in [
        ("intro", intro_bytes),
        ("speech", speech_bytes),
        ("starter", starter_bytes),
        ("wishes", wishes_bytes),
        ("ending", ending_bytes),
        ("special", special_bytes)
    ]:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tf.write(data)
        tf.close()
        files_map[name] = tf.name
        temp_files.append(tf.name)

    try:
        order_id = "test_order_render_1"
        res = audio_renderer.render_production(
            order_id=order_id,
            original_recording_path=files_map["speech"],
            special_music_path=files_map["special"],
            number_call_path=files_map["intro"],
            starter_music_path=files_map["starter"],
            wishes_music_path=files_map["wishes"],
            call_ending_path=files_map["ending"],
            wishes_start_seconds=4.0,
            call_ending_start_seconds=11.0,
            outro_max_duration=6.0,
            music_volume_db=-16.0
        )

        assert os.path.exists(res["output_path"]), "Rendered output file must exist"
        assert res["duration_seconds"] > 20.0, f"Expected total duration > 20s, got {res['duration_seconds']}"

        # Validate the output file with FFmpeg
        meta = validate_audio_file(res["output_path"])
        assert meta["valid"] is True
        assert meta["format"] in ["mp3", "mpeg"]
        assert meta["channels"] == 2

        # Check render params
        params = res["render_params"]
        assert params["intro_duration"] <= 4.5
        assert params["speech_duration"] == 15.0
        assert params["wishes_duration"] == 7.0
        assert params["music_volume_db"] == -16.0

    finally:
        for p in temp_files:
            if os.path.exists(p):
                os.remove(p)

def test_variable_length_handling_at_05():
    """AT-05: Dynamic timeline handles short recordings without hardcoded timestamps."""
    intro_bytes = generate_test_wav(duration_seconds=2.0)
    speech_bytes = generate_test_wav(duration_seconds=6.0) # short speech 6s
    bg_bytes = generate_test_wav(duration_seconds=10.0)
    special_bytes = generate_test_wav(duration_seconds=4.0)

    temp_files = []
    def create_tmp(d):
        tf = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        tf.write(d)
        tf.close()
        temp_files.append(tf.name)
        return tf.name

    try:
        p_intro = create_tmp(intro_bytes)
        p_speech = create_tmp(speech_bytes)
        p_bg1 = create_tmp(bg_bytes)
        p_bg2 = create_tmp(bg_bytes)
        p_bg3 = create_tmp(bg_bytes)
        p_special = create_tmp(special_bytes)

        res = audio_renderer.render_production(
            order_id="test_order_short_variable",
            original_recording_path=p_speech,
            special_music_path=p_special,
            number_call_path=p_intro,
            starter_music_path=p_bg1,
            wishes_music_path=p_bg2,
            call_ending_path=p_bg3,
            wishes_start_seconds=1.5,
            call_ending_start_seconds=4.5,
            outro_max_duration=3.0
        )

        assert os.path.exists(res["output_path"])
        assert res["duration_seconds"] > 9.0 # ~2s intro + 6s speech + 3s outro
    finally:
        for p in temp_files:
            if os.path.exists(p):
                os.remove(p)

if __name__ == "__main__":
    print("Running Phase 4 acceptance tests (AT-05, AT-08, AT-09)...")
    test_audio_renderer_5_stages_at_08_09()
    print("PASS: AT-08, AT-09 5-stage FFmpeg audio arrangement & outro fade")

    test_variable_length_handling_at_05()
    print("PASS: AT-05 Variable length dynamic timeline handling")

    print("\nALL PHASE 4 ACCEPTANCE TESTS PASSED!")
