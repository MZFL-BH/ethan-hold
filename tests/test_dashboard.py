#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_dashboard.py — Unit Tests for Standalone Zero-CDN HTML Dashboard Generator

Verifies:
1. Standalone single-file HTML generation.
2. 100% Zero-CDN compliance (zero external script/link/image/import URLs).
3. Correct injection and rendering of key portfolio metrics, holdings, and circuit breaker badges.
4. Robustness against script injection attacks and varied input data formats.
"""

import json
import os
import re
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

# Add project root to sys.path so modules can be imported directly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_dashboard import (
    generate_dashboard_html,
    render_dashboard_html,
    validate_zero_cdn_compliance,
    sanitize_json_for_script,
    normalize_analysis_data,
)


class TestDashboardGenerator(unittest.TestCase):
    """Test suite for ethan-hold HTML dashboard generation and zero-CDN integrity."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_html_path = Path(self.temp_dir.name) / "test_dashboard.html"

        # Mock standard analysis data conforming to 25-fund benchmark
        self.mock_analysis_data = {
            "portfolio_name": "Ethan-Hold 25只基金基准测试组合",
            "generated_at": "2026-11-08T03:00:00Z",
            "portfolio_summary": {
                "total_cost": 100000.0,
                "total_market_value": 87000.0,
                "total_pnl": -13000.0,
                "total_pnl_rate": -0.13,
                "floating_pnl": -13000.0,
                "floating_pnl_rate": -0.13,
                "sector_exposures": {
                    "泛科技大类": 65.56,
                    "海外美股科技": 36.09,
                    "A股半导体与制造": 29.47,
                    "医药生物与大健康": 6.17,
                    "固定收益与纯债": 1.17,
                },
            },
            "penetrated_holdings": [
                {
                    "rank": 1,
                    "stock_code": "NVDA",
                    "stock_name": "NVDA (英伟达)",
                    "market": "美股",
                    "sector": "AI算力芯片与GPU",
                    "effective_weight": 3.18,
                    "effective_value": 2763.20,
                    "source_funds_count": 8,
                    "core_fund_desc": "8只并联纳指100共同重仓持有",
                },
                {
                    "rank": 4,
                    "stock_code": "002371",
                    "stock_name": "北方华创",
                    "market": "A股",
                    "sector": "半导体前道核心设备",
                    "effective_weight": 2.17,
                    "effective_value": 1884.10,
                    "source_funds_count": 4,
                    "core_fund_desc": "4只半导体芯片基金共同重仓",
                },
            ],
            "sector_distribution": [
                {"sector": "海外美股科技", "value": 31400.0, "weight": 36.09, "macro_group": "泛科技大类", "color": "#58a6ff"},
                {"sector": "A股半导体与制造", "value": 25640.0, "weight": 29.47, "macro_group": "泛科技大类", "color": "#f85149"},
                {"sector": "固定收益与纯债", "value": 1020.0, "weight": 1.17, "macro_group": "固定收益", "color": "#238636"},
            ],
            "fund_list": [
                {
                    "code": "000055",
                    "name": "广发纳斯达克100ETF联接A",
                    "category": "QDII并联纳指",
                    "sector": "海外美股科技",
                    "cost": 6000.0,
                    "market_value": 5400.0,
                    "pnl": -600.0,
                    "pnl_rate": -0.10,
                    "weight": 6.21,
                    "clone_group_id": "CLONE_QDII_NDX100",
                    "is_redundant": True,
                },
                {
                    "code": "320007",
                    "name": "诺安成长混合",
                    "category": "A股半导体",
                    "sector": "A股半导体与制造",
                    "cost": 8000.0,
                    "market_value": 6160.0,
                    "pnl": -1840.0,
                    "pnl_rate": -0.23,
                    "weight": 7.08,
                    "is_loss_heavy": True,
                },
            ],
            "breaker_status": {
                "is_tripped": True,
                "max_severity": "P0_CRITICAL",
                "intercept_messages": [
                    {
                        "code": "P0_MACRO_TECH_OVERWEIGHT",
                        "severity": "P0",
                        "title": "泛科技宏观大类敞口击穿硬顶 (65.56% >= 50.00%)",
                        "detail": "组合泛科技真实穿透敞口已达 65.56%，超出 50.00% 极限制约线 +15.56%",
                        "action": "系统已强制冻结泛科技及半导体增量资金申购，开启 48 小时强制冷静期。",
                    }
                ],
                "cooling_off_hours": 48,
                "rebalance_recommendations": [
                    "建议关闭交易软件进入 48 小时冷静期",
                    "分流资金至固定收益纯债",
                ],
            },
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_dashboard_html_creates_valid_file(self):
        """Verify dashboard HTML is generated, exists, and has substantial file size."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        self.assertTrue(os.path.exists(output_path))
        self.assertEqual(output_path, str(self.output_html_path.resolve()))
        file_size = os.path.getsize(output_path)
        self.assertGreater(file_size, 5000, f"Dashboard file size too small: {file_size} bytes")

    def test_zero_cdn_offline_guarantee(self):
        """Strict verification: zero external network resources (no remote script, link, img, or import)."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Assert no remote script src
        self.assertIsNone(
            re.search(r'<script[^>]+src\s*=\s*[\'"]https?://', content, re.IGNORECASE),
            "Found external script tag with http/https src!"
        )
        # Assert no remote link href
        self.assertIsNone(
            re.search(r'<link[^>]+href\s*=\s*[\'"]https?://', content, re.IGNORECASE),
            "Found external link tag with http/https href!"
        )
        # Assert no remote img src
        self.assertIsNone(
            re.search(r'<img[^>]+src\s*=\s*[\'"]https?://', content, re.IGNORECASE),
            "Found external img tag with http/https src!"
        )
        # Assert no CSS @import http
        self.assertIsNone(
            re.search(r'@import\s+url\s*\([\'"]?https?://', content, re.IGNORECASE),
            "Found external CSS @import with http/https URL!"
        )
        # Assert no protocol-relative CDN URLs
        self.assertNotIn("//cdn.", content)
        self.assertNotIn("//cdnjs.", content)
        self.assertNotIn("//unpkg.com", content)

    def test_render_key_metrics_and_figures(self):
        """Verify key portfolio figures (total cost, total value, PnL, tech exposure) are rendered."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check key numeric figures
        self.assertIn("100,000", content, "Total cost ¥100,000 not found in rendered dashboard")
        self.assertIn("87,000", content, "Total market value ¥87,000 not found in rendered dashboard")
        self.assertIn("-13.00%", content, "Floating PnL rate -13.00% not found in rendered dashboard")
        self.assertIn("65.56%", content, "Tech exposure 65.56% not found in rendered dashboard")

        # Check circuit breaker and risk badges
        self.assertIn("一级硬顶熔断", content)
        self.assertIn("48 小时", content)
        self.assertIn("冷静期", content)

    def test_penetrated_holdings_and_simulator_elements(self):
        """Verify presence of penetrated holdings data and interactive simulator widgets."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check Top Penetrated Holdings
        self.assertIn("NVDA", content)
        self.assertIn("北方华创", content)

        # Check Tab navigation elements
        self.assertIn("tab-overview", content)
        self.assertIn("tab-holdings", content)
        self.assertIn("tab-sectors", content)
        self.assertIn("tab-circuit", content)
        self.assertIn("tab-funds", content)

        # Check Pre-Trade Simulator Widget
        self.assertIn("sim-fund-select", content)
        self.assertIn("sim-amount-input", content)
        self.assertIn("runSimulation", content)

    def test_render_dashboard_html_contract_compatibility(self):
        """Verify render_dashboard_html interface contract as defined in PROJECT.md."""
        target_file = str((Path(self.temp_dir.name) / "contract_dashboard.html").resolve())
        returned_path = render_dashboard_html(self.mock_analysis_data, target_file)
        self.assertEqual(returned_path, target_file)
        self.assertTrue(os.path.exists(returned_path))
        self.assertGreater(os.path.getsize(returned_path), 5000)

    def test_zero_cdn_validator_rejects_external_urls(self):
        """Verify that validate_zero_cdn_compliance raises ValueError on violation."""
        violating_html_script = '<html><head><script src="https://cdn.jsdelivr.net/npm/vue"></script></head><body></body></html>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(violating_html_script)

        violating_html_link = '<html><head><link href="https://fonts.googleapis.com/css" rel="stylesheet"></head><body></body></html>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(violating_html_link)

        violating_html_import = '<html><style>@import url("https://cdn.example.com/style.css");</style><body></body></html>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(violating_html_import)

    def test_sanitize_json_prevents_script_hijacking(self):
        """Verify that script closing tags within data are properly escaped."""
        dangerous_data = {
            "comment": "</script><script>alert('xss')</script>"
        }
        sanitized = sanitize_json_for_script(dangerous_data)
        self.assertNotIn("</script", sanitized.lower())
        self.assertIn(r"<\/script", sanitized)

    def test_custom_portfolio_data_rendering(self):
        """Verify that custom portfolio metrics are properly calculated and injected."""
        custom_data = {
            "portfolio_summary": {
                "total_cost": 200000.0,
                "total_market_value": 180000.0,
                "total_pnl": -20000.0,
                "total_pnl_rate": -0.10,
                "sector_exposures": {
                    "泛科技大类": 72.50,
                },
            }
        }
        custom_output = Path(self.temp_dir.name) / "custom_dashboard.html"
        generate_dashboard_html(custom_data, str(custom_output))
        with open(custom_output, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("200,000", content)
        self.assertIn("180,000", content)
        self.assertIn("72.50%", content)

    def test_missing_template_raises_filenotfound(self):
        """Verify that an invalid template path raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            generate_dashboard_html({}, str(self.output_html_path), template_path="/non/existent/path.html")

    def test_svg_vector_charts_and_theme_elements(self):
        """Verify native SVG elements and executive dark-mode styling exist in template."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Native SVG elements
        self.assertIn("<svg", content)
        self.assertIn('id="donut-svg"', content)
        self.assertIn('id="donut-slices-group"', content)
        self.assertIn("donut-slice", content)
        self.assertIn("bar-track", content)
        self.assertIn("bar-fill", content)

        # Executive light mode CSS tokens
        self.assertIn("--bg-canvas: #f6f8fa;", content)
        self.assertIn("--bg-card: #ffffff;", content)
        self.assertIn("--border-default: #d0d7de;", content)
        self.assertIn("--color-primary: #0969da;", content)
        self.assertIn("--color-danger: #cf222e;", content)

    def test_redundancy_clones_and_cooling_off_elements(self):
        """Verify parallel fund redundancy indicators and 48-hour cooling-off countdown timer."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parallel redundancy elements
        self.assertIn("并联同质化", content)
        self.assertIn("冗余度", content)
        self.assertIn("0.88", content)
        self.assertIn("countdown-clock", content)

    def test_normalize_analysis_data_robustness(self):
        """Verify normalize_analysis_data gracefully handles diverse key namings and values."""
        raw_input = {
            "total_cost": 50000.0,
            "total_value": 45000.0,
            "total_pnl": -5000.0,
            "total_pnl_rate": -0.10,
            "sector_exposures": {
                "泛科技大类": 60.0,
                "A股半导体与制造": 30.0,
                "海外美股科技": 30.0,
            },
            "circuit_breaker": {
                "is_tripped": True,
                "max_severity": "P0_CRITICAL",
                "cooling_off_hours": 48,
            },
            "funds": [
                {"code": "123456", "name": "测试基金", "cost": 50000.0, "market_value": 45000.0}
            ]
        }
        normalized = normalize_analysis_data(raw_input)
        self.assertEqual(normalized["portfolio_summary"]["total_cost"], 50000.0)
        self.assertEqual(normalized["portfolio_summary"]["total_market_value"], 45000.0)
        self.assertEqual(normalized["breaker_status"]["max_severity"], "P0_CRITICAL")
        self.assertIn("fund_list", normalized)
        self.assertEqual(len(normalized["sector_distribution"]), 2)

    def test_javascript_syntax_and_execution_validity(self):
        """
        Verify that the generated dashboard's inlined JavaScript has zero syntax errors
        and parses cleanly via a real JS engine (Node.js).
        """
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Extract main <script> tag
        js_matches = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
        self.assertTrue(len(js_matches) > 0, "No <script> block found in generated dashboard")
        main_js = js_matches[0]

        # 1. Syntax check via node -c
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
            tf.write(main_js)
            js_temp_path = tf.name

        try:
            res = subprocess.run(["node", "-c", js_temp_path], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Node.js syntax validation failed: {res.stderr}")
        finally:
            if os.path.exists(js_temp_path):
                os.remove(js_temp_path)

    def test_zero_cdn_enhanced_validator_blocks_all_covert_leaks(self):
        """Verify enhanced validate_zero_cdn_compliance blocks SVG images, fonts, protocol-relative, and CSS url."""
        # SVG Image href
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance('<svg><image href="https://leak.com/img.png"/></svg>')
        # SVG Use href
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance('<svg><use xlink:href="//evil.com/icon.svg#test"/></svg>')
        # Protocol-relative
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance('<script src="//cdn.jsdelivr.net/npm/vue"></script>')
        # CSS font-face
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance('<style>@font-face { src: url("https://fonts.evil.com/font.woff2"); }</style>')
        # Inline CSS background
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance('<div style="background-image: url(\'https://tracker.com/pixel.gif\');"></div>')

    def test_core_holdings_macro_insight_rendered(self):
        """Verify Four Core Holdings Macro & Social Insight & Forecast are rendered in dashboard."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check section title
        self.assertIn("高占比核心重仓深度透视", content)
        self.assertIn("四大核心持仓", content)

        # Check four holdings
        self.assertIn("建信上海金 ETF 联接 C", content)
        self.assertIn("纳指 100 并联集群", content)
        self.assertIn("华泰柏瑞中证红利低波动", content)
        self.assertIn("融通稳信增益 6 个月持有", content)

        # Check macro and forecast subtitles
        self.assertIn("宏观与社会知识背景透视", content)
        self.assertIn("未来 1~3 个月潜在波动与风险预测", content)
        self.assertIn("投资实操应对建议", content)

        # Check Light Mode tokens
        self.assertIn("--bg-canvas: #f6f8fa;", content)
        self.assertIn("--bg-card: #ffffff;", content)

    def test_sheet_macro_declaration_and_toggle_rows_rendered(self):
        """Verify Tab 5 Sheet includes core holdings declaration, toggle functions, and badges."""
        output_path = generate_dashboard_html(self.mock_analysis_data, str(self.output_html_path))
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check Sheet Declaration banner
        self.assertIn("Sheet 声明指示：核心高占比重仓宏观背景透视与 1~3 个月波动前瞻", content)
        self.assertIn("四大主力 (合占 66.9%)", content)

        # Check JS function and styling
        self.assertIn("function toggleMacroInsight(code)", content)
        self.assertIn("MACRO_INSIGHTS", content)
        self.assertIn(".btn-micro", content)
        self.assertIn("isLossChasing = (pnlRate <= LOSS_CHASING_THRESHOLD)", content)


if __name__ == "__main__":
    unittest.main()
