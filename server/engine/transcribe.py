
import os
import json
import base64
import time
import subprocess
import argparse
import re
from pathlib import Path
from google import genai
from google.genai import types

# Configurations
MODEL_ID = "gemini-2.5-flash"
CHUNK_SIZE_MB = 4

def load_api_key():
    """
    Attempts to find .env.local in common locations and load GEMINI_API_KEY.
    """
    current_dir = Path(__file__).resolve().parent
    
    # Potential locations for .env.local
    candidates = [
        current_dir / ".env.local",
        current_dir.parent / ".env.local",
        current_dir.parent / "Poddub_Minimax" / "codes" / ".env.local", # Known location
        Path("d:/MingggSync/Playground/poddub-ai/.env.local"), # External but known
    ]

    for env_path in candidates:
        if env_path.exists():
            print(f"Loading env from: {env_path}")
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        key = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
    return None

def get_audio_duration(file_path):
    """Returns duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)
        ]
        # Create non-blocking subprocess or just standard run
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Warning: Could not determine duration for {file_path}: {e}")
        return 0

def split_audio_with_ffmpeg(input_path, output_dir, segment_time=300):
    """
    Splits audio into chunks of 'segment_time' seconds using ffmpeg.
    Returns a list of paths to the generated chunks.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Pattern for chunks: chunk_000.mp3, chunk_001.mp3
    output_pattern = output_dir / "chunk_%03d.mp3"
    
    # ffmpeg -y -i input.mp3 ...
    cmd = [
        "ffmpeg", "-y", "-i", str(input_path),
        "-f", "segment",
        "-segment_time", str(segment_time),
        "-c", "copy",
        str(output_pattern)
    ]
    
    print(f"Splitting audio into {segment_time}s chunks...")
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"Error splitting audio: {e.stderr.decode()}")
        return []
        
    # Collect generated files
    chunks = sorted(output_dir.glob("chunk_*.mp3"))
    print(f"Created {len(chunks)} chunks.")
    return chunks

