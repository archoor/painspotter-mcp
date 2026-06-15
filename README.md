# PainSpotter MCP Server

Query [PainSpotter](https://painspotter.ai) business opportunities and weekly blog analyses directly from Claude, Cursor, or any MCP client.

PainSpotter mines Reddit, Hacker News and Product Hunt discussions and uses LLMs to surface validated business opportunities, organized in three layers: **Category** (domain) → **Theme** (a clustered pain point with trend signal) → **Opportunity** (a concrete product idea with commercial scores). The **Blog** publishes weekly long-form analyses of selected opportunities (free to read, built for AI citation).

## Two ways to connect

### Remote (recommended — zero install)

Point your client at the hosted endpoint and pass your API key as a header. Create a key at <https://painspotter.ai/account>.

Claude / Cursor (`~/.cursor/mcp.json` or Claude connectors):

```json
{
  "mcpServers": {
    "painspotter": {
      "url": "https://painspotter.ai/mcp/",
      "headers": { "X-API-Key": "psk_live_your_key" }
    }
  }
}
```

### Local (stdio fallback)

> The local stdio package talks to the public REST API. It exposes opportunity search plus **free blog tools** (no key needed for blog). For the full 7-tool hosted set (overview, trending themes, theme detail), use the remote endpoint above.

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

### Hosted endpoint (`https://painspotter.ai/mcp/`) — 7 tools

| Tool | Tier | Quota cost | Description |
|---|---|---|---|
| `get_overview` | Free | 1 | Categories overview + trending snapshot |
| `get_opportunity` | Free | 1 | Full detail of one opportunity (+ related blog URL if any) |
| `list_blog_posts` | Free | **0** | Recent published weekly analyses |
| `get_blog_post` | Free | **0** | Full Markdown of one blog article |
| `query_opportunities` | Pro | 2 | Filter by keyword / score / platform / recommendation / category |
| `list_trending_themes` | Pro | 2 | Pain points trending up right now |
| `get_theme` | Pro | 4 | Theme-level market signal + underlying opportunities |

### Local stdio package — 4 tools

| Tool | Key required | Description |
|---|---|---|
| `query_opportunities` | Yes | Filter opportunities (Pro-equivalent search via v1 API) |
| `get_opportunity` | Yes | Full opportunity detail |
| `list_blog_posts` | **No** | Recent published blog posts |
| `get_blog_post` | **No** | Full Markdown of one article |

Free keys can call the free hosted tools; Pro and Business keys unlock everything. Blog tools (`list_blog_posts`, `get_blog_post`) never consume quota on the hosted endpoint. Other calls deduct from the key's monthly allowance (Free 20 / Pro 1000 / Business 5000 units). Upgrade at <https://painspotter.ai/pricing>.

## License

MIT — see [LICENSE](./LICENSE).
