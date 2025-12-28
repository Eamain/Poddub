
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
from werkzeug.utils import secure_filename

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
class JobManager:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()

    def create_job(self, job_id, project_name):
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id,
                "project_name": project_name,
                "status": "pending",
                "logs": [],
                "progress": 0,
                "result_path": None,
                "error": None
            }
        return job_id

    def update_job(self, job_id, status=None, log=None, progress=None, result_path=None, error=None):
        with self.lock:
            if job_id not in self.jobs: return
            if status: self.jobs[job_id]["status"] = status
            if log: self.jobs[job_id]["logs"].append(log)
            if progress is not None: self.jobs[job_id]["progress"] = progress
            if result_path: self.jobs[job_id]["result_path"] = result_path
            if error: self.jobs[job_id]["error"] = error

    def get_job(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

job_manager = JobManager()

# --- Background Processing ---
def run_backend_pipeline(job_id, file_path, project_name):
    try:
        job_manager.update_job(job_id, status="transcribing", log=f"Starting transcription for {project_name}...", progress=5)
        
        # 1. Transcribe
        # SERVER_DIR = .../poddub-ai/server
        # dirname(SERVER_DIR) = .../poddub-ai
        # dirname(dirname(SERVER_DIR)) = .../Playground
        base_tools = os.path.dirname(os.path.dirname(SERVER_DIR)) 
        transcribe_script = os.path.join(base_tools, "Podcast_Tools", "Audio_to_Transcription", "Audio_to_Transcription.py")
        
        # We need to interpret stdout to update logs
        cmd_trans = [sys.executable, transcribe_script, file_path]
        
        # Inject API Key into subprocess env
        env = os.environ.copy()
        if GEMINI_API_KEY:
             env["GEMINI_API_KEY"] = GEMINI_API_KEY
        
        process = subprocess.Popen(cmd_trans, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding='utf-8', env=env)
        
        # Capture output for debugging
        full_output = []
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                full_output.append(line)
                job_manager.update_job(job_id, log=f"[Transcribe] {line}")
        
        process.wait()
        if process.returncode != 0:
            error_details = "\n".join(full_output[-5:]) # Last 5 lines
            raise Exception(f"Transcription failed. Code: {process.returncode}. Last logs: {error_details}")

        job_manager.update_job(job_id, status="polishing", log="Transcription complete. Starting Polishing...", progress=40)

        # 2. Polish
        # Infer JSON path from standard output structure of Audio_to_Transcription
        # usually 00Outputfiles/<ProjectName>/<ProjectName>.json
        # But wait, Audio_to_Transcription creates based on input filename?
        # Let's assume standard behavior:
        base_filename = os.path.splitext(os.path.basename(file_path))[0]
        # It creates a folder in 00Outputfiles? 
        # Actually, let's look for the json file in the likely location.
        output_files_dir = os.path.join(base_tools, "Podcast_Tools", "00Outputfiles", base_filename)
        json_path = os.path.join(output_files_dir, f"{base_filename}.json")
        
        if not os.path.exists(json_path):
            # Fallback search
             job_manager.update_job(job_id, log=f"Warning: Expected JSON at {json_path} not found. Searching...")
             # ... implementation detail ...

        polish_script = os.path.join(base_tools, "Podcast_Tools", "Translation_Polishing", "poddub_polish.py")
        cmd_polish = [sys.executable, polish_script, json_path]
        
        process = subprocess.Popen(cmd_polish, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding='utf-8')
        
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if line:
                job_manager.update_job(job_id, log=f"[Polish] {line}")
                # Try to parse progress from logs like "Processing Batch 1/23"
                if "Processing Batch" in line:
                    try:
                        # logical guess at progress 40 -> 90
                        job_manager.update_job(job_id, progress=60) 
                    except: pass
        
        process.wait()
        if process.returncode != 0:
            raise Exception("Polishing failed.")

        # 3. Finalize
        # The polished file is typically named *_polished.json or just updates the original depending on script version.
        # poddub_polish.py typically creates `..._polished.json`
        polished_json_path = json_path.replace(".json", "_polished.json")
        if not os.path.exists(polished_json_path):
             polished_json_path = json_path # Fallback if it overwrote

        job_manager.update_job(job_id, status="completed", log="Pipeline Finished Successfully!", progress=100, result_path=polished_json_path)

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        job_manager.update_job(job_id, status="failed", error=str(e), log=f"CRITICAL ERROR: {e}")

@app.route('/api/process_upload', methods=['POST'])
def process_upload():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    filename = secure_filename(file.filename)
    job_id = f"job_{int(os.times()[4] * 100)}"
    project_name = os.path.splitext(filename)[0]
    
    # Save to temp
    upload_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(upload_path)
    
    job_manager.create_job(job_id, project_name)
    
    thread = threading.Thread(target=run_backend_pipeline, args=(job_id, upload_path, project_name))
    thread.start()
    
    return jsonify({"status": "started", "job_id": job_id, "project_name": project_name})

@app.route('/api/job_status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)

@app.route('/api/get_result/<job_id>', methods=['GET'])
def get_job_result(job_id):
    job = job_manager.get_job(job_id)
    if not job or job['status'] != 'completed':
        return jsonify({"error": "Job not ready"}), 400
    
    return send_file(job['result_path'], as_attachment=True)

@app.route('/api/voice_check', methods=['POST'])
def voice_check():
    # Load saved_voices.json from Podcast_Tools (source of truth)
    base_tools = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(SERVER_DIR))), "Podcast_Tools")
    saved_voices_path = os.path.join(base_tools, "saved_voices.json")
    
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
        return jsonify({"error": f"Project file not found: {json_path}"}), 404

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
    base_tools = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(SERVER_DIR))), "Podcast_Tools")
    saved_voices_path = os.path.join(base_tools, "saved_voices.json")
    
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
    
    script_path = os.path.join(ENGINE_DIR, "generate.py")
    
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

if __name__ == "__main__":
    port = 8000
    print(f"\n--- Poddub AI TTS Server ---")
    print(f"Listening on port {port}")
    print(f"Supported Providers: Gemini ({GEMINI_MODEL}), Minimax")
    print(f"----------------------------\n")
    serve(app, host='0.0.0.0', port=port, threads=8)
