
import os
import asyncio
import logging
from google import genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to find API key
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env.local')
if os.path.exists(env_path) and not os.environ.get("GEMINI_API_KEY"):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip().startswith("GEMINI_API_KEY="):
                os.environ["GEMINI_API_KEY"] = line.strip().split("=", 1)[1]
                logger.info("Loaded GEMINI_API_KEY")
                break

API_KEY = os.environ.get("GEMINI_API_KEY")

async def test_connect(model_id):
    logger.info(f"Testing connection to model: {model_id}")
    client = genai.Client(api_key=API_KEY, http_options={'api_version': 'v1alpha'})
    config = { "response_modalities": ["AUDIO"] }
    
    try:
        async with client.aio.live.connect(model=model_id, config=config) as session:
            logger.info("Connection successful!")
            await session.send(input="Hello", end_of_turn=True)
            async for response in session.receive():
                if response.server_content:
                    logger.info("Received content")
                    break
        print(f"SUCCESS: {model_id} works with Live API")
    except Exception as e:
        print(f"FAILURE: {model_id} failed with error: {e}")

if __name__ == "__main__":
    if not API_KEY:
        print("Error: No API Key")
    else:
        # Test the user requested model
        asyncio.run(test_connect("gemini-2.5-flash-tts"))
        
        # Test the one known to work?
        # asyncio.run(test_connect("gemini-2.5-flash-native-audio-preview-12-2025"))
