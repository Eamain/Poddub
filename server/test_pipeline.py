import requests
import time
import os
import sys

# Configuration
BASE_URL = "http://localhost:8000"
TEST_FILE = "d:\\MingggSync\\Playground\\Temp\\20251223\\temp_chunk_1.mp3"

def run_test():
    if not os.path.exists(TEST_FILE):
        print(f"Error: Test file not found at {TEST_FILE}")
        return

    print(f"--- Starting Pipeline Verification ---\nFile: {TEST_FILE}")
    
    # 1. Upload
    print("\n1. Uploading File...")
    with open(TEST_FILE, 'rb') as f:
        files = {'file': f}
        try:
            res = requests.post(f"{BASE_URL}/api/process_upload", files=files)
            if res.status_code != 200:
                print(f"Upload Failed: {res.text}")
                return
            data = res.json()
            job_id = data['job_id']
            print(f"Upload Success. Job ID: {job_id}")
        except Exception as e:
            print(f"Connection Error: {e}")
            return

    # 2. Poll Status
    print("\n2. Polling Status...")
    while True:
        res = requests.get(f"{BASE_URL}/api/job_status/{job_id}")
        status = res.json()
        
        # Print Progress Bar (simplified)
        stages = status.get('stages', {})
        t_pct = stages.get('transcribe', {}).get('percent', 0)
        p_pct = stages.get('polish', {}).get('percent', 0)
        
        print(f"\rStatus: {status['status']} | Transcribe: {t_pct}% | Polish: {p_pct}%", end="")
        
        if status['status'] == 'awaiting_review':
            print("\n\n3. Reached 'awaiting_review'. Analysis Complete!")
            print("Detected Stages:")
            print(status['stages'])
            break
            
        if status['status'] == 'failed':
            print(f"\n\nPipeline Failed: {status.get('error')}")
            break
            
        time.sleep(2)

    # 3. Simulate Voice Map Submission (optional, if we want to test generation)
    # For now, we stop here to verify Analysis Phase.

if __name__ == "__main__":
    run_test()
