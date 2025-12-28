
import os
import json
import base64
import time
import subprocess
import re
from google import genai
from google.genai import types

# Configurations
API_KEY = "" # Will be filled from .env.local
MODEL_ID = "gemini-2.5-flash"
CHUNK_SIZE_MB = 4

def load_env():
    global API_KEY
    # Try multiple locations for .env.local
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.local'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env.local')
    ]
    for env_path in candidates:
         if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith("GEMINI_API_KEY="):
                        API_KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                        return

def get_audio_duration(file_path):
    """Returns duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"Warning: Could not determine duration for {file_path}: {e}")
        return 0

def process_file(file_path, output_dir):
    load_env()
    if not API_KEY:
        print("Error: No GEMINI_API_KEY found in .env.local")
        return

    client = genai.Client(api_key=API_KEY)
    
    file_size = os.path.getsize(file_path)
    chunk_size_bytes = CHUNK_SIZE_MB * 1024 * 1024
    total_chunks = (file_size + chunk_size_bytes - 1) // chunk_size_bytes
    
    all_segments = []
    all_speakers = set()
    current_time_offset = 0.0 # Tracks the start time of the current chunk
    
    print(f"Starting processing: {os.path.basename(file_path)}")
    print(f"File size: {file_size / (1024*1024):.2f} MB, Chunks: {total_chunks}")
    
    # Check if we can use ffmpeg to split for duration tracking
    # If we read by bytes, we can't be 100% sure of duration unless we probe the chunk.
    # So we will save each chunk to a temp file, probe it, then send it.
    
    with open(file_path, 'rb') as f:
        for i in range(total_chunks):
            print(f"Processing chunk {i+1}/{total_chunks}...")
            chunk_data = f.read(chunk_size_bytes)
            if not chunk_data: break

            # Save chunk to temp file to get duration
            temp_chunk_path = os.path.join(output_dir, f"temp_chunk_{i}.mp3")
            with open(temp_chunk_path, "wb") as temp_f:
                temp_f.write(chunk_data)
            
            chunk_duration = get_audio_duration(temp_chunk_path)
            
            # Simple context management for previous speakers
            known_speakers = ", ".join(all_speakers)
            speaker_context = f"PREVIOUSLY IDENTIFIED SPEAKERS: [{known_speakers}]. Use these names if voices match." if known_speakers else ""
            
            prompt = f"""
            You are a professional transcriber and translator.
            This is Part {i+1} of {total_chunks} of a podcast.

            INSTRUCTIONS:
            1. **VERBATIM TRANSCRIPTION**: Transcribe every sentence in English.
            2. **Speaker Identification**: {speaker_context} If distinct names are mentioned (e.g. Ben Gilbert, David Rosenthal), use them.
            3. **TIMESTAMPS**: Provide `startTime` and `endTime` for each segment (in format MM:SS or HH:MM:SS), relative to the start of THIS chunk (00:00).
            4. **CONTENT FILTERING**: EXCLUDE advertisements, sponsor reads, and intro/outro music. Only transcribe the core conversation.
            5. **TRANSLATION**: Translate to Simplified Chinese. 
               - Style: Colloquial, Natural, "Grounding" (接地气). 
               - Avoid machine-translation style. Make it sound like a real conversation.
               - Polishing: Automatically polish the translation to be smooth.
            
            6. **Output Format**: JSON object with a list of segments.
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
                                    'detectedSpeakers': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
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
                        for s in result['detectedSpeakers']:
                            if s: all_speakers.add(s)
                    
                    print(f"Chunk {i+1} done. Segments needed: {len(result.get('segments', []))}. Chunk duration: {chunk_duration:.2f}s")
                    success = True
                    break
                except Exception as e:
                    print(f"Attempt {attempt+1} failed: {e}")
                    time.sleep(5)
            
            # Update offset
            current_time_offset += chunk_duration
            
            # Clean up temp chunk
            if os.path.exists(temp_chunk_path):
                os.remove(temp_chunk_path)

            if not success:
                print(f"Failed chunk {i+1}")
            
            time.sleep(1) # Safety

    # Save outputs
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # JSON output
    project_data = {
        "segments": all_segments,
        "detectedSpeakers": sorted(list(all_speakers)),
        "version": "gemini-2.5-flash-optimized",
        "timestamp": int(time.time() * 1000)
    }
    json_path = os.path.join(output_dir, f"{base_name}.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, ensure_ascii=False, indent=2)
    
    # Markdown output with Timestamps
    md_path = os.path.join(output_dir, f"{base_name}.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(f"# Transcript: {base_name}\n\n")
        f.write(f"**Speakers**: {', '.join(sorted(list(all_speakers)))}\n\n")
        f.write("---\n\n")
        for seg in all_segments:
            start = seg.get('startTime', '00:00:00')
            speaker = seg.get('speaker', 'Unknown')
            en = seg.get('originalEnglish', '')
            cn = seg.get('translatedChinese', '')
            
            f.write(f"### [{start}] {speaker}\n")
            f.write(f"**EN**: {en}\n")
            f.write(f"**CN**: {cn}\n\n")
            
    print(f"Success! Files saved to {output_dir}")
    print(f"JSON: {json_path}")
    print(f"MD:   {md_path}")

if __name__ == "__main__":
    # Example usage
    # audio_file = r"..."
    # process_file(audio_file, "output")
    pass
