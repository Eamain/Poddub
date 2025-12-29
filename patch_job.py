
import json
import os

path = r"server/jobs/job_0/status.json"
transcript_path = r"D:\MingggSync\Playground\Podcast_Tools\00Outputfiles\Joe_Rogan_Test_1min\Joe_Rogan_Test_1min.json"

if os.path.exists(path):
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    data['transcript_path'] = transcript_path
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print("Patched job_0 successfully.")
else:
    print("job_0 status file not found.")
