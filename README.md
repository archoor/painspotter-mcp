# PainSpotter MCP Server

Query [PainSpotter](https://painspotter.ai) business opportunities directly from Claude, Cursor, or any MCP client.

PainSpotter mines Reddit, Hacker News and Product Hunt discussions and uses LLMs to surface validated business opportunities, organized in three layers: **Category** (domain) → **Theme** (a clustered pain point with trend signal) → **Opportunity** (a concrete product idea with commercial scores).

## Two ways to connect

### Remote (recommended — zero install)

Point your client at the hosted endpoint and pass your API key as a header. Create a key at <https://painspotter.ai/account>.

Claude / Cursor (`~/.cursor/mcp.json` or Claude connectors):

```json
{
  "mcpServers": {
    "painspotter": {
      "url": "https://painspotter.ai/mcp",
      "headers": { "X-API-Key": "psk_live_your_key" }
    }
  }
}
```

### Local (stdio fallback)

> The local stdio package talks to the public v1 REST API and exposes the **opportunity tools** only. For the full 5-tool set (overview, trending themes, theme detail) use the remote endpoint above.

```bash
pip install painspotter-mcp   # or: uvx painspotter-mcp
```

```json
{
  "mcpServers": {
    "painspotter": {
      "command": "uvx",
      "args": ["painspotter-mcp"],
      "env": {
        "PAINSPOTTER_API_KEY": "psk_live_your_key",
        "PAINSPOTTER_API_BASE": "https://painspotter.ai"
      }
    }
  }
}
```

## Tools & tiering

| Tool | Tier | Quota cost | Description |
|---|---|---|---|
| `get_overview` | Free | 1 | Categories overview + trending snapshot |
| `get_opportunity` | Free | 1 | Full detail of one opportunity |
| `query_opportunities` | Pro | 2 | Filter by keyword / score / platform / recommendation / category |
| `list_trending_themes` | Pro | 2 | Pain points trending up right now |
| `get_theme` | Pro | 4 | Theme-level market signal + underlying opportunities |

Free keys can only call the two free tools; Pro keys unlock everything. Each call deducts its quota cost from the key's monthly allowance (Free 20 / Pro 1000 units). Exceeding the quota returns a friendly error; upgrade at <https://painspotter.ai/pricing>.

## License

MIT — see [LICENSE](./LICENSE).
