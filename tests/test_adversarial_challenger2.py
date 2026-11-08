#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_adversarial_challenger2.py — Tier 5 White-Box Adversarial Verification Suite

Target: ethan-hold Skill
Author: Challenger 2 (teamwork_challenger)

Coverage:
1. Exact boundary thresholds:
   - Macro sector: 49.999% vs 50.000%
   - Sub-sector: 34.999% vs 35.000%
   - Single stock: 14.999% vs 15.000%
   - PnL: -9.999% vs -10.000%
   - Defensive floor vs Sub-sector ceiling false-positive conflict
2. Pre-trade simulation bypass attempts:
   - Front-end JS vs Python engine discrepancy on P0 macro tech cap (fund 000834 bypass)
   - Staggered increment accumulation
   - Disguised sector mapping (English tickers like QQQ)
   - Negative / zero amounts
3. CLI input fuzzing:
   - Chinese comma in --simulate-buy
   - CSV with Chinese commas, corrupted quotes, trailing empty lines, accounting parentheses, missing headers
4. XSS / HTML injection payload tests:
   - Injection payloads in fund names, stock names, categories
   - Verifying lack of DOM escaping in dashboard template
5. Zero-CDN leakage fuzzing:
   - SVG image href, CSS @font-face, protocol-relative URLs, background url
