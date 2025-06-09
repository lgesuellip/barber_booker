import os
import httpx
from mcp.server import FastMCP

API_URL = os.getenv("AGENT_API_URL", "http://localhost:8001/agent")
API_TOKEN = os.getenv("AGENT_API_TOKEN", "")

server = FastMCP(
    name="cloudflare_proxy",
    instructions="Proxy to the upstream agent API via Cloudflare",
)

@server.tool()
async def agent_query(message: str) -> str:
    """Forward a message to the upstream agent API."""
    headers = {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}
    async with httpx.AsyncClient() as client:
        resp = await client.post(API_URL, json={"message": message}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        # Expect the remote API to return {'response': 'text'}
        return data.get("response", "")

app = server
