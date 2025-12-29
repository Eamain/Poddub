
import os
import json
import threading
import time
from datetime import datetime

class JobStorage:
    def __init__(self, jobs_dir):
        self.jobs_dir = jobs_dir
        if not os.path.exists(self.jobs_dir):
            os.makedirs(self.jobs_dir)
        self.lock = threading.Lock()

    def _get_job_dir(self, job_id):
        job_dir = os.path.join(self.jobs_dir, job_id)
        if not os.path.exists(job_dir):
            os.makedirs(job_dir)
        return job_dir

    def _get_status_file(self, job_id):
        return os.path.join(self._get_job_dir(job_id), "status.json")
        
    def _get_log_file(self, job_id):
        return os.path.join(self._get_job_dir(job_id), "process.log")

    def create_job(self, job_id, project_name):
        status = {
            "id": job_id,
            "project_name": project_name,
            "status": "pending",
            "progress": 0,
            "stages": {
                "transcribe": {"status": "pending", "percent": 0},
                "polish": {"status": "pending", "percent": 0},
                "analysis": {"status": "pending", "outline": False, "summary": False},
                "generate": {"status": "pending", "percent": 0}
            },
            "created_at": str(datetime.now()),
            "last_updated": str(datetime.now()),
            "error": None
        }
        with self.lock:
            with open(self._get_status_file(job_id), 'w', encoding='utf-8') as f:
                json.dump(status, f, indent=2)
            # Create empty log file
            open(self._get_log_file(job_id), 'w').close()
        return job_id

    def update_job(self, job_id, **kwargs):
        with self.lock:
            file_path = self._get_status_file(job_id)
            if not os.path.exists(file_path): return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update fields
            for k, v in kwargs.items():
                data[k] = v
                
            data['last_updated'] = str(datetime.now())
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

    def update_stage(self, job_id, stage_key, **kwargs):
        """Updates a specific stage (e.g. 'transcribe') with kwargs"""
        with self.lock:
            file_path = self._get_status_file(job_id)
            if not os.path.exists(file_path): return
            
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'stages' not in data:
                data['stages'] = {}
            if stage_key not in data['stages']:
                data['stages'][stage_key] = {}
            
            for k, v in kwargs.items():
                data['stages'][stage_key][k] = v
                
            data['last_updated'] = str(datetime.now())
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)

    def append_log(self, job_id, message):
        # Append to log file directly
        # No lock needed usually for append, but let's be safe if high concurrency (unlikely for single job)
        log_file = self._get_log_file(job_id)
        timestamp = datetime.now().strftime("%H:%M:%S")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")

    def get_job(self, job_id):
        status_path = self._get_status_file(job_id)
        log_path = self._get_log_file(job_id)
        
        if not os.path.exists(status_path): return None
        
        with open(status_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Read logs (limit to last 100 lines to avoid huge payload)
        logs = []
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                logs = f.readlines()
        
        data['logs'] = [l.strip() for l in logs]
        return data