def process_file_with_gemini(file_path, output_dir):
    api_key = load_api_key()
    if not api_key:
        print("Error: No GEMINI_API_KEY found in typical .env.local locations.")
        return
    
    client = genai.Client(api_key=api_key)
    
    # 1. Split Audio
    temp_chunks_dir = Path(output_dir) / "temp_chunks"
    chunks = split_audio_with_ffmpeg(file_path, temp_chunks_dir, segment_time=300) # 5 minutes
    
    if not chunks:
        print("Failed to split audio.")
        return

    total_chunks = len(chunks)
    all_segments = []
    all_speakers = {}
    current_time_offset = 0.0
    
    print(f"Starting transcription of {total_chunks} chunks...")

    # 2. Process contents
    for i, chunk_path in enumerate(chunks):
        print(f"Processing chunk {i+1}/{total_chunks}: {chunk_path.name}")
        
        chunk_duration = get_audio_duration(chunk_path)
        
        # Read chunk bytes
        with open(chunk_path, 'rb') as f:
            chunk_data = f.read()

        # Simple context management
        known_speakers = ", ".join(all_speakers)
        speaker_context = f"PREVIOUSLY IDENTIFIED SPEAKERS: [{known_speakers}]. Use these names if voices match." if known_speakers else ""
        
        prompt = f"""
        You are a professional transcriber and translator.
        This is Part {i+1} of {total_chunks} of a podcast.

        INSTRUCTIONS:
        1. **VERBATIM TRANSCRIPTION**: Transcribe every sentence in English.
        2. **Speaker Identification**: {speaker_context} If distinct names are mentioned, use them.
        3. **Speaker Gender**: Identify the gender (Male/Female) of each speaker.
        4. **TIMESTAMPS**: Provide `startTime` and `endTime` for each segment (formatted as MM:SS or HH:MM:SS), relative to the start of THIS chunk (00:00).
        5. **CONTENT FILTERING**: EXCLUDE advertisements, sponsor reads, and intro/outro music. Only transcribe the core conversation.
        6. **TRANSLATION**: Translate to Simplified Chinese.
           - Style: Colloquial, Natural, "Grounding" (接地气).
           - Polishing: Automatically polish the translation to be smooth.
        
        7. **Output Format**: JSON object with a list of segments and speaker info.
        """
        
        success = False
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=[
                        types.Part.from_bytes(data=chunk_data, mime_type="audio/mp3"),
                        types.Part.from_text(text=prompt)
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema={
                            'type': 'OBJECT',
                            'properties': {
                                'detectedSpeakers': {
                                    'type': 'ARRAY',
                                    'items': {
                                        'type': 'OBJECT',
                                        'properties': {
                                            'name': {'type': 'STRING'},
                                            'gender': {'type': 'STRING', 'enum': ['Male', 'Female', 'Unknown']}
                                        }
                                    }
                                },
                                'segments': {
                                    'type': 'ARRAY',
                                    'items': {
                                        'type': 'OBJECT',
                                        'properties': {
                                            'startTime': {'type': 'STRING'},
                                            'endTime': {'type': 'STRING'},
                                            'speaker': {'type': 'STRING'},
                                            'originalEnglish': {'type': 'STRING'},
                                            'translatedChinese': {'type': 'STRING'}
                                        }
                                    }
                                }
                            }
                        }
                    )
                )
                
                result = json.loads(response.text)
                if 'segments' in result:
                    chunk_segments = result['segments']
                     # Post-process timestamps
                    for seg in chunk_segments:
                        start_str = seg.get('startTime', '00:00')
                        end_str = seg.get('endTime', '00:00')
                        
                        def parse_time(t_str):
                            parts = list(map(int, t_str.split(':')))
                            if len(parts) == 2: return parts[0]*60 + parts[1]
                            if len(parts) == 3: return parts[0]*3600 + parts[1]*60 + parts[2]
                            return 0
                        
                        start_seconds = parse_time(start_str) + current_time_offset
                        end_seconds = parse_time(end_str) + current_time_offset
                        
                        # Format back to HH:MM:SS
                        def format_time(seconds):
                            m, s = divmod(seconds, 60)
                            h, m = divmod(m, 60)
                            return f"{int(h):02d}:{int(m):02d}:{int(s):02d}"
                        
                        seg['startTime'] = format_time(start_seconds)
                        seg['endTime'] = format_time(end_seconds)

                    all_segments.extend(chunk_segments)

                if 'detectedSpeakers' in result:
                    for s_obj in result['detectedSpeakers']:
                        name = s_obj.get('name')
                        if name and (name not in all_speakers or all_speakers[name] == 'Unknown'):
                            all_speakers[name] = s_obj.get('gender', 'Unknown')
                
                print(f"Chunk {i+1} done. Segments: {len(result.get('segments', []))}. Duration: {chunk_duration:.2f}s")
                success = True
                break
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                time.sleep(5)
        
        # Cleanup processed chunk immediately to save space? strict
        # chunk_path.unlink() # Keep for debug if needed, or remove at end
        
        if not success:
            print(f"Failed to process chunk {i+1}")
        
        current_time_offset += chunk_duration
        time.sleep(1)

    # Cleanup temp directory
    try:
        import shutil
        shutil.rmtree(temp_chunks_dir)
    except Exception as e:
        print(f"Warning: Failed to cleanup temp dir: {e}")

    # --- Save Outputs ---
    base_name = Path(file_path).stem
    output_path_dir = Path(output_dir) # Ensure type
    
    final_speakers_list = [{'name': k, 'gender': v} for k, v in all_speakers.items()]

    # 1. JSON Data
    project_data = {
        "segments": all_segments,
        "detectedSpeakers": final_speakers_list, 
        "version": "gemini-2.5-flash-optimized",
        "timestamp": int(time.time() * 1000)
    }
    json_path = output_path_dir / f"{base_name}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, ensure_ascii=False, indent=2)
    
    # 2. Markdown/Text Readable
    md_path = output_path_dir / f"{base_name}.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"# Transcript: {base_name}\n\n")
        
        # Readable speaker list
        speaker_summary = ", ".join([f"{k} ({v})" for k, v in all_speakers.items()])
        f.write(f"**Speakers Detected**: {speaker_summary}\n\n")
        f.write("---\n\n")
        for seg in all_segments:
            start = seg.get('startTime', '00:00:00')
            speaker = seg.get('speaker', 'Unknown')
            en = seg.get('originalEnglish', '')
            cn = seg.get('translatedChinese', '')
            f.write(f"### [{start}] {speaker}\n")
            f.write(f"**EN**: {en}\n")
            f.write(f"**CN**: {cn}\n\n")

    print(f"\nSuccess! Output saved to: {output_dir}")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to MP3 file")
    args = parser.parse_args()
    
    input_path = Path(args.file)
    if not input_path.exists():
        print(f"File not found: {input_path}")
        return

    # Determine output directory (../00Outputfiles)
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir.parent / "00Outputfiles"

    process_file_with_gemini(str(input_path), str(output_dir))

if __name__ == "__main__":
    main()
