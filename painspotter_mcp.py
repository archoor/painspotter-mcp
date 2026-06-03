"""
PainSpotter MCP Server

让 Claude / Cursor 用户直接在 IDE 里查询 PainSpotter 商机数据。

环境变量（必填）：
  PAINSPOTTER_API_KEY   — 在 painspotter.ai → Account → API Key 获取
  PAINSPOTTER_API_BASE  — 默认 https://painspotter.ai（自部署时改此值）

工具列表（4 个）：
  list_opportunities    — 按评分/平台/推荐等级列出商机
  search_opportunities  — 关键词全文搜索商机
  get_opportunity       — 获取单个商机完整详情
  get_top_opportunities — 快速获取 Top N 商机

快速配置（Claude Desktop ~/.cursor/mcp.json）：
  {
    "mcpServers": {
      "painspotter": {
        "command": "python",
        "args": ["/path/to/painspotter_mcp.py"],
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
        "You have access to PainSpotter's business opportunity database. "
        "These are AI-analyzed opportunities discovered from Reddit, HackerNews, and ProductHunt discussions. "
        "Each opportunity includes a pain point, target audience, monetization model, and commercial scores. "
        "Use these tools to help users discover, evaluate, and compare business ideas."
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

@mcp.tool()
def list_opportunities(
    min_score: int = 0,
    platform: Optional[str] = None,
    recommendation: Optional[str] = None,
    page_size: int = 10,
) -> str:
    """
    列出 PainSpotter 商机，按综合评分从高到低排序。

    Args:
        min_score: 最低综合评分（0-100，默认 0）
        platform: 平台筛选，可选 reddit / producthunt（留空=全部）
        recommendation: 推荐等级筛选，可选 Build / Validate / Skip（留空=全部）
        page_size: 返回条数（1-50，默认 10）
    """
    params: dict = {
        "min_score": min_score,
        "page_size": min(max(page_size, 1), 50),
        "online_only": True,
    }
    if platform:
        params["platform"] = platform
    if recommendation and recommendation in ("Build", "Validate", "Skip"):
        params["recommendation"] = recommendation

    data = _get("/opportunities", params)
    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        return "没有找到符合条件的商机。尝试降低 min_score 或去掉筛选条件。"

    header = f"共 {total} 个商机，显示前 {len(items)} 条（按评分排序）：\n"
    rows = "\n\n".join(_fmt_item(o) for o in items)
    return header + rows


@mcp.tool()
def search_opportunities(
    query: str,
    min_score: int = 0,
    page_size: int = 10,
) -> str:
    """
    按关键词搜索商机（匹配标题和描述）。

    Args:
        query: 搜索关键词，如 "sleep tracker" "AI writing" "freelancer"
        min_score: 最低综合评分（0-100，默认 0）
        page_size: 返回条数（1-30，默认 10）
    """
    params = {
        "q": query.strip(),
        "min_score": min_score,
        "page_size": min(max(page_size, 1), 30),
        "online_only": True,
    }
    data = _get("/opportunities", params)
    items = data.get("items", [])
    total = data.get("total", 0)

    if not items:
        return f'关键词 "{query}" 没有匹配结果。建议换用更通用的词，或拆分为单词搜索。'

    header = f'关键词 "{query}" 命中 {total} 条，显示前 {len(items)} 条：\n'
    rows = "\n\n".join(_fmt_item(o) for o in items)
    return header + rows


@mcp.tool()
def get_opportunity(opportunity_id: int) -> str:
    """
    获取指定商机的完整详情，包含描述、MVP 功能、竞争对手、风险点和社区证据数。

    Args:
        opportunity_id: 商机 ID（从 list_opportunities 或 search_opportunities 的结果中获取）
    """
    data = _get(f"/opportunities/{opportunity_id}")
    return _fmt_detail(data)


@mcp.tool()
def get_top_opportunities(
    limit: int = 5,
    platform: Optional[str] = None,
    recommendation: Optional[str] = None,
) -> str:
    """
    快速获取评分最高的商机（适合"给我看看最好的机会"类问题）。

    Args:
        limit: 返回条数（1-20，默认 5）
        platform: 平台筛选，可选 reddit / producthunt（留空=全部）
        recommendation: 推荐等级，可选 Build / Validate / Skip（只看 Build 推荐则填 Build）
    """
    params: dict = {
        "min_score": 60,
        "page_size": min(max(limit, 1), 20),
        "online_only": True,
    }
    if platform:
        params["platform"] = platform
    if recommendation and recommendation in ("Build", "Validate", "Skip"):
        params["recommendation"] = recommendation

    data = _get("/opportunities", params)
    items = data.get("items", [])

    if not items:
        return "暂时没有符合条件的高评分商机（评分≥60）。"

    header = f"Top {len(items)} 商机（评分≥60，按评分排序）：\n"
    rows = "\n\n".join(_fmt_item(o) for o in items)
    footer = "\n\n使用 get_opportunity(id) 获取任意商机的完整详情。"
    return header + rows + footer


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
