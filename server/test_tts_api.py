
import os
import logging
from google import genai

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper to find .env.local
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.local')
if os.path.exists(env_path) and not os.environ.get("GEMINI_API_KEY"):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.strip().split("=", 1)[1]
                break

API_KEY = os.environ.get("GEMINI_API_KEY")

MODEL = "gemini-2.5-flash"

def test_generate():
    version = 'v1beta'
    logger.info(f"Testing generation with {MODEL} using {version}...")
    
    # Text from the user's workflow
    text = "Hello, this is a test of the specific TTS model."
    prompt = f"Read this: {text}"
    config = { "response_modalities": ["AUDIO"] }

    try:
        client = genai.Client(api_key=API_KEY, http_options={'api_version': version})
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=config
        )
        
        if response.parts:
            print(f"SUCCESS: {MODEL} works with {version}!")
        else:
            print(f"FAILURE: No parts in response. Text: {response.text}")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_generate()
