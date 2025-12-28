import os
import requests
import json
import subprocess
from pathlib import Path

# --- Configuration ---
# Allow importing from sibling directories or expect this to be run with correct PYTHONPATH
# For simplicity, we'll load env here or expect caller to set env.

def load_env_local(env_path):
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val.strip().strip('"').strip("'")

# Try to find .env.local relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env.local"
if ENV_PATH.exists():
    load_env_local(ENV_PATH)

API_KEY = os.environ.get("MINIMAX_API_KEY")
GROUP_ID = os.environ.get("MINIMAX_GROUP_ID")
API_BASE_URL = "https://api.minimaxi.com/v1"

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except Exception:
        raise FileNotFoundError("FFmpeg not found. Please ensure it is in PATH.")

def upload_file(file_path):
    """
    Uploads a file to Minimax and returns the file_id.
    Target URL: https://api.minimax.chat/v1/files/upload?GroupId=...
    """
    if not API_KEY or not GROUP_ID:
        raise ValueError("Missing MINIMAX_API_KEY or MINIMAX_GROUP_ID")
    
    url = f"{API_BASE_URL}/files/upload?GroupId={GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        # Content-Type is handled by requests when using files=
    }
    
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "audio/mpeg")}
        payload = {"purpose": "voice_clone"}
        
        response = requests.post(url, headers=headers, files=files, data=payload)
        
    if response.status_code != 200:
        raise Exception(f"File upload failed: {response.text}")
    
    result = response.json()
    if result.get("base_resp", {}).get("status_code") != 0:
         raise Exception(f"File upload API error: {result}")
         
    return result.get("file", {}).get("file_id")

def clone_voice(file_id, voice_id=None, prompt_text=""):
    """
    Clones a voice from an uploaded file_id.
    Target URL: https://api.minimax.chat/v1/voice_cloning?GroupId=...
    """
    url = f"{API_BASE_URL}/voice_clone?GroupId={GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # If no voice_id provided, generate a random one or let API handle it? 
    # Minimax usually requires a voice_id to update or create.
    # Actually, for T2A V2 custom voice, the endpoint is create_custom_voice.
    # It returns a voice_id.
    
    print(f"DEBUG: Uploaded File ID: {file_id}")

    # API requires 'voice_id' (alphanumeric, >8 chars)
    # Sanitize voice_id if provided, ensuring it fits requirements
    # If using name, strip special chars
    final_voice_id = voice_id if voice_id else f"ClonedVoice{file_id[-6:]}"
    
    # Ensure plain alphanumeric to avoid "invalid params"
    import re
    final_voice_id = re.sub(r'[^a-zA-Z0-9]', '', final_voice_id)
    if not final_voice_id[0].isalpha(): final_voice_id = "V" + final_voice_id
    if len(final_voice_id) < 8: final_voice_id += "12345678"

    # VERIFIED WORKING PAYLOAD (2024-12-24)
    # The simple payload with just file_id and voice_id works correctly.
    # The clone_prompt structure has strict duration limits and causes errors.
    payload = {
        "file_id": file_id,
        "voice_id": final_voice_id
    }
    print(f"DEBUG: Clone Payload: {payload}")
    
    response = requests.post(url, headers=headers, json=payload)
    print(f"DEBUG: Clone Response: {response.text}")
    
    if response.status_code != 200:
        raise Exception(f"Voice cloning failed: {response.text}")
        
    result = response.json()
    if result.get("base_resp", {}).get("status_code") != 0:
         raise Exception(f"Voice clone API error: {result}")
         
    # Check return structure. Usually returns { "voice_id": "...", ... }
    # UPDATE: API doesn't return voice_id, so we assume the one we sent is valid if success.
    # vid = result.get("voice_id")
    # print(f"DEBUG: Keys in result: {list(result.keys())}")
    # print(f"DEBUG: Returning Voice ID: '{vid}' (Type: {type(vid)})")
    
    # If we are here, status_code is 0 (success)
    print(f"DEBUG: API Success. Returning generated Voice ID: {final_voice_id}")
    return final_voice_id

def extract_segment(source_path, start_time, end_time, output_path):
    """
    Extracts a segment from source audio using ffmpeg.
    start_time, end_time: strings like "00:00:10" or seconds.
    """
    check_ffmpeg()
    
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-ss", str(start_time),
        "-to", str(end_time),
        "-c", "copy", # Fast copy without re-encoding
        str(output_path)
    ]
    
    # Validation: Re-encoding might be safer if "copy" fails due to keyframes, 
    # but for MP3 copy is usually fine. If cuts are imprecise, we might need re-encoding.
    # Let's use re-encoding to ensure clean cut and format.
    cmd = [
        "ffmpeg", "-y",
        "-i", str(source_path),
        "-ss", str(start_time),
        "-to", str(end_time),
        "-vn", "-acodec", "libmp3lame", "-q:a", "2",
        str(output_path)
    ]
    
    subprocess.run(cmd, capture_output=True, check=True)

