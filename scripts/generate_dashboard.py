#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_dashboard.py — Standalone Zero-CDN Offline HTML Dashboard Generator

Part of Ethan-Hold (仓位罗盘).
Strictly adheres to Zero-CDN / Offline-First principles:
- 100% standalone single-file HTML output.
- ZERO external network requests (no remote scripts, fonts, CSS, or images).
- Native SVG charts and client-side reactive pre-trade circuit breaker simulator.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve default template path
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "dashboard_template.html"


def sanitize_json_for_script(data: Any) -> str:
    """
    Safely serialize a dictionary to a JSON string that can be embedded
    inside an HTML <script> block without allowing tag injection or breaking script boundaries.
    """
    serialized = json.dumps(data, ensure_ascii=False, indent=2)
    # Prevent closing script tag injection and HTML comment breakout
    sanitized = re.sub(r'</script', r'<\\/script', serialized, flags=re.IGNORECASE)
    sanitized = re.sub(r'<!--', r'<\\!--', sanitized)
    return sanitized


def validate_zero_cdn_compliance(html_content: str) -> None:
    """
    Validate that the HTML contains ZERO external HTTP/HTTPS resource dependencies.
    Raises ValueError if any remote script, stylesheet, font, image, SVG resource, or media is found.
    Strictly covers:
    - http:// and https:// URLs
    - Protocol-relative // URLs
    - HTML resource tags (<script>, <link>, <img>, <iframe>, <audio>, <video>, <source>, <track>, <embed>, <object>)
    - SVG resource tags (<image>, <use>) with href or xlink:href
    - CSS @import, @font-face, and all url(...) expressions
    """
    forbidden_patterns = [
        # 1. HTML tags with remote or protocol-relative src attribute
        (r'<(?:script|img|iframe|audio|video|source|track|embed|input)\b[^>]*?\bsrc\s*=\s*[\'"]?(?:https?:)?//', "External media/script src URL"),
        # 2. Link tags with remote or protocol-relative href attribute
        (r'<link\b[^>]*?\bhref\s*=\s*[\'"]?(?:https?:)?//', "External stylesheet/font/resource in <link href=...>"),
        # 3. SVG image or use tags with href or xlink:href
        (r'<(?:image|use)\b[^>]*?\b(?:xlink:)?href\s*=\s*[\'"]?(?:https?:)?//', "External SVG image/use href URL"),
        # 4. Object tags with data attribute
        (r'<object\b[^>]*?\bdata\s*=\s*[\'"]?(?:https?:)?//', "External object data URL"),
        # 5. CSS @import statements
        (r'@import\s+(?:url\s*\(\s*[\'"]?|[\'"])(?:https?:)?//', "External CSS @import URL"),
        # 6. CSS url(...) declarations (covers @font-face, background, background-image, cursor, content, etc.)
        (r'url\s*\(\s*[\'"]?(?:https?:)?//', "External resource in CSS url(...)"),
    ]

    for pattern, desc in forbidden_patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            raise ValueError(f"Zero-CDN violation detected: {desc} -> {match.group(0)}")


