# Cloudflare MCP Server

This repository includes an example MCP server that can be deployed on Cloudflare Workers. The server proxies requests to an upstream agent API protected by a bearer token.

## Server code

The server lives in `src/cloudflare/mcp_server.py`. It defines a `FastMCP` instance with a single tool named `agent_query` that forwards messages to your agent API using `httpx`.

To run the server locally using the MCP CLI:

```bash
mcp run src/cloudflare/mcp_server.py:app --transport streamable-http
```

Set the following environment variables for the API location and token:

- `AGENT_API_URL` – URL of the upstream agent endpoint
- `AGENT_API_TOKEN` – bearer token for authorization

When deploying to Cloudflare Workers, use `wrangler` with the Python worker runtime and point it at this module. The MCP library will serve the endpoint using Streamable HTTP.

## Using the server in the agent

`src/agents/base/graph.py` looks for the environment variable `CF_MCP_SERVER_URL`. When set, it creates a `MultiServerMCPClient` connected to that URL and exposes the tools served by the Cloudflare worker. Those tools are added to the existing calendar agent tool set.

```bash
export CF_MCP_SERVER_URL="https://your-worker.workers.dev/mcp"
```

Run the application normally and it will access the additional tools via MCP.
