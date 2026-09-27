#!/usr/bin/env python3
"""
HyperFrames Voiceover Generator & Audio Muxer
Uses Google Gemini 3.8 Flash TTS to synthesize voiceover cues from voiceover.json
and syncs them to video via FFmpeg.
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request


import glob

def parse_arguments():
    parser = argparse.ArgumentParser(description="Generate voiceover and merge with HyperFrames video.")
    parser.add_argument("--config", default="voiceover.json", help="Path to voiceover.json configuration")
    parser.add_argument("--video", default=None, help="Path to input raw video")
    parser.add_argument("--output", default="out/video.mp4", help="Path for final merged video")
    parser.add_argument("--workdir", default="audio_work", help="Directory for temporary audio files")
    return parser.parse_args()


def find_input_video(specified_path):
    if specified_path and os.path.exists(specified_path):
        return specified_path
    
    # Check renders directory
    render_candidates = sorted(glob.glob("renders/*.mp4"), key=os.path.getmtime, reverse=True)
    if render_candidates:
        return render_candidates[0]
    
    # Check out directory or root
    other_candidates = [f for f in glob.glob("**/*.mp4", recursive=True) if "audio_work" not in f and "final" not in f]
    if other_candidates:
        return sorted(other_candidates, key=os.path.getmtime, reverse=True)[0]
    
    return None


def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"⚠️  Config file '{config_path}' not found.")
        return None
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_api_key():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key and os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY="):
                    api_key = line.strip().split("=", 1)[1].strip()
                    break
    return api_key


def generate_segment_audio(text, voice_name, model, api_key, raw_out_path, wav_out_path):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [{"text": text}]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name
                    }
                }
            }
        }
    }

    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8")

    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                res = json.load(resp)
                candidates = res.get("candidates", [])
                if not candidates:
                    raise RuntimeError("No candidates returned from Gemini API")
                parts = candidates[0].get("content", {}).get("parts", [])
                audio_data = None
                mime_type = "audio/wav"
                for p in parts:
                    if "inlineData" in p:
                        audio_data = base64.b64decode(p["inlineData"]["data"])
                        mime_type = p["inlineData"].get("mimeType", "audio/wav")
                        break

                if not audio_data:
                    raise RuntimeError("No inline audio data found in API response")

                with open(raw_out_path, "wb") as f:
                    f.write(audio_data)

                # Convert to standard 24kHz / 48kHz WAV if needed
                if "wav" in mime_type.lower():
                    if os.path.exists(wav_out_path):
                        os.remove(wav_out_path)
                    os.rename(raw_out_path, wav_out_path)
                else:
                    subprocess.run([
                        "ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1",
                        "-i", raw_out_path, wav_out_path
                    ], capture_output=True, check=True)

                return True

        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait_sec = 20 * attempt
                print(f"   ⏳ Rate limit (429). Retrying in {wait_sec}s (attempt {attempt}/{max_retries})...")
                time.sleep(wait_sec)
            else:
                err_body = e.read().decode("utf-8", errors="replace")
                print(f"   ❌ HTTP Error {e.code}: {err_body[:300]}")
                return False
        except Exception as e:
            print(f"   ❌ Generation error: {e}")
            if attempt < max_retries:
                time.sleep(5)
            else:
                return False

    return False


def get_audio_duration(file_path):
    try:
        probe = subprocess.run([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "json", file_path
        ], capture_output=True, text=True, check=True)
        return float(json.loads(probe.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def main():
    args = parse_arguments()
    config = load_config(args.config)
    video_path = find_input_video(args.video)

    if not config:
        print("No voiceover configuration provided. Checking video...")
        if video_path and os.path.exists(video_path):
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            shutil.copyfile(video_path, args.output)
            print(f"Copied raw video to {args.output}")
        sys.exit(0)

    api_key = get_api_key()
    if not api_key:
        print("⚠️  GEMINI_API_KEY is not set! Skipping voiceover generation.")
        if video_path and os.path.exists(video_path):
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            shutil.copyfile(video_path, args.output)
            print(f"Fallback: copied raw video to {args.output}")
        sys.exit(0)

    model = config.get("model", "gemini-3.8-flash-tts")
    default_voice = config.get("voice", "Charon")
    total_duration = config.get("total_duration", 60)
    segments = config.get("segments", [])

    print(f"\n=======================================================")
    print(f"🎙️  HyperFrames Gemini TTS Narration Pipeline")
    print(f"Model: {model} | Voice: {default_voice} | Segments: {len(segments)}")
    print(f"=======================================================\n")

    os.makedirs(args.workdir, exist_ok=True)
    wav_files = []

    for idx, seg in enumerate(segments):
        seg_id = seg.get("id", f"seg_{idx}")
        start_sec = float(seg.get("start_sec", 0.0))
        text = seg.get("text", "").strip()
        voice = seg.get("voice", default_voice)

        if not text:
            continue

        raw_path = os.path.join(args.workdir, f"{seg_id}.raw")
        wav_path = os.path.join(args.workdir, f"{seg_id}.wav")

        print(f"[{idx+1}/{len(segments)}] {seg_id} @ {start_sec:.2f}s (voice: {voice})")
        print(f"   💬 \"{text}\"")

        ok = generate_segment_audio(text, voice, model, api_key, raw_path, wav_path)
        if not ok or not os.path.exists(wav_path):
            print(f"   ❌ Failed to generate audio for {seg_id}")
            continue

        dur = get_audio_duration(wav_path)
        print(f"   ✓ Audio generated ({dur:.2f}s, ends at {start_sec + dur:.2f}s)")
        wav_files.append((wav_path, start_sec, dur))

        # Pace requests to respect rate limits
        if idx < len(segments) - 1:
            time.sleep(12)

    if not wav_files:
        print("❌ No audio clips were successfully generated.")
        if os.path.exists(args.video):
            os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
            shutil.copyfile(args.video, args.output)
        sys.exit(0)

    print(f"\n=== Assembling Master Voice Track ({total_duration}s) ===")
    filter_parts = []
    inputs = []
    for i, (path, start, dur) in enumerate(wav_files):
        delay_ms = int(start * 1000)
        inputs.extend(["-i", path])
        filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume=1.0[a{i}]")

    mix_inputs = "".join(f"[a{i}]" for i in range(len(wav_files)))
    filter_graph = f"{'; '.join(filter_parts)}; {mix_inputs}amix=inputs={len(wav_files)}:dropout_transition=0:normalize=0[mixed]; [mixed]apad=whole_dur={total_duration}[outa]"

    master_wav = os.path.join(args.workdir, "master_voiceover.wav")
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_graph,
        "-map", "[outa]",
        "-t", str(total_duration),
        master_wav
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"FFmpeg audio mix error: {res.stderr}")
        sys.exit(1)

    print(f"✓ Master voice track created: {master_wav}")

    # Merge with input video if present
    if video_path and os.path.exists(video_path):
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        print(f"\n=== Merging Audio with Video: {video_path} -> {args.output} ===")
        merge_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", master_wav,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            args.output
        ]
        res_merge = subprocess.run(merge_cmd, capture_output=True, text=True)
        if res_merge.returncode != 0:
            print(f"Merge error: {res_merge.stderr}")
            sys.exit(1)
        print(f"\n🎉 Successfully created final video with voiceover: {args.output}")
    else:
        print(f"Input video not found. Master audio generated at: {master_wav}")


if __name__ == "__main__":
    main()