def normalize_analysis_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize various input formats (from penetration engine, circuit breaker engine,
    or raw benchmarks) into the canonical dashboard data structure.
    """
    normalized = dict(data)

    # 1. Normalize portfolio_summary without artificial hardcoded fallbacks
    summary = normalized.get("portfolio_summary") or {}
    total_cost = (
        summary.get("total_cost")
        if summary.get("total_cost") is not None
        else (normalized.get("total_cost") if normalized.get("total_cost") is not None else 0.0)
    )
    total_value = (
        summary.get("total_market_value")
        if summary.get("total_market_value") is not None
        else (
            summary.get("total_value")
            if summary.get("total_value") is not None
            else (
                normalized.get("total_market_value")
                if normalized.get("total_market_value") is not None
                else (normalized.get("total_value") if normalized.get("total_value") is not None else 0.0)
            )
        )
    )
    pnl = (
        summary.get("floating_pnl")
        if summary.get("floating_pnl") is not None
        else (
            summary.get("total_pnl")
            if summary.get("total_pnl") is not None
            else (
                normalized.get("floating_pnl")
                if normalized.get("floating_pnl") is not None
                else (normalized.get("total_pnl") if normalized.get("total_pnl") is not None else (total_value - total_cost))
            )
        )
    )
    pnl_rate = (
        summary.get("floating_pnl_rate")
        if summary.get("floating_pnl_rate") is not None
        else (
            summary.get("total_pnl_rate")
            if summary.get("total_pnl_rate") is not None
            else (
                normalized.get("floating_pnl_rate")
                if normalized.get("floating_pnl_rate") is not None
                else (normalized.get("total_pnl_rate") if normalized.get("total_pnl_rate") is not None else (pnl / total_cost if total_cost else 0.0))
            )
        )
    )

    # Ensure rate format
    if abs(pnl_rate) > 1.0:
        pnl_rate = pnl_rate / 100.0

    sector_exposures = summary.get("sector_exposures") or normalized.get("sector_exposures") or {}

    normalized["portfolio_summary"] = {
        "total_cost": float(total_cost),
        "total_market_value": float(total_value),
        "total_pnl": float(pnl),
        "total_pnl_rate": float(pnl_rate),
        "floating_pnl": float(pnl),
        "floating_pnl_rate": float(pnl_rate),
        "sector_exposures": sector_exposures,
    }

    # 2. Normalize breaker_status / circuit_breaker
    breaker = normalized.get("breaker_status") or normalized.get("circuit_breaker") or {}
    if breaker:
        # Guarantee standard keys
        normalized["breaker_status"] = {
            "is_tripped": breaker.get("is_tripped", True),
            "max_severity": breaker.get("max_severity", "P0_CRITICAL"),
            "intercept_messages": breaker.get("intercept_messages", []),
            "cooling_off_hours": breaker.get("cooling_off_hours", 48),
            "rebalance_recommendations": breaker.get("rebalance_recommendations", []),
        }

    # 3. Normalize fund_list
    funds = normalized.get("fund_list") or normalized.get("funds") or []
    if funds:
        normalized["fund_list"] = funds

    # 4. Normalize penetrated_holdings
    holdings = normalized.get("penetrated_holdings") or []
    if holdings:
        normalized["penetrated_holdings"] = holdings

    # 5. Normalize sector_distribution
    sectors = normalized.get("sector_distribution") or []
    if not sectors and sector_exposures:
        # Build sector_distribution from sector_exposures dict
        palette = [
            "#58a6ff", "#f85149", "#bc8cff", "#79c0ff", "#d29922",
            "#ff7b72", "#56d364", "#e3b341", "#39d353", "#8b949e",
            "#f0883e", "#238636"
        ]
        built_sectors = []
        for i, (sec_name, pct) in enumerate(sector_exposures.items()):
            if sec_name == "泛科技大类":
                continue
            built_sectors.append({
                "sector": sec_name,
                "weight": float(pct),
                "value": round(float(pct) / 100.0 * float(total_value), 2),
                "macro_group": "泛科技大类" if "科技" in sec_name or "半导体" in sec_name else "其他板块",
                "color": palette[i % len(palette)],
            })
        normalized["sector_distribution"] = built_sectors

    return normalized


def generate_dashboard_html(
    analysis_data: Dict[str, Any],
    output_file: str,
    template_path: Optional[str] = None
) -> str:
    """
    Generates a standalone, zero-CDN, offline-ready HTML dashboard from analysis data.

    Parameters:
    -----------
    analysis_data: Dict[str, Any]
        Portfolio analysis results containing portfolio_summary, penetrated_holdings,
        sector_distribution, fund_list, and breaker_status.
    output_file: str
        Target filepath for the generated HTML file.
    template_path: Optional[str]
        Optional custom path to the HTML dashboard template.

    Returns:
    --------
    str:
        Absolute filepath of the generated HTML dashboard.
    """
    tmpl_path = Path(template_path) if template_path else DEFAULT_TEMPLATE_PATH
    if not tmpl_path.exists():
        raise FileNotFoundError(f"Dashboard template not found at {tmpl_path}")

    with open(tmpl_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    normalized_data = normalize_analysis_data(analysis_data)
    sanitized_json = sanitize_json_for_script(normalized_data)

    # 1. Inject JSON data into script container (Target exact script tag to avoid JS code collisions)
    script_tag_pattern = r'(<script\s+id=["\']portfolio-data-script["\'][^>]*>)(.*?)(</script>)'
    placeholder = "/*__PORTFOLIO_DATA_PLACEHOLDER__*/"
    if re.search(script_tag_pattern, template_content, re.DOTALL):
        rendered_html = re.sub(
            script_tag_pattern,
            lambda m: f"{m.group(1)}\n{sanitized_json}\n  {m.group(3)}",
            template_content,
            count=1,
            flags=re.DOTALL
        )
    elif placeholder in template_content:
        # Fallback: strictly replace ONLY the first occurrence (count=1)
        rendered_html = template_content.replace(placeholder, sanitized_json, 1)
    else:
        # Fallback injection before closing </head>
        rendered_html = template_content.replace(
            "</head>",
            f'<script id="portfolio-data-script" type="application/json">\n{sanitized_json}\n</script>\n</head>',
            1
        )

    # 2. Pre-fill / update static metrics in HTML for static searchability and offline viewing
    summary = normalized_data["portfolio_summary"]
    total_cost_str = f"¥{summary['total_cost']:,.2f}"
    total_value_str = f"¥{summary['total_market_value']:,.2f}"
    pnl_rate = summary["total_pnl_rate"]
    pnl_rate_pct = pnl_rate * 100.0 if abs(pnl_rate) <= 1.0 else pnl_rate
    pnl_str = f"{'-' if summary['total_pnl'] < 0 else ''}¥{abs(summary['total_pnl']):,.2f} ({pnl_rate_pct:+.2f}%)"

    tech_exp = summary.get("sector_exposures", {}).get("泛科技大类", 0.0)
    tech_str = f"{tech_exp:.2f}%"

    rendered_html = rendered_html.replace("¥100,000.00", total_cost_str)
    rendered_html = rendered_html.replace("¥87,000.00", total_value_str)
    rendered_html = rendered_html.replace("-¥13,000.00 (-13.00%)", pnl_str)
    rendered_html = rendered_html.replace("65.56%", tech_str)

    # 3. Strictly validate Zero-CDN compliance
    validate_zero_cdn_compliance(rendered_html)

    # 4. Write to destination file
    out_path = Path(output_file).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    # 5. Validate file creation and non-zero size
    if not out_path.exists():
        raise RuntimeError(f"Failed to generate dashboard: output file does not exist at {out_path}")
    if out_path.stat().st_size == 0:
        raise RuntimeError(f"Generated dashboard file is empty (0 bytes) at {out_path}")

    return str(out_path)


# Alias for interface contract compatibility with PROJECT.md
def render_dashboard_html(analysis_result: Dict[str, Any], output_filepath: str) -> str:
    """
    Interface Contract function conforming to PROJECT.md § Interface Contracts.
    """
    return generate_dashboard_html(analysis_result, output_filepath)


if __name__ == "__main__":
    import sys

    # Quick CLI invocation
    if len(sys.argv) > 2:
        input_json_path = sys.argv[1]
        out_file_path = sys.argv[2]
        with open(input_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        generated_path = generate_dashboard_html(data, out_file_path)
        print(f"✅ Dashboard generated successfully: {generated_path}")
    else:
        # Default run with benchmark data
        default_output = Path(__file__).resolve().parent.parent / "dashboard.html"
        generated_path = generate_dashboard_html({}, str(default_output))
        print(f"✅ Default benchmark dashboard generated: {generated_path}")
