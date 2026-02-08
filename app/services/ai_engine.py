import httpx

async def analyze_slack_message(text: str):
    """Uses a free Hugging Face model to detect sentiment."""
    # Example using a simple sentiment analysis API
    API_URL = "https://api-inference.huggingface.co/models/distilbert-base-uncased-finetuned-sst-2-english"
    headers = {"Authorization": f"Bearer {settings.HF_TOKEN}"}

    async with httpx.AsyncClient() as client:
        response = await client.post(API_URL, headers=headers, json={"inputs": text})
        # If sentiment is negative, we return 'HIGH_PRIORITY'
        return "HIGH" if "NEGATIVE" in str(response.json()) else "LOW"
