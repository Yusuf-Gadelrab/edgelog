import httpx
import json

async def score_sentiment(text: str) -> dict:
    """
    Uses local qwen3-fast to score real-time news/tweets for sentiment.
    Returns JSON with bullish/bearish score (-1.0 to 1.0).
    """
    prompt = f"""Analyze the financial sentiment of this text.
Return ONLY valid JSON exactly matching this schema: {{"score": float (-1.0 to 1.0), "reason": "short explanation"}}
Text: {text}"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen3-fast",
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=5.0
            )
            data = resp.json()
            return json.loads(data.get("response", "{}"))
    except Exception as e:
        return {"score": 0.0, "reason": str(e)}
