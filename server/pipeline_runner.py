
import os
import sys
import subprocess
import shutil

class PipelineRunner:
    def __init__(self, job_storage, base_tools_dir):
        self.storage = job_storage
        self.base_tools = base_tools_dir
        self.last_result_path = None
        
        # Define paths to external scripts
        self.script_transcribe = os.path.join(self.base_tools, "Podcast_Tools", "Audio_to_Transcription", "Audio_to_Transcription.py")
        self.script_polish = os.path.join(self.base_tools, "Podcast_Tools", "Translation_Polishing", "poddub_polish.py")
        # Use the MINIMAX generate.py
        self.script_generate = os.path.join(self.base_tools, "Podcast_Tools", "Poddub_Minimax", "codes", "generate.py")

    def log(self, job_id, msg):
        print(f"[Job {job_id}] {msg}")
        self.storage.append_log(job_id, msg)

    def run_command(self, job_id, command_args, stage_key=None, env=None):
        """Runs a command, streams output, and parses progress via Regex."""
        import re
        
        # Ensure unbuffered output
        if command_args[0] == sys.executable:
             if '-u' not in command_args:
                 command_args.insert(1, '-u')
        
        process = subprocess.Popen(
            command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding='utf-8', # Force UTF-8
            env=env
        )
        
        # Regex Patterns
        # Transcribe: "Processing chunk 1/4"
        # Polish: "Processing Batch 1/5"
        # Generate: "Generating segment 1/10" (Hypothetical, need to verify or just use generic)
        
        re_chunk = re.compile(r"Processing chunk (\d+)/(\d+)")
        re_batch = re.compile(r"Processing Batch (\d+)/(\d+)")
        re_gen = re.compile(r"Generating segment (\d+)/(\d+)")
        re_done = re.compile(r"Done! Output: (.+)")
        
        for line in iter(process.stdout.readline, ''):
            line = line.strip()
            if not line: continue
            
            self.storage.append_log(job_id, line)
            
            # Progress Parsing
            if stage_key == 'transcribe':
                m = re_chunk.search(line)
                if m:
                    curr, total = int(m.group(1)), int(m.group(2))
                    pct = int((curr / total) * 100)
                    self.storage.update_stage(job_id, 'transcribe', percent=pct, current=curr, total=total)
            
            elif stage_key == 'polish':
                m = re_batch.search(line)
                if m:
                    curr, total = int(m.group(1)), int(m.group(2))
                    pct = int((curr / total) * 100)
                    self.storage.update_stage(job_id, 'polish', percent=pct, current=curr, total=total)

            elif stage_key == 'generate':
                m = re_gen.search(line)
                if m:
                    curr, total = int(m.group(1)), int(m.group(2))
                    pct = int((curr / total) * 100)
                    self.storage.update_stage(job_id, 'generate', percent=pct, current=curr, total=total)
            
            # Check for result path
            m_done = re_done.search(line)
            if m_done:
                self.last_result_path = m_done.group(1).strip()

        process.wait()
        return process.returncode

    def run_analysis_phase(self, job_id, upload_path, project_name):
        """Runs Transcribe -> Polish -> Outline -> Summary. Stops before Generation."""
        try:
            self.storage.update_job(job_id, status="processing")
            self.log(job_id, f"--- Starting Analysis Phase for {project_name} ---")

            # --- PREP PATHS ---
            output_base = os.path.join(self.base_tools, "Podcast_Tools", "00Outputfiles", project_name)
            expected_json = os.path.join(output_base, f"{project_name}.json")
            
            # --- STEP 1: TRANSCRIBE ---
            if os.path.exists(expected_json):
                self.log(job_id, ">> Step 1: Transcribe - SKIPPED (File exists)")
                self.storage.update_stage(job_id, 'transcribe', status="completed", percent=100)
            else:
                self.log(job_id, ">> Step 1: Transcribe - STARTED")
                self.storage.update_stage(job_id, 'transcribe', status="active", percent=0)
                
                env = os.environ.copy()
                env["PYTHONIOENCODING"] = "utf-8"
                
                ret = self.run_command(job_id, [sys.executable, self.script_transcribe, upload_path], stage_key='transcribe', env=env)
                if ret != 0: raise Exception("Transcription script failed.")
                
                self.storage.update_stage(job_id, 'transcribe', status="completed", percent=100)
                self.log(job_id, ">> Step 1: Transcribe - COMPLETED")

            # --- STEP 2: POLISH ---
            # Verify JSON exists
            if not os.path.exists(expected_json):
                 raise Exception(f"Expected JSON not found at: {expected_json}")
            
            self.log(job_id, ">> Step 2: Polish - STARTED")
            self.storage.update_stage(job_id, 'polish', status="active", percent=0)
            
            ret = self.run_command(job_id, [sys.executable, self.script_polish, expected_json], stage_key='polish')
            if ret != 0: raise Exception("Polish script failed.")
            
            self.storage.update_stage(job_id, 'polish', status="completed", percent=100)
            self.log(job_id, ">> Step 2: Polish - COMPLETED")

            # --- STEP 3: CONTENT ANALYSIS (Skipped - Manual Trigger) ---
            # Moved to Review Phase as per user request.
            self.log(job_id, ">> Step 3: Content Analysis - SKIPPED (Waiting for manual trigger)")
            self.storage.update_stage(job_id, 'analysis', status="pending")

            # --- UPDATE STATUS ---
            self.storage.update_job(job_id, transcript_path=expected_json)
            self.storage.update_job(job_id, status="awaiting_review")
            self.log(job_id, "--- Analysis Phase Complete. Waiting for User Review. ---")

        except Exception as e:
            self.log(job_id, f"CRITICAL ERROR: {str(e)}")
            self.storage.update_job(job_id, status="failed", error=str(e))

    def run_generation_phase(self, job_id, project_name):
        """Runs Audio Generation. Triggered after voice selection."""
        try:
            self.storage.update_job(job_id, status="processing")
            self.log(job_id, f"--- Starting Generation Phase for {project_name} ---")
            
            output_base = os.path.join(self.base_tools, "Podcast_Tools", "00Outputfiles", project_name)
            expected_json = os.path.join(output_base, f"{project_name}.json") # Generate uses the base json usually
            
            # Generate uses voice map from saved_voices.json which should be updated by now.
            
            self.log(job_id, ">> Step 4: Audio Generation - STARTED")
            self.storage.update_stage(job_id, 'generate', status="active", percent=0)

            cmd_gen = [sys.executable, self.script_generate, "--file", expected_json, "--auto", "--no-preview"]
            
            ret = self.run_command(job_id, cmd_gen, stage_key='generate')
            if ret != 0: raise Exception("Generation script failed.")
            
            self.storage.update_stage(job_id, 'generate', status="completed", percent=100)
            self.log(job_id, ">> Step 4: Audio Generation - COMPLETED")
            
            self.storage.update_job(job_id, status="completed", progress=100, result_path=self.last_result_path)
            self.log(job_id, "Pipeline Finished Successfully.")

        except Exception as e:
            self.log(job_id, f"CRITICAL ERROR: {str(e)}")
            self.storage.update_job(job_id, status="failed", error=str(e))
