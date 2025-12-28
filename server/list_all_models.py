
import os
from google import genai

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.local')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.strip().split("=", 1)[1]
                break

API_KEY = os.environ.get("GEMINI_API_KEY")

for version in ['v1beta', 'v1alpha']:
    print(f"\n--- VERSION: {version} ---")
    try:
        client = genai.Client(api_key=API_KEY, http_options={'api_version': version})
        for m in client.models.list():
            print(f"Model: {m.name}")
    except Exception as e:
        print(f"Error {version}: {e}")
