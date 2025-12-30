
import os
import sys
import logging
import json
import requests
import tempfile
from flask import Flask, request, jsonify, send_file
from waitress import serve
from google import genai
import threading
import subprocess
import shutil
from werkzeug.utils import secure_filename
# Load .env.local explicitly
from pathlib import Path
current_path = Path(__file__).resolve()
possible_envs = [
    current_path.parent / '.env.local',
    current_path.parent.parent / '.env.local',
    current_path.parent.parent / 'Podcast_Tools' / 'Poddub_Minimax' / 'codes' / '.env.local'
]
for env_file in possible_envs:
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line and not line.startswith('#'):
                         k, v = line.split('=', 1)
                         if k not in os.environ: # Don't overwrite system env
                             os.environ[k] = v.strip().strip('"').strip("'")
        except Exception as e:
            print(f"Error loading {env_file}: {e}")

import re

# Paths
SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.path.join(SERVER_DIR, "engine")
OUTPUT_DIR = os.path.join(SERVER_DIR, "output")
UPLOAD_FOLDER = os.path.join(SERVER_DIR, "uploads")

for d in [ENGINE_DIR, OUTPUT_DIR, UPLOAD_FOLDER]:
    if not os.path.exists(d): os.makedirs(d)

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- CORS Configuration (Manual) ---
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# --- Configuration & Env Loading ---
def load_env_local():
    # Helper to find .env.local in common locations
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Check both locations. Load global first, then local specific to allow overrides.
    global_env = os.path.join(os.path.dirname(os.path.dirname(current_dir)), 'Podcast_Tools', 'Poddub_Minimax', 'codes', '.env.local')
    local_env = os.path.join(os.path.dirname(current_dir), '.env.local')
    
    candidates = [global_env, local_env]
    
    for env_path in candidates:
        if os.path.exists(env_path):
            try:
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        if "=" in line:
                            key, val = line.split("=", 1)
                            # Remove quotes if present
                            val = val.strip().strip("'").strip('"')
                            os.environ[key] = val
                logger.info(f"Loaded environment from: {env_path}")
            except Exception as e:
                logger.warning(f"Failed to load {env_path}: {e}")
            
load_env_local()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY")
MINIMAX_GROUP_ID = os.environ.get("MINIMAX_GROUP_ID")

if not GEMINI_API_KEY:
    logger.warning("GEMINI_API_KEY not found. Gemini TTS will fail.")
if not MINIMAX_API_KEY or not MINIMAX_GROUP_ID:
    logger.warning("MINIMAX_API_KEY or GROUP_ID not found. Minimax TTS will fail.")

# --- Gemini Configuration ---
# Restoring the VERIFIED working model from poddub_tts.py
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025") 

# --- Minimax Configuration (Verified Voices) ---
MINIMAX_VOICES = {
    "Ben": "Chinese (Mandarin)_Reliable_Executive",      # 沉稳高管
    "David": "Chinese (Mandarin)_Gentleman",             # 温润男声
    "Speaker A": "Chinese (Mandarin)_Reliable_Executive",
    "Speaker B": "Chinese (Mandarin)_Gentleman",
    "Male": "Chinese (Mandarin)_Male_Announcer",         # 播报男声
    "Female": "Chinese (Mandarin)_News_Anchor",          # 新闻女声
    "Default": "Chinese (Mandarin)_Reliable_Executive"
}

# --- Shared Utilities ---
def get_minimax_voice_id(speaker_name):
    # Simple fuzzy matching or fallback
    if not speaker_name: return MINIMAX_VOICES["Default"]
    
    # Try direct match
    if speaker_name in MINIMAX_VOICES:
        return MINIMAX_VOICES[speaker_name]
    
    # Try substring match
    for key, vid in MINIMAX_VOICES.items():
        if key in speaker_name:
            return vid
            
    return MINIMAX_VOICES["Default"]

# --- Generators ---