def find_best_segment(segments, speaker_name, min_duration=15, max_duration=90):
    """
    Finds the best segment for voice cloning.
    Strategy:
    1. Avoid first 5 minutes (300s) to skip Intro/BGM.
    2. Look for segments with ideal duration (15s - 90s).
    3. Pick the longest available candidate in that "safe zone".
    4. Fallback: If nothing found in safe zone, check entire file.
    """
    
    SAFE_START_TIME = 300 # 5 minutes
    
    # Helper to parse time
    def to_sec(t_str):
        if not t_str: return 0
        parts = list(map(float, t_str.split(':')))
        if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2: return parts[0]*60 + parts[1]
        return 0

    candidates = []
    
    for seg in segments:
        if seg.get("speaker") != speaker_name: continue
        
        start = to_sec(seg.get("startTime"))
        end = to_sec(seg.get("endTime"))
        dur = end - start
        
        # Hard constraint: Too short segments (likely interruptions/noise) are useless for cloning
        if dur < min_duration: continue
        
        # Soft constraint: Too long segments might have mixed speakers or hallucinations? 
        # Actually long is good, but let's cap it to avoid uploading huge files if not needed.
        # But we pass max_duration to extract logic, here we just want to find a good source block.
        
        candidates.append({
            "seg": seg,
            "start": start,
            "dur": dur
        })

    # Strategy 1: Filter candidates in Safe Zone (> 5 min)
    safe_candidates = [c for c in candidates if c['start'] > SAFE_START_TIME]
    
    # If we have safe candidates, pick the longest one (up to a limit, but usually longer is better for quality)
    if safe_candidates:
        # Sort by duration descending
        safe_candidates.sort(key=lambda x: x['dur'], reverse=True)
        print(f"  -> Found {len(safe_candidates)} safe segments (>5m). Best duration: {safe_candidates[0]['dur']:.1f}s")
        return safe_candidates[0]['seg']
        
    # Strategy 2: Fallback to any candidate (maybe it's a short podcast < 5 min)
    if candidates:
        candidates.sort(key=lambda x: x['dur'], reverse=True)
        print(f"  -> No safe segments found. Falling back to earlier segments. Best duration: {candidates[0]['dur']:.1f}s")
        return candidates[0]['seg']

    print(f"Warning: No segment longer than {min_duration}s found for {speaker_name}.")
    return None

def process_cloning(json_path, audio_path, output_dir):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    segments = data.get("segments", [])
    speakers = data.get("detectedSpeakers", []) # List of dicts or strings
    
    # Normalize speakers
    speaker_names = set()
    for s in speakers:
        if isinstance(s, dict): speaker_names.add(s['name'])
        else: speaker_names.add(s)
            
    voice_map = {}
    temp_dir = Path(output_dir) / "temp_samples"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    for name in speaker_names:
        print(f"Finding sample for speaker: {name}...")
        best_seg = find_best_segment(segments, name)
        
        if not best_seg:
            print(f"  -> No suitable segment found. Skipping.")
            continue
            
        print(f"  -> Extracting segment ({best_seg['startTime']} - {best_seg['endTime']})...")
        sample_path = temp_dir / f"sample_{name}.mp3"
        try:
            extract_segment(audio_path, best_seg['startTime'], best_seg['endTime'], sample_path)
            
            print(f"  -> Uploading to Minimax...")
            file_id = upload_file(sample_path)
            
            print(f"  -> Cloning voice...")
            # Use name as part of voice ID for readability in dashboard
            import time
            voice_name = f"Clone_{name}_{int(time.time())}"
            # Pass the text from the segment as prompt_text
            prompt_text = best_seg.get('text', '')
            voice_id = clone_voice(file_id, voice_name, prompt_text)
            
            voice_map[name] = voice_id
            print(f"  -> Success! Voice ID: {voice_id}")
            
        except Exception as e:
            print(f"  -> Failed: {e}")
            
    # Save voice map
    map_path = Path(output_dir) / "voice_map.json"
    with open(map_path, 'w', encoding='utf-8') as f:
        json.dump(voice_map, f, ensure_ascii=False, indent=2)
        
    print(f"\nVoice mapping saved to {map_path}")
    return map_path

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("json", help="Transcript JSON file")
    parser.add_argument("audio", help="Source Audio file")
    parser.add_argument("--outdir", help="Output directory")
    args = parser.parse_args()
    
    out = args.outdir if args.outdir else os.path.dirname(args.json)
    process_cloning(args.json, args.audio, out)
