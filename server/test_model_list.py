
import os
import logging
from google import genai

logging.basicConfig(level=logging.INFO)

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.local')
if os.path.exists(env_path) and not os.environ.get("GEMINI_API_KEY"):
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
            if "tts" in m.name.lower() or "flash" in m.name.lower():
                print(f"Name: {m.name}")
                print(f"Methods: {m.supported_generation_methods}")
    except Exception as e:
        print(f"Error listing {version}: {e}")