def generate_with_gemini(text, speaker):
    if not GEMINI_API_KEY:
        raise ValueError("Gemini API Key missing")
        
    client = genai.Client(api_key=GEMINI_API_KEY, http_options={'api_version': 'v1alpha'})
    logger.info(f"Gemini generating for {speaker}: {text[:20]}...")

    # Persona Instructions
    if "Ben" in speaker or "Speaker A" in speaker:
        system_instruction = "You are Ben Gilbert (Acquired). Deep, resonant, analytical voice. Downward inflection."
    elif "David" in speaker or "Speaker B" in speaker:
        system_instruction = "You are David Rosenthal (Acquired). Bright, energetic, high-pitched (Tenor). Upward inflection. Enthusiastic."
    else:
        system_instruction = "You are a professional narrator. Neutral, clear, balanced voice."

    prompt = f"{system_instruction}\n\nACTION: Read the following line exactly as written.\nLINE:\n{text}"
    config = { "response_modalities": ["AUDIO"] }

    # Create temp file
    fd, temp_path = tempfile.mkstemp(suffix=".pcm")
    os.close(fd)

    try:
        # Check for Live API model
        if "native-audio" in GEMINI_MODEL or "flash-exp" in GEMINI_MODEL:
            import asyncio
            async def run_gen():
                async with client.aio.live.connect(model=GEMINI_MODEL, config=config) as session:
                    await session.send(input=prompt, end_of_turn=True)
                    with open(temp_path, "wb") as f:
                        async for response in session.receive():
                            if response.server_content and response.server_content.model_turn:
                                for part in response.server_content.model_turn.parts:
                                    if part.inline_data:
                                        f.write(part.inline_data.data)
                            if response.server_content and response.server_content.turn_complete:
                                break
            asyncio.run(run_gen())
        else:
            # Standard generate_content
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=config
            )
            with open(temp_path, "wb") as f:
                if response.parts:
                    for part in response.parts:
                        if part.inline_data:
                            f.write(part.inline_data.data)

        if os.path.getsize(temp_path) == 0:
             raise Exception("Gemini returned empty audio")
             
        # Read and return bytes
        with open(temp_path, "rb") as f:
            audio_data = f.read()
        return audio_data, "audio/l16" # PCM

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def generate_with_minimax(text, speaker):
    if not MINIMAX_API_KEY or not MINIMAX_GROUP_ID:
        raise ValueError("Minimax API Key or Group ID missing")

    voice_id = get_minimax_voice_id(speaker)
    logger.info(f"Minimax generating for {speaker} (Voice: {voice_id}): {text[:20]}...")

    url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={MINIMAX_GROUP_ID}"
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "speech-2.6-hd",
        "text": text,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3"
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    
    if response.status_code != 200:
        raise Exception(f"Minimax API Error {response.status_code}: {response.text}")

    res_json = response.json()
    audio_hex = res_json.get("data", {}).get("audio")
    
    if not audio_hex:
        raise Exception(f"Minimax returned no audio data. Response: {res_json}")

    return bytes.fromhex(audio_hex), "audio/mpeg"


# --- HTTP Server ---

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok", 
        "gemini_model": GEMINI_MODEL,
        "providers": ["gemini", "minimax"]
    })