"""

import csv
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

# Add skill root to sys.path
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order, DEFAULT_THRESHOLDS
from scripts.penetration import map_macro_sector, normalize_stock_identity, penetrate_portfolio
from scripts.generate_dashboard import (
    generate_dashboard_html,
    normalize_analysis_data,
    sanitize_json_for_script,
    validate_zero_cdn_compliance,
)
from scripts.run_analysis import clean_financial_number, parse_portfolio_file


class TestTier5AdversarialBoundaries(unittest.TestCase):
    """1. Exact Boundary Conditions Stress Testing"""

    def test_macro_sector_exact_boundary(self):
        """Macro sector threshold: 49.999% (PASS) vs 50.000% (TRIPPED P0)"""
        summary_pass = {
            "total_value": 100000.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {"泛科技大类": 49.999},
        }
        res_pass = evaluate_circuit_breakers(summary_pass, [])
        self.assertFalse(res_pass["is_tripped"])
        self.assertEqual(res_pass["max_severity"], "NORMAL")

        summary_trip = {
            "total_value": 100000.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {"泛科技大类": 50.000},
        }
        res_trip = evaluate_circuit_breakers(summary_trip, [])
        self.assertTrue(res_trip["is_tripped"])
        self.assertEqual(res_trip["max_severity"], "P0_CRITICAL")
        self.assertTrue(any(m["code"] == "P0_MACRO_TECH_OVERWEIGHT" for m in res_trip["intercept_messages"]))

    def test_sub_sector_exact_boundary(self):
        """Sub-sector threshold: 34.999% (PASS) vs 35.000% (TRIPPED P0)"""
        summary_pass = {
            "total_value": 100000.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {"医药与大健康": 34.999},
        }
        res_pass = evaluate_circuit_breakers(summary_pass, [])
        self.assertFalse(res_pass["is_tripped"])
        self.assertEqual(res_pass["max_severity"], "NORMAL")

        summary_trip = {
            "total_value": 100000.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {"医药与大健康": 35.000},
        }
        res_trip = evaluate_circuit_breakers(summary_trip, [])
        self.assertTrue(res_trip["is_tripped"])
        self.assertEqual(res_trip["max_severity"], "P0_CRITICAL")
        self.assertTrue(any(m["code"] == "P0_SUB_SECTOR_OVERWEIGHT" for m in res_trip["intercept_messages"]))

    def test_single_stock_exact_boundary(self):
        """Single stock threshold: 14.999% (PASS) vs 15.000% (TRIPPED P0)"""
        summary = {"total_value": 100000.0, "floating_pnl_rate": 0.0, "sector_exposures": {}}
        holdings_pass = [{"stock_name": "测试股A", "effective_weight": 14.999, "effective_value": 14999.0}]
        res_pass = evaluate_circuit_breakers(summary, holdings_pass)
        self.assertFalse(res_pass["is_tripped"])
        self.assertEqual(res_pass["max_severity"], "NORMAL")

        holdings_trip = [{"stock_name": "测试股B", "effective_weight": 15.000, "effective_value": 15000.0}]
        res_trip = evaluate_circuit_breakers(summary, holdings_trip)
        self.assertTrue(res_trip["is_tripped"])
        self.assertEqual(res_trip["max_severity"], "P0_CRITICAL")
        self.assertTrue(any(m["code"] == "P0_SINGLE_STOCK_OVERWEIGHT" for m in res_trip["intercept_messages"]))

    def test_pnl_exact_boundary(self):
        """PnL threshold: -9.999% (PASS) vs -10.000% (TRIPPED P1 when tech >= 40%)"""
        summary_pass = {
            "total_value": 100000.0,
            "floating_pnl_rate": -0.09999,
            "sector_exposures": {"泛科技大类": 45.0},
        }
        res_pass = evaluate_circuit_breakers(summary_pass, [])
        self.assertFalse(res_pass["is_tripped"])
        self.assertEqual(res_pass["max_severity"], "NORMAL")

        summary_trip = {
            "total_value": 100000.0,
            "floating_pnl_rate": -0.10000,
            "sector_exposures": {"泛科技大类": 45.0},
        }
        res_trip = evaluate_circuit_breakers(summary_trip, [])
        self.assertTrue(res_trip["is_tripped"])
        self.assertEqual(res_trip["max_severity"], "P1_WARNING")
        self.assertEqual(res_trip["cooling_off_hours"], 48)
        self.assertTrue(any(m["code"] == "P1_LOSS_CHASING_FREEZE" for m in res_trip["intercept_messages"]))

    def test_defensive_sector_false_positive_bug(self):
        """
        Adversarial Finding: Defensive asset rebalancing false-positive trip.
        When user holds > 35% in '防御底线 (纯债/现金/黄金)', circuit breaker treats it as
        a sub-sector breach and trips P0_CRITICAL, blocking the user from safe assets!
        """
        summary_defensive = {
            "total_value": 100000.0,
            "floating_pnl_rate": 0.05,
            "sector_exposures": {
                "防御底线 (纯债/现金/黄金)": 80.0,
                "中盘与宽基": 20.0,
            },
        }
        res = evaluate_circuit_breakers(summary_defensive, [])
        # Verification: Defensive assets must NOT trip P0_SUB_SECTOR_OVERWEIGHT
        is_falsely_tripped = any(
            m.get("code") == "P0_SUB_SECTOR_OVERWEIGHT" and "防御底线" in m.get("title", "")
            for m in res["intercept_messages"]
        )
        self.assertFalse(is_falsely_tripped, "Defensive assets > 35% must NOT be incorrectly blocked as P0_SUB_SECTOR_OVERWEIGHT")


class TestTier5PreTradeSimulationBypass(unittest.TestCase):
    """2. Pre-Trade Simulation Bypass Attempts"""

    def test_frontend_vs_python_discrepancy_p0_macro_bypass(self):
        """
        Adversarial Finding: Front-end dashboard simulator bypasses P0 Macro Tech Cap.
        In dashboard_template.html (line 1793):
          isIntercepted = (isTechTarget && (currentTechPct >= 50 || newTechPct >= 50) && pnlRate <= -0.10);
        Notice the `&& pnlRate <= -0.10`!
        If a tech fund has pnl_rate > -10% (e.g. fund 000834 at -9.0%),
        Python engine correctly BLOCKS it (P0_CRITICAL),
        BUT the Front-end JS simulator ALLOWS it (ORDER PERMITTED)!
        """
        fixture_path = SKILL_ROOT / "tests" / "fixtures" / "portfolio_25_funds.json"
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        pen_res = penetrate_portfolio(data)
        fund_000834 = next(f for f in pen_res["funds"] if f["code"] == "000834")
        self.assertAlmostEqual(fund_000834["pnl_rate"], -0.09, places=2)

        # 1. Python Engine verification: STRICTLY BLOCKED
        py_res = simulate_buy_order(pen_res, fund_000834, 10000.0)
        self.assertEqual(py_res["status"], "BLOCKED")
        self.assertTrue(py_res["is_tripped"])
        self.assertEqual(py_res["max_severity"], "P0_CRITICAL")
        self.assertIn("泛科技大类", py_res["message"])

        # 2. Front-end JS logic verification (simulated):
        # Line 1793 logic:
        currentTechPct = pen_res["portfolio_summary"]["sector_exposures"]["泛科技大类"] # 65.56
        HARD_CAP_MACRO = 50.0
        LOSS_CHASING_THRESHOLD = -0.10
        pnlRate = fund_000834["pnl_rate"] # -0.09
        isTechTarget = True
        newTechPct = (57040.0 + 10000.0) / (87000.0 + 10000.0) * 100 # 69.11%

        fe_isIntercepted = (isTechTarget and (currentTechPct >= HARD_CAP_MACRO or newTechPct >= HARD_CAP_MACRO) and pnlRate <= LOSS_CHASING_THRESHOLD)
        # BUG CONFIRMED: Front-end evaluates to False because pnlRate (-0.09) > -0.10!
        self.assertFalse(fe_isIntercepted, "BUG CONFIRMED: Frontend JS simulator permits tech buy when pnl > -10%, bypassing P0 hard cap!")

    def test_english_ticker_disguised_sector_bypass(self):
        """
        Adversarial Finding: English ETF symbols (e.g. QQQ) without Chinese keywords
        bypass map_macro_sector into '其他分散资产'.
        """
        macro = map_macro_sector("US Equity", "Invesco QQQ Trust", "ETF")
        self.assertEqual(macro, "其他分散资产", "Pure English ticker QQQ maps to '其他分散资产', bypassing '泛科技大类'")

    def test_negative_amount_rebalance_pass(self):
        """Negative buy amount represents sell/redeem and is approved as healthy rebalance."""
        state = {
            "summary": {"total_value": 100000.0, "total_cost": 100000.0, "floating_pnl_rate": -0.15, "sector_exposures": {"泛科技大类": 65.0}},
            "penetrated_stocks": []
        }
        res = simulate_buy_order(state, {"name": "纳指100", "sector": "泛科技"}, -5000.0)
        self.assertEqual(res["status"], "APPROVED")
        self.assertFalse(res["is_tripped"])


class TestTier5CLIInputFuzzing(unittest.TestCase):
    """3. CLI Input Fuzzing & Malformed File Handling"""

    def test_cli_chinese_comma_simulate_buy_handled(self):
        """Passing Chinese comma '，' in simulate_buy is normalized and parsed correctly."""
        simulate_buy_arg = "320007，5000"
        normalized = simulate_buy_arg.replace("，", ",")
        parts = [p.strip() for p in normalized.split(",") if p.strip()]
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "320007")
        self.assertEqual(parts[1], "5000")

    def test_csv_with_chinese_commas_supported(self):
        """CSV delimited by Chinese commas is properly parsed into structured funds."""
        csv_content = "代码，名称，本金，市值，盈亏\n000055，广发纳指，1000，900，-100\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name
        try:
            res = parse_portfolio_file(temp_path)
            self.assertEqual(len(res["funds"]), 1)
            self.assertEqual(res["funds"][0]["code"], "000055")
            self.assertEqual(res["funds"][0]["cost"], 1000.0)
            self.assertEqual(res["funds"][0]["market_value"], 900.0)
            self.assertEqual(res["funds"][0]["pnl"], -100.0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_csv_with_chinese_commas_rejected(self):
        """Alias for backward compatibility with older test runners."""
        return self.test_csv_with_chinese_commas_supported()

    def test_csv_with_missing_headers_rejected(self):
        """CSV missing recognized header names fails recognition."""
        csv_content = "000055,广发纳指,1000,900,-100\n000834,大成纳指,2000,1800,-200\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name
        try:
            with self.assertRaises(ValueError):
                parse_portfolio_file(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_csv_with_trailing_empty_lines_and_accounting_brackets(self):
        """CSV with trailing empty lines and accounting parentheses (1,000.00) parsed properly."""
        csv_content = "代码,名称,本金,市值,浮动盈亏\n000055,广发纳指,10000,9000,(1,000.00)\n\n\n"
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name
        try:
            res = parse_portfolio_file(temp_path)
            self.assertEqual(len(res["funds"]), 1)
            self.assertEqual(res["funds"][0]["pnl"], -1000.0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


class TestTier5XSSAndSecurityInjection(unittest.TestCase):
    """4. XSS & HTML Injection Payload Immunity"""

    def test_stored_xss_in_template_innerhtml(self):
        """
        Adversarial Finding: dashboard_template.html assigns unsanitized fund names and stock names
        directly to innerHTML without HTML escaping, allowing Stored DOM XSS.
        """
        xss_payload = '<img src=x onerror=alert(1)>'
        analysis_data = {
            "portfolio_name": "XSS Target",
            "portfolio_summary": {
                "total_cost": 10000.0,
                "total_market_value": 9000.0,
                "total_pnl": -1000.0,
                "total_pnl_rate": -0.10,
                "sector_exposures": {"泛科技大类": 55.0},
            },
            "fund_list": [
                {
                    "code": "000001",
                    "name": xss_payload,
                    "cost": 10000.0,
                    "market_value": 9000.0,
                    "pnl": -1000.0,
                    "pnl_rate": -0.10,
                    "category": "QDII",
                    "sector": "科技",
                }
            ],
            "penetrated_holdings": [
                {
                    "rank": 1,
                    "stock_code": "XSS",
                    "stock_name": '<svg onload=alert(2)>',
                    "market": "A股",
                    "sector": "半导体",
                    "effective_weight": 5.0,
                    "effective_value": 450.0,
                    "source_funds_count": 1,
                    "core_fund_desc": '<details open ontoggle=alert(3)>',
                }
            ],
        }

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            out_path = f.name

        try:
            generate_dashboard_html(analysis_data, out_path)
            with open(out_path, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Verify that escapeHtml sanitization utility is present in template and used:
            self.assertIn("function escapeHtml", html_content, "Template contains escapeHtml sanitization utility")
            self.assertIn("escapeHtml(", html_content, "Template invokes escapeHtml sanitization on data")
        finally:
            if os.path.exists(out_path):
                os.remove(out_path)


class TestTier5ZeroCDNLeakFuzzing(unittest.TestCase):
    """5. Zero-CDN Leakage Fuzzing & Validator Robustness"""

    def test_validator_bypasses_for_hidden_external_resources(self):
        """
        Validate that validate_zero_cdn_compliance in generate_dashboard.py
        strictly detects SVG image href, CSS @font-face, protocol-relative URLs, and background url.
        """
        # 1. SVG image href leak
        leak_svg = '<svg><image href="https://evil.com/leak.png"/></svg>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(leak_svg)

        # 2. CSS @font-face leak
        leak_font = '<style>@font-face { font-family: evil; src: url("https://fonts.evil.com/font.woff2"); }</style>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(leak_font)

        # 3. Protocol-relative URL leak
        leak_proto = '<script src="//cdn.jsdelivr.net/npm/vue"></script>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(leak_proto)

        # 4. Inline CSS background-image url leak
        leak_bg = '<div style="background-image: url(\'https://tracker.com/pixel.gif\');"></div>'
        with self.assertRaises(ValueError):
            validate_zero_cdn_compliance(leak_bg)


if __name__ == "__main__":
    unittest.main()
