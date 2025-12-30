import requests
import os
import json

BASE_URL = "http://localhost:8000/api"
JSON_PATH = r"d:\MingggSync\Playground\Podcast_Tools\00Outputfiles\Joe_Rogan_Experience_2054_-_Elon_Musk\Joe_Rogan_Experience_2054_-_Elon_Musk.json"

def test_upload_json():
    print(f"--- Testing Upload JSON: {JSON_PATH} ---")
    if not os.path.exists(JSON_PATH):
        print("❌ File NOT FOUND")
        return

    files = {'file': open(JSON_PATH, 'rb')}
    try:
        res = requests.post(f"{BASE_URL}/process_upload", files=files)
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text}")
        
        if res.status_code == 200:
            job_id = res.json().get('job_id')
            print(f"✅ Job ID: {job_id}")
            return job_id
    except Exception as e:
        print(f"❌ Request Failed: {e}")
    return None

def test_list_files(job_id):
    if not job_id: return
    print(f"\n--- Testing List Files for Job {job_id} ---")
    try:
        res = requests.get(f"{BASE_URL}/list_project_files/{job_id}")
        data = res.json()
        files = data.get('files', [])
        print(f"Files Found: {len(files)}")
        for f in files:
            print(f" - {f.get('type')}: {f.get('name')}")
            
        # Check for AI Summary
        has_summary = any(f.get('type') == 'AI Summary' for f in files)
        if has_summary:
            print("❌ FAILURE: 'AI Summary' is present in file list!")
        else:
            print("✅ SUCCESS: 'AI Summary' is NOT present.")
            
    except Exception as e:
        print(f"❌ List Files Failed: {e}")

if __name__ == "__main__":
    job_id = test_upload_json()
    test_list_files(job_id)
