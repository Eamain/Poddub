import os
import json
import requests
import time
import subprocess
import re
import argparse
import sys
import shutil
try:
    from tqdm import tqdm
except ImportError:
    # Minimal fallback for tqdm if not installed
    def tqdm(iterable, *args, **kwargs):
        return iterable

# Import clone_voice functionality
# Expect clone_voice.py to be in the same directory
try:
    from clone_voice import clone_voice, upload_file, extract_segment, find_best_segment
    CLONE_AVAILABLE = True
except ImportError:
    print("Warning: clone_voice.py not found. Voice cloning disabled.")
    CLONE_AVAILABLE = False

# --- Configuration ---
# Since scripts are moved to codes/, BASE_DIR (Project Root) is the parent of the script's location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(CODE_DIR, ".env.local")
SOURCE_DIR = os.path.join(BASE_DIR, "sourcece files")
PREVIEW_DIR = os.path.join(BASE_DIR, "outputpreview")
FINAL_DIR = os.path.join(BASE_DIR, "output files")
OUTPUT_DIR = os.path.join(BASE_DIR, "segments")
FFMPEG_PATH = "ffmpeg"

# Load .env.local
if os.path.exists(ENV_PATH):
    with open(ENV_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'): continue
            if "=" in line:
                key, val = line.split("=", 1)
                os.environ[key] = val

API_KEY = os.environ.get("MINIMAX_API_KEY")
GROUP_ID = os.environ.get("MINIMAX_GROUP_ID")

# Voice Library (Verified Chinese V2 IDs)
AVAILABLE_VOICES = {
    "1": ("沉稳高管 (Reliable Executive)", "Chinese (Mandarin)_Reliable_Executive"),
    "2": ("温润男声 (Gentleman)", "Chinese (Mandarin)_Gentleman"),
    "3": ("播报男声 (Male Announcer)", "Chinese (Mandarin)_Male_Announcer"),
    "4": ("新闻女声 (News Anchor)", "Chinese (Mandarin)_News_Anchor"),
    "5": ("傲娇御姐 (Mature Woman)", "Chinese (Mandarin)_Mature_Woman"),
    "6": ("温暖闺蜜 (Warm Bestie)", "Chinese (Mandarin)_Warm_Bestie"),
}
# Backup IDs if technical ones fail: Chinese (Mandarin)_Reliable_Executive, Chinese (Mandarin)_News_Anchor

DEFAULT_VOICE = "Chinese (Mandarin)_Reliable_Executive"
PREVIEW_CHAR_LIMIT = 720 # ~3 minutes

def clean_text(text):
    return re.sub(r'\[.*?\]', '', text).strip()

def check_ffmpeg():
    try:
        subprocess.run([FFMPEG_PATH, "-version"], capture_output=True, check=True)
    except Exception:
        raise FileNotFoundError(f"FFmpeg not found. Please ensures it is in PATH.")

def verify_audio_file(file_path):
    if not os.path.exists(file_path) or os.path.getsize(file_path) < 100:
        return False
    cmd = [FFMPEG_PATH, "-v", "error", "-i", file_path, "-f", "null", "-"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except Exception:
        return False

def generate_segment(text, voice_id, segment_index, output_dir):
    url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={GROUP_ID}"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    # Get settings from ENV or defaults
    speed = float(os.environ.get("MINIMAX_SPEED", 1.0))
    vol = float(os.environ.get("MINIMAX_VOL", 1.0))
    pitch = int(os.environ.get("MINIMAX_PITCH", 0))

    payload = {
        "model": "speech-2.6-hd",
        "text": text,
        "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": vol, "pitch": pitch},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3"}
    }
    file_path = os.path.join(output_dir, f"seg_{segment_index:03d}.mp3")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                res_json = response.json()
                audio_hex = res_json.get("data", {}).get("audio")
                if audio_hex:
                    with open(file_path, "wb") as f:
                        f.write(bytes.fromhex(audio_hex))
                    return file_path, len(text)
            
            # If we get a valid error from API, don't necessarily retry unless it's a 5xx
            if response.status_code >= 500:
                print(f"Server Error {response.status_code}, retrying...")
            else:
                raise Exception(f"API Error {response.status_code}: {response.text}")
                
        except (requests.exceptions.RequestException, Exception) as e:
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"Error seg {segment_index} (Attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise e
    raise Exception("Max retries exceeded")

def select_input_file():
    if not os.path.exists(SOURCE_DIR): os.makedirs(SOURCE_DIR)
    files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".json") and f != "package.json"]
    if not files:
        base_jsons = [f for f in os.listdir(BASE_DIR) if f.endswith(".json") and f != "package.json"]
        if base_jsons:
            print(f"Moving .json files to '{os.path.basename(SOURCE_DIR)}'...")
            for f in base_jsons:
                os.rename(os.path.join(BASE_DIR, f), os.path.join(SOURCE_DIR, f))
            files = [f for f in os.listdir(SOURCE_DIR) if f.endswith(".json") and f != "package.json"]
        else:
            print(f"No .json files found in '{os.path.basename(SOURCE_DIR)}'.")
            sys.exit(1)
    
    print("\n--- Select Input JSON File ---")
    for i, f in enumerate(files):
        print(f"  {i+1}: {f}")
    
    while True:
        try:
            choice = input(f"Select file (1-{len(files)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(files):
                return os.path.join(SOURCE_DIR, files[idx])
        except ValueError:
            pass
        print("Invalid selection.")

def ask_voice_mapping(speakers_data, interactive=False, audio_path=None, output_dir=None):
    mapping = {}
    print("\n--- Voice Selection ---")
    
    # Normalize input
    normalized_speakers = []
    if speakers_data and isinstance(speakers_data[0], dict):
        normalized_speakers = speakers_data
    else:
        normalized_speakers = [{'name': s, 'gender': 'Unknown'} for s in speakers_data]

    normalized_speakers = [s for s in normalized_speakers if s.get('name')]
    
    seen = set()
    unique_speakers = []
    for s in normalized_speakers:
        if s['name'] not in seen:
            seen.add(s['name'])
            unique_speakers.append(s)

    # 1. First, attempt to load an existing voice_map.json if we are in a resume scenario
    # We can guess output_dir/voice_map.json
    existing_map = {}
    if output_dir:
        map_path = os.path.join(output_dir, "voice_map.json")
        if os.path.exists(map_path):
             print(f"Loading existing voice map from {map_path}...")
             try:
                 with open(map_path, 'r', encoding='utf-8') as f:
                     existing_map = json.load(f)
             except: pass

    # 2. Process Speakers
    for s_obj in unique_speakers:
        speaker = s_obj['name']
        gender = s_obj.get('gender', 'Unknown')
        
        # Check if already mapped
        if speaker in existing_map:
            mapping[speaker] = existing_map[speaker]
            print(f"  -> '{speaker}' assigned from existing map: {mapping[speaker]}")
            continue

        # Try Cloning if Audio Available and Cloning Module Loaded
        cloned_id = None
        if audio_path and CLONE_AVAILABLE and os.path.exists(audio_path):
            print(f"  -> Attempting to clone voice for '{speaker}'...")
            
            # Need segments data to find best segment. 
            # We don't have segments passed into this function directly in previous signature.
            # But main() has 'data'. We should have passed 'segments' to this function.
            # Fix: We will rely on caller to pass segments or read from the file again? 
            # For efficiency let's modify signature or just read the json if available in memory?
            # Actually, find_best_segment needs segments list.
            # Let's fallback to NOT cloning here if we don't have segments, OR modify signature.
            # Modifying signature is safer. But let's check call site.
            pass 

    # Voice Pools (Defaults)
    male_pool = ["1", "2", "3"]
    female_pool = ["4", "5", "6"]
    male_usage = 0
    female_usage = 0
    
    # We need segments for cloning logic. Let's assume we pass them or extract differently.
    # Refactoring: ask_voice_mapping should take 'segments' if cloning is desired.
    pass 


def ask_voice_mapping_v2(speakers_data, segments, audio_path=None, output_dir=None, interactive=False):
    mapping = {}
    print("\n--- Voice Selection & Cloning ---")

    # Load existing map
    if output_dir:
        map_path = os.path.join(output_dir, "voice_map.json")
        if os.path.exists(map_path):
             print(f"Loading existing voice map from {map_path}")
             try:
                 with open(map_path, 'r', encoding='utf-8') as f:
                     mapping = json.load(f)
             except: pass
    
    # Identify unique speakers
    normalized_speakers = []
    if speakers_data and isinstance(speakers_data[0], dict):
        normalized_speakers = speakers_data
    else:
        normalized_speakers = [{'name': s, 'gender': 'Unknown'} for s in speakers_data]
        
    unique_speakers = {}
    for s in normalized_speakers:
        if s['name'] and s['name'] not in unique_speakers:
            unique_speakers[s['name']] = s

    # Pools
    male_pool = ["1", "2", "3"]
    female_pool = ["4", "5", "6"]
    male_usage = 0
    female_usage = 0
    
    # Load saved voices if available
    saved_voices_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "saved_voices.json")
    if os.path.exists(saved_voices_path):
        try:
            with open(saved_voices_path, 'r', encoding='utf-8') as f:
                saved_voices = json.load(f)
                print(f"Loaded saved voices from: {saved_voices_path}")
                for name, vid in saved_voices.items():
                    if name in unique_speakers:
                        mapping[name] = vid
                        print(f"  -> Using saved Voice ID for '{name}': {vid}")
        except Exception as e:
            print(f"Warning: Failed to load saved_voices.json: {e}")

    temp_dir = None
    if output_dir:
        temp_dir = os.path.join(output_dir, "temp_samples")
        if not os.path.exists(temp_dir): os.makedirs(temp_dir)

    for name, s_obj in unique_speakers.items():
        if name in mapping: 
            continue
            
        gender = s_obj.get('gender', 'Unknown')
        
        # 1. Attempt Cloning
        cloned_success = False
        if audio_path and CLONE_AVAILABLE and os.path.exists(audio_path) and temp_dir:
            print(f"Processing Speaker: {name}...")
            best_seg = find_best_segment(segments, name)
            if best_seg:
                print(f"  -> Found sample segment ({best_seg['startTime']} - {best_seg['endTime']})")
                sample_path = os.path.join(temp_dir, f"sample_{name}.mp3")
                try:
                    extract_segment(audio_path, best_seg['startTime'], best_seg['endTime'], sample_path)
                    file_id = upload_file(sample_path)
                    voice_name = f"Clone_{name}_{int(time.time())}"
                    # Use segment text as prompt
                    prompt_text = best_seg.get('text', '') # translatedChinese? or original?
                    # Audio_to_Transcription segments have 'translatedChinese'
                    prompt_text = best_seg.get('translatedChinese', '') or "Welcome to the podcast."
                    
                    voice_id = clone_voice(file_id, voice_name, prompt_text)
                    mapping[name] = voice_id
                    print(f"  -> Cloning Success! Assigned Voice ID: {voice_id}")
                    cloned_success = True
                except Exception as e:
                    print(f"  -> Cloning Failed: {e}")
            else:
                 print(f"  -> No suitable sample segment found for cloning.")

        if cloned_success: continue

        # 2. Fallback to Defaults (only if cloning was NOT attempted/requested)
        # If cloning WAS requested (audio_path exists) and we reached here (cloned_success is False),
        # it means cloning failed. We must STOP.
        if audio_path and CLONE_AVAILABLE and os.path.exists(audio_path) and temp_dir:
             print(f"❌ Critical Error: Failed to clone voice for speaker '{name}'. Stopping execution.")
             sys.exit(1)
             
        default_idx = "1"
        reason = "Default"
        if gender.lower() == "female":
            default_idx = female_pool[female_usage % len(female_pool)]
            female_usage += 1
            reason = "Gender: Female (Rotation)"
        elif gender.lower() == "male":
             default_idx = male_pool[male_usage % len(male_pool)]
             male_usage += 1
             reason = "Gender: Male (Rotation)"
        else:
             default_idx = male_pool[male_usage % len(male_pool)]
             male_usage += 1
             reason = "Unknown Gender (Default)"
             
        assigned_voice = AVAILABLE_VOICES[default_idx][1]
        
        if interactive:
             print(f"Speaker '{name}' ({gender}) - Clone Failed/Unavailable.")
             mapping[name] = assigned_voice
        else:
             mapping[name] = assigned_voice
             print(f"  -> Assigned System Voice: {AVAILABLE_VOICES[default_idx][0]} [{reason}]")

    # Save updated map
    if output_dir:
        map_path = os.path.join(output_dir, "voice_map.json")
        with open(map_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)

    return mapping

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--file", help="Specify input JSON file")
    parser.add_argument("--audio", help="Optional: Source Audio file for Voice Cloning")
    parser.add_argument("--auto", action="store_true", help="Run in automation mode (no interactive prompts)")
    parser.add_argument("--no-preview", action="store_true", help="Skip preview generation")
    args = parser.parse_args()

    check_ffmpeg()
    
    # 1. Select File
    input_file = args.file if args.file else select_input_file()
    
    # 2. Ask for Preview (if not specified via flag)
    # If auto, default to False unless --preview is set.
    # If not auto, ask user.
    if args.auto:
        is_preview = args.preview # True if --preview, False if not (and not asking)
    else:
        is_preview = args.preview
        if not args.preview and not args.no_preview:
            choice = input("\nDo you want to generate a 3-minute PREVIEW first? (y/n) [y]: ").strip().lower()
            is_preview = (choice != 'n')

    # 3. Ask for Interactive Voice (if not specified via flag)
    if args.auto:
        is_interactive = args.interactive
    else:
        is_interactive = args.interactive
        if not args.interactive:
            choice = input("Do you want to manually SELECT VOICES? (y/n) [n]: ").strip().lower()
            is_interactive = (choice == 'y')

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    segments = data.get("segments", [])
    
    # Get speakers from metadata if available, otherwise extract from segments
    speakers_data = data.get("detectedSpeakers", [])
    if not speakers_data:
         # Fallback to extracting names from segments (Unknown gender)
         unique_names = sorted(list(set(seg.get("speaker", "Unknown") for seg in segments if seg.get("speaker") and seg.get("speaker") != "None")))
         speakers_data = [{'name': n, 'gender': 'Unknown'} for n in unique_names]

    # Determine project dir for output and voice map
    # If args.file is in the project dir, use that dir.
    project_segments_dir = None
    input_dir = os.path.dirname(os.path.abspath(input_file))
    if "00Outputfiles" in input_dir: # Heuristic
         project_segments_dir = input_dir
    else:
         # Standard fallback (e.g. running standalone)
         project_segments_dir = os.path.join(OUTPUT_DIR, os.path.splitext(os.path.basename(input_file))[0])
         
    if not os.path.exists(project_segments_dir): os.makedirs(project_segments_dir)

    # Use V2 Mapping Logic
    voice_map = ask_voice_mapping_v2(speakers_data, segments, audio_path=args.audio, output_dir=project_segments_dir, interactive=is_interactive)

    process_segments = []
    current_chars = 0
    for i, seg in enumerate(segments):
        text = clean_text(seg.get("translatedChinese", ""))
        if not text: continue
        current_chars += len(text)
        process_segments.append((i, seg, text))
        if is_preview and current_chars >= PREVIEW_CHAR_LIMIT: break

    if not os.path.exists(OUTPUT_DIR): os.makedirs(OUTPUT_DIR)
    
    # Create a project-specific segments directory to prevent collisions
    project_name = os.path.splitext(os.path.basename(input_file))[0]
    project_segments_dir = os.path.join(OUTPUT_DIR, project_name)
    if not os.path.exists(project_segments_dir): os.makedirs(project_segments_dir)

    if not os.path.exists(PREVIEW_DIR): os.makedirs(PREVIEW_DIR)
    if not os.path.exists(FINAL_DIR): os.makedirs(FINAL_DIR)
    
    segment_files = []
    chars_sent = 0
    chars_cached = 0
    
    for i, seg, text in tqdm(process_segments, desc="Processing"):
        voice_id = voice_map.get(seg.get("speaker", "Unknown"), DEFAULT_VOICE)
        file_path = os.path.join(project_segments_dir, f"seg_{i:03d}.mp3")
        if os.path.exists(file_path) and verify_audio_file(file_path):
            segment_files.append(file_path)
            chars_cached += len(text)
            continue
        try:
            path, c_count = generate_segment(text, voice_id, i, project_segments_dir)
            segment_files.append(path)
            chars_sent += c_count
        except Exception as e:
            print(f"Error seg {i}: {e}")
            print("CRITICAL: Segment generation failed. Stopping to prevent broken output.")
            sys.exit(1)

    # Output filename matches source JSON
    source_filename = os.path.basename(input_file).replace(".json", "_CN.mp3")
    target_dir = PREVIEW_DIR if is_preview else FINAL_DIR
    output_path = os.path.join(target_dir, source_filename)
    
    concat_file = os.path.join(project_segments_dir, "concat.txt")
    with open(concat_file, 'w', encoding='utf-8') as f:
        for f_path in segment_files: f.write(f"file '{f_path.replace(os.sep, '/')}'\n")
    
    # Remove old output to ensure we don't play previous successful runs on failure
    if os.path.exists(output_path): os.remove(output_path)
    
    result = subprocess.run([FFMPEG_PATH, "-y", "-f", "concat", "-safe", "0", "-i", concat_file, "-c", "copy", output_path], capture_output=True)
    if result.returncode != 0:
        print(f"FFmpeg Error: {result.stderr.decode('utf-8')}")
        sys.exit(1)
    
    # Copy source JSON to target directory if it's the final generation
    if not is_preview:
        json_target = os.path.join(target_dir, os.path.basename(input_file))
        shutil.copy2(input_file, json_target)
        print(f"Copied source JSON to: {json_target}")

    print(f"\n--- Token Usage Report ---")
    print(f"  本次生成的字符数: {chars_sent}")
    print(f"  从缓存中恢复的字符数: {chars_cached}")
    print(f"  总计处理字符数: {chars_sent + chars_cached}")
    print(f"--------------------------")
    print(f"\nDone! Output: {output_path}")

if __name__ == "__main__":
    main()
