"""Webhook proxy endpoint with SSRF vulnerability."""
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class WebhookRequest(BaseModel):
    url: str
    method: str = "GET"
    headers: dict[str, str] = {}
    body: str | None = None


@app.post("/api/webhooks/test")
async def test_webhook(req: WebhookRequest):
    """Test a webhook URL by making a request to it.
    No URL validation — allows requests to internal services."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.request(
                method=req.method,
                url=req.url,
                headers=req.headers,
                content=req.body,
                timeout=10.0,
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=str(e))

    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": response.text[:1000],
    }


@app.post("/api/integrations/fetch-metadata")
async def fetch_metadata(url: str):
    """Fetch Open Graph metadata from a URL. Also vulnerable to SSRF."""
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url, timeout=5.0)
    return {"content_type": resp.headers.get("content-type"), "length": len(resp.text)}
