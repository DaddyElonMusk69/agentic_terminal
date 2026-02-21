import asyncio
import base64
import httpx

async def main():
    api_url = "https://freeimage.host/api/1/upload"
    # Needs a real API key to test, let's see if there is one in .env
    # For now, I'll just print the error without key if possible, but freeimage requires key.
    # Where does the user store the API key? `BACKEND_PROMPT_IMAGE_FREEIMAGE_API_KEY`
    import os
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("BACKEND_PROMPT_IMAGE_FREEIMAGE_API_KEY")
    if not api_key:
        # Check DB or fallback
        print("No API key found in env")
        return
        
    image_bytes = b"dummy image content just for testing"
    payload = {
        "key": api_key,
        "source": base64.b64encode(image_bytes).decode("ascii"),
        "format": "json",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, data=payload)
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")

asyncio.run(main())