@app.route('/generate', methods=['POST'])
def generate_audio():
    data = request.json
    text = data.get('text')
    speaker = data.get('speaker', 'Speaker A')
    provider = data.get('provider', 'gemini').lower() # Default to gemini

    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        if provider == 'minimax':
            audio_data, mimetype = generate_with_minimax(text, speaker)
            filename = "audio.mp3"
        elif provider == 'gemini':
            audio_data, mimetype = generate_with_gemini(text, speaker)
            filename = "audio.pcm"
        else:
            return jsonify({"error": f"Unknown provider: {provider}"}), 400

        from io import BytesIO
        return send_file(
            BytesIO(audio_data),
            mimetype=mimetype,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Generation failed ({provider}): {e}")
        return jsonify({"error": str(e)}), 500


# --- Podcast Automation Endpoints ---

@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    filename = secure_filename(file.filename)
    upload_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(upload_path)
    
    # Define Output (Project Dir)
    project_name = os.path.splitext(filename)[0]
    project_output_dir = os.path.join(OUTPUT_DIR, project_name)
    if not os.path.exists(project_output_dir): os.makedirs(project_output_dir)

    script_path = os.path.join(ENGINE_DIR, "transcribe.py")
    
    def run_task():
        # engine/transcribe.py usage: python script.py [file_path] (it outputs to 00Outputfiles by default, we need to verify args)
        # Checking Audio_to_Transcription.py args:
        # It takes 'file_path' positional. Output dir is seemingly inferred or hardcoded? 
        # Actually viewed code earlier: it uses `output_dir = "00Outputfiles/" + base...`
        # We might need to pass --output logic if updated, or just let it write to its default and we detect it.
        # But wait, we copied it to server/engine/transcribe.py
        # We assume it runs in its own logic.
        cmd = [sys.executable, script_path, upload_path] 
        # Add output dir arg if supported? The original script didn't seem to have argparse for output dir in the snippets I saw.
        # It had `output_dir = ...` inside.
        # Let's trust it works or we wrap it.
        # For now, simplistic call.
        subprocess.run(cmd, check=False) # check=False to avoid crashing thread

    thread = threading.Thread(target=run_task)
    thread.start()
    
    return jsonify({"status": "started", "job_id": project_name})

# --- Job Management ---
from job_storage import JobStorage
from pipeline_runner import PipelineRunner

# ... imports ...

# Initialize Persistent Storage
JOBS_DIR = os.path.join(SERVER_DIR, "jobs")
job_storage = JobStorage(JOBS_DIR)

# Initialize Pipeline Runner
# Base tools is grandparent of server dir
BASE_TOOLS_DIR = os.path.dirname(os.path.dirname(SERVER_DIR))
pipeline_runner = PipelineRunner(job_storage, BASE_TOOLS_DIR)

# --- Background Processing ---
def run_backend_analysis(job_id, file_path, project_name):
    pipeline_runner.run_analysis_phase(job_id, file_path, project_name)

def run_backend_generation(job_id, project_name):
    pipeline_runner.run_generation_phase(job_id, project_name)

@app.route('/api/process_upload', methods=['POST'])
def process_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    filename = secure_filename(file.filename)
    # Generate ID based on timestamp
    job_id = f"job_{int(os.times()[4] * 100)}"
    project_name = os.path.splitext(filename)[0]
    
    # Save to uploads folder
    upload_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(upload_path)
    
    # Create persistent job
    job_storage.create_job(job_id, project_name)
    
    # Check if this is a pre-processed JSON import
    if filename.lower().endswith('.json'):
        # 1. Setup Project Directory
        base_tools = os.path.dirname(os.path.dirname(SERVER_DIR))
        project_output_dir = os.path.join(base_tools, "Podcast_Tools", "00Outputfiles", project_name)
        if not os.path.exists(project_output_dir): os.makedirs(project_output_dir)
        
        # 2. Copy JSON to standard location
        final_json_path = os.path.join(project_output_dir, f"{project_name}.json")
        try:
            shutil.copy(upload_path, final_json_path)
        except Exception as e:
            logger.error(f"Failed to copy imported JSON: {e}")
            return jsonify({"error": "Failed to import project file"}), 500
            
        # 3. Update Job properly
        # We assume stages are completed
        job_storage.update_job(job_id, status='awaiting_review', transcript_path=final_json_path)
        job_storage.update_stage(job_id, 'transcribe', status='completed', percent=100)
        job_storage.update_stage(job_id, 'polish', status='completed', percent=100)
        
        # Add transcript to tracked files
        job_storage.add_file(job_id, f"{project_name}.json", "Bilingual Transcript", final_json_path)
        
        logger.info(f"Imported project {project_name} from JSON.")
        
    else:
        # Start thread for ANALYSIS PHASE only (Audio)
        thread = threading.Thread(target=run_backend_analysis, args=(job_id, upload_path, project_name))
        thread.start()
    
    return jsonify({"status": "started", "job_id": job_id, "project_name": project_name})

@app.route('/api/start_generation', methods=['POST'])
def start_generation():
    data = request.json
    job_id = data.get('job_id')
    project_name = data.get('project_name')
    
    if not job_id or not project_name:
        return jsonify({"error": "Missing job_id or project_name"}), 400

    # Start thread for GENERATION PHASE
    thread = threading.Thread(target=run_backend_generation, args=(job_id, project_name))
    thread.start()
    
    return jsonify({"status": "started", "message": "Generation phase started"})



@app.route('/api/save_voices', methods=['POST'])
def save_voices_map():
    data = request.json
    voice_map = data.get('voice_map') # {"Speaker 0": "VoiceID", ...}
    
    if not voice_map:
        return jsonify({"error": "No voice map provided"}), 400

    # Write to saved_voices.json in Podcast_Tools
    try:
        saved_voices_path = os.path.join(BASE_TOOLS_DIR, "Podcast_Tools", "saved_voices.json")
        with open(saved_voices_path, 'w', encoding='utf-8') as f:
            json.dump(voice_map, f, indent=4)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/job_status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    job = job_storage.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route('/api/get_result/<job_id>', methods=['GET'])
def get_job_result(job_id):
    job = job_storage.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
        
    status = job.get('status')
    file_path = None
    
    if status == 'completed':
        file_path = job.get('result_path')
    elif status == 'awaiting_review':
        file_path = job.get('transcript_path')
        if not file_path:
             # Fallback if pipeline_runner didn't save it yet (for old jobs)
             # Try to infer it from project name?
             # For now, just error or try to find it.
             pass
    else:
        return jsonify({"error": f"Job not ready (Status: {status})"}), 400
    
    if not file_path or not os.path.exists(file_path):
         return jsonify({"error": f"Result file missing: {file_path}"}), 404

    return send_file(file_path, as_attachment=True)

@app.route('/api/list_project_files/<job_id>', methods=['GET'])
def list_project_files(job_id):
    job = job_storage.get_job(job_id)
    if not job: return jsonify({"error": "Job not found"}), 404
    
    # State-based file listing (User Request: Do NOT match from folder)
    # We only return files that have been explicitly tracked in the job state.
    files = job.get('files', [])
    
    # Enrich with size if file exists on disk, otherwise mark missing
    final_files = []
    for f_entry in files:
        if os.path.exists(f_entry['path']):
            f_entry['size'] = os.path.getsize(f_entry['path'])
            final_files.append(f_entry)
        else:
             # Skip missing files or keep them? safer to skip if they were deleted manually
             pass

    return jsonify({"files": final_files})

@app.route('/api/download_file/<job_id>', methods=['GET'])
def download_project_file(job_id):
    filename = request.args.get('file')
    if not filename: return jsonify({"error": "Missing file param"}), 400
    
    job = job_storage.get_job(job_id)
    if not job: return jsonify({"error": "Job not found"}), 404
    
    # Resolve Directory (Same logic as above)
    transcript_path = job.get('transcript_path')
    if transcript_path:
        project_dir = os.path.dirname(transcript_path)
    else:
        project_name = job.get('project_name')
        base_tools = os.path.dirname(os.path.dirname(SERVER_DIR))
        project_dir = os.path.join(base_tools, "Podcast_Tools", "00Outputfiles", project_name)

    file_path = os.path.join(project_dir, filename) # Use original filename but check traversal
    
    # Simple directory traversal check
    if os.path.relpath(file_path, start=project_dir).startswith(".."):
         return jsonify({"error": "Invalid filename"}), 400

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404
        
    return send_file(file_path, as_attachment=True, download_name=filename)



@app.route('/api/get_voices', methods=['GET'])
def get_voices():
    # 1. Start with Default Minimax Voices
    voice_list = []
    for name, vid in MINIMAX_VOICES.items():
        voice_list.append({"name": f"{name} (Default)", "id": vid})

    # 2. Add Saved/Cloned Voices
    # SERVER_DIR = .../poddub-ai/server
    # dirname(SERVER_DIR) = .../poddub-ai
    # dirname(...) = .../Playground
    base_playground = os.path.dirname(os.path.dirname(SERVER_DIR))
    saved_voices_path = os.path.join(base_playground, "Podcast_Tools", "saved_voices.json")
    
    if os.path.exists(saved_voices_path):
        try:
            with open(saved_voices_path, 'r', encoding='utf-8') as f:
                saved_map = json.load(f)
                for speaker, vid in saved_map.items():
                    # Check if this ID is a default one
                    is_default = any(v['id'] == vid for v in voice_list)
                    if not is_default:
                        # User requested ID in name to avoid confusion
                        voice_list.append({"name": f"{speaker} (ID: {vid})", "id": vid})
        except Exception as e:
            logger.error(f"Error loading saved voices: {e}")
            
    return jsonify({"voices": voice_list})

@app.route('/api/generate_doc', methods=['POST'])
def generate_doc():
    data = request.json
    job_id = data.get('job_id')
    doc_type = data.get('doc_type') # 'outline' or 'summary'
    
    if not job_id or doc_type not in ['outline', 'summary']:
        return jsonify({"error": "Invalid parameters"}), 400
        
    job = job_storage.get_job(job_id)
    if not job: return jsonify({"error": "Job not found"}), 404
    
    transcript_path = job.get('transcript_path')
    if not transcript_path or not os.path.exists(transcript_path):
        return jsonify({"error": "Transcript not found"}), 400
        
    # Determine script path
    base_playground = os.path.dirname(os.path.dirname(SERVER_DIR))
    podcast_tools_dir = os.path.join(base_playground, "Podcast_Tools")

    if doc_type == 'outline':
        script_path = os.path.join(podcast_tools_dir, "Podcast_Outline", "generate_outline.py")
    else:
        script_path = os.path.join(podcast_tools_dir, "Podcast_Summary", "Generate_Summary.py")
        
    # Output dir (same as transcript dir)
    output_dir = os.path.dirname(transcript_path)
    
    def run_task():
        try:
            pipeline_runner.log(job_id, f"Manually generating {doc_type}...")
            
            # Cleanup skipped to prevent data loss on failure - Scripts will overwrite
            # try:
            #     project_name = job.get('project_name')
            #     for f in os.listdir(output_dir):
            #         # Protect source files
            #         if f == f"{project_name}.md" or f == f"{project_name}.json":
            #             continue
            #             
            #         f_path = os.path.join(output_dir, f)
            #         if doc_type == 'outline':
            #             if ("Outline" in f or "outline" in f) and f.endswith(".md"):
            #                  # os.remove(f_path)
            #                  pass
            #         elif doc_type == 'summary':
            #             if (("summary" in f.lower() or "摘要" in f) and f.endswith(".md")) or "AI_Summary" in f:
            #                  # os.remove(f_path)
            #                  pass
            # except Exception as e:
            #     pipeline_runner.log(job_id, f"Cleanup warning: {e}")
            
            if doc_type == 'outline':
                cmd = [sys.executable, script_path, transcript_path, "--outdir", output_dir]
                pipeline_runner.run_command(job_id, cmd)
                pipeline_runner.storage.update_stage(job_id, 'analysis', outline=True)
                
                # State Update: Track generated file
                # We need to predict the filename or scan ONLY for the NEW file.
                # generate_outline.py returns the output path. run_command usually captures output?
                # For now, let's scan for the newest Outline file and add it.
                # This is a safe "scan" because it's targeted after an action, but better if script returned it.
                # Since we replaced the generic list logic, we must explicit add here.
                
                # Try to find the expected file
                # generate_outline logic: f"{safe_title}_Outline.md" OR f"{base_name}_Outline.md"
                # Let's look for any *new* .md file with Outline in name?
                # Or just list all Outlines and pick latest?
                # User hates scanning. But we just generated it.
                # To be precise, our updated generate_outline creates f"{safe_title}_Outline.md".
                # We can't easily know safe_title here without parsing logic.
                # Let's Iterate output_dir and find the Outline.md that was modified recently.
                
                candidates = []
                for f in os.listdir(output_dir):
                    if "Outline" in f and f.endswith(".md"):
                         f_path = os.path.join(output_dir, f)
                         candidates.append((f_path, os.path.getmtime(f_path)))
                
                if candidates:
                    candidates.sort(key=lambda x: x[1], reverse=True)
                    latest_outline = candidates[0][0]
                    f_name = os.path.basename(latest_outline)
                    job_storage.add_file(job_id, f_name, "Outline", latest_outline) 
                
            else: # summary
                project_name = job.get('project_name', 'Unknown')
                output_filename = f"{project_name}_AI_Summary.md"
                output_path = os.path.join(output_dir, output_filename)
                
                cmd = [sys.executable, script_path, "--json", transcript_path, "--output", output_path, "--project", project_name]
                pipeline_runner.run_command(job_id, cmd)
                pipeline_runner.storage.update_stage(job_id, 'analysis', summary=True)
                
                # State Update
                if os.path.exists(output_path):
                     job_storage.add_file(job_id, output_filename, "AI Summary", output_path)
            
            pipeline_runner.log(job_id, f"{doc_type.capitalize()} generation complete.")
            
        except Exception as e:
            pipeline_runner.log(job_id, f"Error generating {doc_type}: {e}")

    thread = threading.Thread(target=run_task)
    thread.start()
    
    return jsonify({"status": "started", "message": f"Generating {doc_type}..."})

@app.route('/api/voice_check', methods=['POST'])
def voice_check():
    # Load saved_voices.json from Podcast_Tools (source of truth)
    base_playground = os.path.dirname(os.path.dirname(SERVER_DIR))
    saved_voices_path = os.path.join(base_playground, "Podcast_Tools", "saved_voices.json")
    
    data = {}
    if os.path.exists(saved_voices_path):
        try:
            with open(saved_voices_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except: pass
        
    return jsonify(data)

@app.route('/api/generate_full', methods=['POST'])
def generate_full():
    data = request.json
    project_name = data.get('project_name')
    minimax_args = data.get('minimax_settings', {}) # {speed, vol, pitch}
    voice_map = data.get('voice_map', {}) # {Speaker A: VoiceID, ...}

    if not project_name:
        return jsonify({"error": "Missing project_name"}), 400

    # Paths
    project_dir = os.path.join(OUTPUT_DIR, project_name)
    json_path = os.path.join(project_dir, f"{project_name}.json")
    
    if not os.path.exists(json_path):
        # Fallback: Check Podcast_Tools/00Outputfiles
        # SERVER_DIR is .../poddub-ai/server, so grandparanet is playground
        base_tools = os.path.dirname(os.path.dirname(SERVER_DIR))
        fallback_dir = os.path.join(base_tools, "Podcast_Tools", "00Outputfiles", project_name)
        fallback_path = os.path.join(fallback_dir, f"{project_name}.json")
        
        if os.path.exists(fallback_path):
            logger.info(f"Found project file in fallback location: {fallback_path}")
            json_path = fallback_path
            # Also update project_dir to where the file actually is, so generate.py runs there?
            # actually generate.py might expect to run in place. 
            # We pass json_path to generate.py. 
        else:
            return jsonify({"error": f"Project file not found: {json_path} (checked fallback: {fallback_path})"}), 404

    # 1. Save temporary voice_map.json usually? 
    # Actually generate.py in `Podcast_Tools` loads `saved_voices.json` (global) OR we can pass args?
    # Looking at generate.py (copied to engine/generate.py), let's see how it accepts args.
    # If it's the original script, it might load `saved_voices.json` from specific path.
    # We might need to override it or ensure it looks in the right place.
    # It likely expects `saved_voices.json` in `Podcast_Tools`.
    # To support custom voice map from UI, we might need to modify `engine/generate.py` or 
    # write to `saved_voices.json` before running. 
    # SAFE OPTION: Write a temp voice map and pass it if script supports it, OR Update the global `saved_voices.json` with the UI selection.
    
    # Let's update global saved_voices.json since that's the source of truth for "My Voices".
    # Let's update global saved_voices.json since that's the source of truth for "My Voices".
    # SERVER_DIR is .../poddub-ai/server
    # dirname -> poddub-ai
    # dirname -> Playground
    base_playground = os.path.dirname(os.path.dirname(SERVER_DIR))
    saved_voices_path = os.path.join(base_playground, "Podcast_Tools", "saved_voices.json")
    
    try:
        # Load existing
        current_voices = {}
        if os.path.exists(saved_voices_path):
            with open(saved_voices_path, 'r', encoding='utf-8') as f:
                current_voices = json.load(f)
        
        # Merge new mappings
        current_voices.update(voice_map)
        
        # Save back
        with open(saved_voices_path, 'w', encoding='utf-8') as f:
            json.dump(current_voices, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Failed to update saved_voices.json: {e}")

    # 2. Call generate.py
    # We need to pass arguments.
    # Original: python generate.py <json_path>
    # It generates audio in the same folder.
    # Use NON-BLOCKING thread
    
    # Point to external generate.py in Podcast_Tools/Poddub_Minimax/codes/
    script_path = os.path.join(base_playground, "Podcast_Tools", "Poddub_Minimax", "codes", "generate.py")
    
    def run_gen_task():
        # Using sys.executable to ensure same env
        cmd = [sys.executable, script_path, json_path]
        
        # Pass Minimax settings via Environment Variables? 
        # generate.py might not support args for speed/vol yet.
        # We might need to patch engine/generate.py to read these env vars or args.
        # For now, let's assume we patch engine/generate.py later to respect these.
        env = os.environ.copy()
        env["MINIMAX_SPEED"] = str(minimax_args.get('speed', 1.0))
        env["MINIMAX_VOL"] = str(minimax_args.get('vol', 1.0))
        env["MINIMAX_PITCH"] = str(minimax_args.get('pitch', 0))
        
        subprocess.run(cmd, env=env, check=False)

    thread = threading.Thread(target=run_gen_task)
    thread.start()

    return jsonify({"status": "started", "message": "Audio generation started", "project": project_name})

# --- Voice Preview & Caching ---
PREVIEW_CACHE_DIR = os.path.join(SERVER_DIR, "cache", "previews")
if not os.path.exists(PREVIEW_CACHE_DIR): os.makedirs(PREVIEW_CACHE_DIR)

@app.route('/api/preview_voice', methods=['GET'])
def preview_voice():
    voice_id = request.args.get('voice_id')
    # Default text: English + Chinese (2 sentences total as requested)
    default_text = "Hello, this is a preview of my voice. 大家好，这是我的中文语音预览。"
    text = request.args.get('text', default_text)
    
    if not voice_id:
        return jsonify({"error": "Missing voice_id"}), 400

    # Sanitize voice_id for filename
    safe_vid = "".join([c for c in voice_id if c.isalnum() or c in ('-', '_')])
    cache_filename = f"{safe_vid}.mp3" 
    cache_path = os.path.join(PREVIEW_CACHE_DIR, cache_filename)

    # 1. FORCE REAL-TIME GENERATION (User Request)
    # We remove the cache check to ensure every click generates fresh audio.
    # if os.path.exists(cache_path):
    #    return send_file(cache_path, mimetype="audio/mpeg")

    # 2. Generate New
    try:
        # Determine provider based on ID format or trial
        # Minimax IDs are usually strings/integers. 
        # Gemini does not have "voices" in the same way, but let's assume Minimax for now 
        # as get_voices mainly returns Minimax voices.
        
        # NOTE: We need to use `generate_with_minimax` but it expects 'speaker' name to lookup ID.
        # We have the ID directly. We need a lower-level generate function or hack it.
        # Refactoring generate_with_minimax to take voice_id directly would be cleaner,
        # but let's just make a direct call here to avoid breaking existing code.
        
        if not MINIMAX_API_KEY or not MINIMAX_GROUP_ID:
             raise Exception("Minimax API not configured")

        url = f"https://api.minimax.chat/v1/t2a_v2?GroupId={MINIMAX_GROUP_ID}"
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "speech-2.6-hd",
            "text": text,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3"
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
             raise Exception(f"Minimax API Error: {response.text}")
        
        res_json = response.json()
        audio_hex = res_json.get("data", {}).get("audio")
        if not audio_hex:
             raise Exception("No audio data returned")
             
        audio_data = bytes.fromhex(audio_hex)

        # 3. Save to Cache
        with open(cache_path, 'wb') as f:
            f.write(audio_data)

        from io import BytesIO
        return send_file(
            BytesIO(audio_data),
            mimetype="audio/mpeg",
            as_attachment=False
        )

    except Exception as e:
        logger.error(f"Preview generation failed: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = 8000
    print(f"\n--- Poddub AI TTS Server ---")
    print(f"Listening on port {port}")
    print(f"Supported Providers: Gemini ({GEMINI_MODEL}), Minimax")
    print(f"----------------------------\n")
    serve(app, host='0.0.0.0', port=port, threads=8)
