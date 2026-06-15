"""
PainSpotter MCP Server (local stdio)

Lets Claude / Cursor users query PainSpotter business opportunities from their IDE.

This local stdio package talks to the public PainSpotter v1 REST API and exposes
the opportunity-level tools plus free blog tools. It is a subset of the hosted endpoint at
https://painspotter.ai/mcp — the hosted server has 7 tools (adds get_overview,
list_trending_themes, get_theme). See README.md.

Environment variables:
  PAINSPOTTER_API_KEY   — create one at https://painspotter.ai/account (required)
  PAINSPOTTER_API_BASE  — defaults to https://painspotter.ai (override for self-host)

Tools (4):
  query_opportunities — filter opportunities by keyword, score, platform, recommendation
  get_opportunity     — full detail of one opportunity
  list_blog_posts     — recent published blog analyses (free, no API key needed)
  get_blog_post       — full Markdown of one blog article (free, no API key needed)

Quick config (~/.cursor/mcp.json or Claude Desktop):
  {
    "mcpServers": {
      "painspotter": {
        "command": "uvx",
        "args": ["painspotter-mcp"],
        "env": {
          "PAINSPOTTER_API_KEY": "psk_live_...",
          "PAINSPOTTER_API_BASE": "https://painspotter.ai"
        }
      }
    }
  }
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import httpx
from fastmcp import FastMCP

# ── 配置 ──────────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("PAINSPOTTER_API_BASE", "https://painspotter.ai").rstrip("/")
API_KEY = os.environ.get("PAINSPOTTER_API_KEY", "")

mcp = FastMCP(
    "PainSpotter",
    instructions=(
        "PainSpotter is a database of AI-analyzed business opportunities mined from "
        "Reddit, Hacker News and Product Hunt discussions. Each opportunity is a concrete "
        "product idea carrying a pain point, target audience, monetization model and commercial scores.\n\n"
        "This local server exposes the opportunity-level tools: use query_opportunities to "
        "search and filter, then get_opportunity for the full detail of a specific result. "
        "It also exposes the free blog: list_blog_posts / get_blog_post return weekly "
        "long-form opportunity analyses (no API key needed). "
        "For category overviews and trending themes, use the hosted endpoint at "
        "https://painspotter.ai/mcp."
    ),
)


# ── HTTP 工具函数 ───────────────────────────────────────────────────────────────

def _get(path: str, params: Optional[dict] = None) -> dict:
    """向 PainSpotter API 发 GET 请求。"""
    if not API_KEY:
        raise ValueError(
            "PAINSPOTTER_API_KEY 未配置。"
            "请到 painspotter.ai → Account → API Key 创建后设置环境变量。"
        )
    url = f"{API_BASE}/api/v1{path}"
    resp = httpx.get(url, params=params, headers={"X-API-Key": API_KEY}, timeout=15)
    if resp.status_code == 401:
        raise PermissionError("API key 无效或已撤销，请检查 PAINSPOTTER_API_KEY。")
    if resp.status_code == 429:
        data = resp.json().get("detail", {})
        raise RuntimeError(
            f"API 配额已用完（{data.get('current', '?')}/{data.get('limit', '?')}次）。"
            f"下次重置：{data.get('reset_at', '—')}。"
        )
    resp.raise_for_status()
    return resp.json()


def _get_public(path: str, params: Optional[dict] = None) -> dict:
    """向 PainSpotter 公开 API 发 GET（无需 API key）。

    Blog 是免费、面向引用的内容表面，不计入配额、不需密钥。
    """
    url = f"{API_BASE}{path}"
    resp = httpx.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _fmt_item(o: dict) -> str:
    """将列表项格式化为 LLM 易读的简洁文本。"""
    rec_emoji = {"Build": "🟢", "Validate": "🟡", "Skip": "🔴"}.get(o.get("recommendation", ""), "⚪")
    return (
        f"#{o['id']} [{o['score']}分] {rec_emoji} {o['recommendation']} | "
        f"{o['title']}\n"
        f"   平台:{o['platform']} | 频道:{o['channel_name']} | "
        f"痛点:{o['pain_point_intensity']}/10 | 付费意愿:{o['willingness_to_pay_score']}/10 | "
        f"难度:{o['tech_difficulty']}/10\n"
        f"   受众:{o.get('target_audience', '—')} | 变现:{o.get('monetization_model', '—')}"
    )


def _fmt_detail(o: dict) -> str:
    """将详情格式化为 LLM 易读的结构化文本。"""
    lines = [
        f"## {o['title']}",
        f"ID: {o['id']} | 平台: {o['platform']} | 频道: {o['channel_name']}",
        f"综合评分: {o['score']}/100 | 推荐: {o['recommendation']}",
        "",
        "### 评分明细",
        f"- 痛点强度: {o['pain_point_intensity']}/10",
        f"- 付费意愿: {o['willingness_to_pay_score']}/10",
        f"- 技术难度: {o['tech_difficulty']}/10（越低越易）",
        f"- 可持续性: {o['sustainability_score']}/10",
        "",
        "### 机会描述",
        o.get("description", "—"),
        "",
        f"**目标受众**: {o.get('target_audience', '—')}",
        f"**变现模式**: {o.get('monetization_model', '—')}",
        f"**市场规模估计**: {o.get('market_size_estimate', '—')}",
    ]

    if o.get("key_features"):
        lines += ["", "### MVP 核心功能"] + [f"- {f}" for f in o["key_features"]]

    if o.get("competitors"):
        lines += ["", f"### 竞争对手: {', '.join(o['competitors'])}"]
        if o.get("differentiation"):
            lines.append(f"**差异化机会**: {o['differentiation']}")

    if o.get("risks"):
        lines += ["", "### 主要风险"] + [f"- {r}" for r in o["risks"]]

    if o.get("evidence_count"):
        lines.append(f"\n**支持证据数**: {o['evidence_count']} 条社区讨论")

    return "\n".join(lines)


# ── MCP 工具 ───────────────────────────────────────────────────────────────────

@mcp.tool(
    annotations={
        "title": "Query Opportunities",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def query_opportunities(
    query: Optional[str] = None,
    min_score: int = 0,
    platform: Optional[str] = None,
    recommendation: Optional[str] = None,
    page_size: int = 10,
) -> str:
    """Search PainSpotter opportunities: filter by keyword, minimum score, platform
    and recommendation tier. Results are sorted by overall score, highest first.

    Args:
        query: Keyword matched against title + description, e.g. "sleep tracker",
            "AI writing". Empty = no keyword filter.
        min_score: Minimum overall score, 0-100. Default 0.
        platform: Platform filter: reddit / hackernews / producthunt. Empty = all.
        recommendation: Recommendation tier: Build / Validate / Skip. Empty = all.
        page_size: Number of results to return, 1-30. Default 10.
    """
    params: dict = {
        "min_score": min_score,
        "page_size": min(max(page_size, 1), 30),
        "online_only": True,
    }
    if query and query.strip():
        params["q"] = query.strip()
    if platform:
        params["platform"] = platform
    if recommendation and recommendation in ("Build", "Validate", "Skip"):
        params["recommendation"] = recommendation

    data = _get("/opportunities", params)
    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        return "No opportunities matched. Try lowering min_score or removing filters."

    header = f"{total} matching opportunities, showing top {len(items)} (sorted by score):\n"
    rows = "\n\n".join(_fmt_item(o) for o in items)
    footer = "\n\nUse get_opportunity(opportunity_id) for the full detail of any result."
    return header + rows + footer


@mcp.tool(
    annotations={
        "title": "Get Opportunity Detail",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def get_opportunity(opportunity_id: int) -> str:
    """Get the full detail of a specific opportunity: description, score breakdown,
    MVP features, competitors, differentiation, risks and community evidence count.

    Args:
        opportunity_id: Opportunity ID, taken from query_opportunities results.
    """
    data = _get(f"/opportunities/{opportunity_id}")
    return _fmt_detail(data)


@mcp.tool(
    annotations={
        "title": "List Blog Posts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def list_blog_posts(limit: int = 10) -> str:
    """List recent published PainSpotter blog posts — weekly long-form analyses of
    validated business opportunities (who's hurting, why now, how to build it, plus an
    indie-hacker checklist). Free; no API key required.

    Args:
        limit: Number of posts to return, 1-30. Default 10.
    """
    data = _get_public(
        "/api/blog", {"page": 1, "page_size": min(max(limit, 1), 30)}
    )
    items = data.get("items", [])
    if not items:
        return "No blog posts published yet."
    lines = [f"{data.get('total', len(items))} published posts, showing {len(items)}:\n"]
    for p in items:
        pub = (p.get("published_at") or "")[:10]
        lines.append(f"- [{pub}] {p['title']}\n  slug: {p['slug']} | {p.get('excerpt', '')}")
    lines.append("\nUse get_blog_post(slug) for the full article.")
    return "\n".join(lines)


@mcp.tool(
    annotations={
        "title": "Get Blog Post",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
def get_blog_post(slug: str) -> str:
    """Get the full Markdown body of one published blog post by its slug. Free; no API
    key required. Content is an original AI synthesis with no verbatim community quotes.

    Args:
        slug: Article slug, taken from list_blog_posts results.
    """
    p = _get_public(f"/api/blog/by-slug/{slug}")
    header = [
        f"# {p['title']}",
        f"URL: {API_BASE}/blog/{p['slug']}",
    ]
    if p.get("published_at"):
        header.append(f"Published: {p['published_at'][:10]}")
    if p.get("tags"):
        header.append(f"Tags: {', '.join(p['tags'])}")
    body = p.get("body_md") or p.get("excerpt") or ""
    return "\n".join(header) + "\n\n" + body


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
