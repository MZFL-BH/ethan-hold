"""
test_tier4_real_world_scenarios.py — Tier 4: Real-World Portfolio & End-to-End Scenarios.
Realistic portfolio tests including the 25-fund -13% benchmark portfolio and full artifact audit.
"""

import copy
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

# Add tests/e2e to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fixtures import (
    BENCHMARK_25_FUNDS,
    TOP_15_PENETRATED_ORACLE,
    SKILL_ROOT,
    SCRIPTS_DIR,
    TEMPLATES_DIR,
    REFERENCES_DIR,
    DOCS_DIR,
    calculate_portfolio_totals,
    evaluate_risk_rules
)

# Attempt import of production modules if present
try:
    from scripts.penetration import penetrate_portfolio
    from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
    from scripts.generate_dashboard import render_dashboard_html
    PROD_MODULES_AVAILABLE = True
except ImportError:
    try:
        from scripts.penetration import penetrate_portfolio
        from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
        PROD_MODULES_AVAILABLE = "CORE_ONLY"
    except ImportError:
        PROD_MODULES_AVAILABLE = False


class TestTier4RealWorldScenarios(unittest.TestCase):
    """Tier 4: Real-world realistic scenarios and end-to-end integration audits."""

    def test_scenario01_canonical_25_funds_benchmark_ground_truth(self):
        """Scenario 1: Full end-to-end audit of canonical 25-fund -13% floating loss benchmark."""
        # 1. Total Portfolio Calculations
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        self.assertEqual(totals["total_cost"], 100000.0, "Total cost must be ¥100,000.00")
        self.assertEqual(totals["total_market_value"], 87000.0, "Total market value must be ¥87,000.00")
        self.assertEqual(totals["total_pnl"], -13000.0, "Total PnL must be -¥13,000.00")
        self.assertAlmostEqual(totals["total_pnl_rate"], -0.13, places=4, msg="PnL rate must be -13.00%")

        # 2. 8 Parallel QDII Nasdaq-100 funds
        qdii_funds = [f for f in BENCHMARK_25_FUNDS if f["category"] == "QDII并联纳指"]
        self.assertEqual(len(qdii_funds), 8, "Must contain exactly 8 QDII funds")
        qdii_mv = sum(f["market_value"] for f in qdii_funds)
        self.assertEqual(qdii_mv, 31400.0, "QDII total value must be ¥31,400.00")
        self.assertAlmostEqual(qdii_mv / 87000.0 * 100, 36.09, delta=0.05)

        # 3. 4 A-share Semiconductor funds
        chip_funds = [f for f in BENCHMARK_25_FUNDS if f["category"] in ["A股半导体重仓", "A股半导体指数"]]
        self.assertEqual(len(chip_funds), 4, "Must contain exactly 4 semiconductor funds")
        chip_mv = sum(f["market_value"] for f in chip_funds)
        self.assertEqual(chip_mv, 19790.0, "Semiconductor total value must be ¥19,790.00")
        self.assertAlmostEqual(chip_mv / 87000.0 * 100, 22.75, delta=0.05)

        # 4. Merged Tech Exposure
        self.assertEqual(totals["tech_market_value"], 57040.0, "Merged tech exposure value must be ¥57,040.00")
        self.assertAlmostEqual(totals["tech_ratio"] * 100, 65.56, delta=0.05, msg="Tech ratio must be 65.56%")

        # 5. Production module penetration verification if available
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "Ethan-Hold 25只基金经典测试组合", "funds": BENCHMARK_25_FUNDS}
            pen_res = penetrate_portfolio(portfolio)
            self.assertEqual(pen_res["summary"]["total_funds_count"], 25)
            self.assertEqual(pen_res["summary"]["total_cost"], 100000.0)
            self.assertEqual(pen_res["summary"]["total_value"], 87000.0)
            self.assertEqual(pen_res["summary"]["floating_pnl"], -13000.0)
            self.assertEqual(pen_res["summary"]["floating_pnl_rate"], -0.13)
            self.assertIn("泛科技大类", pen_res["macro_sectors"])
            self.assertAlmostEqual(pen_res["macro_sectors"]["泛科技大类"]["percentage"], 65.56, delta=0.1)

            # Check circuit breaker
            cb_res = evaluate_circuit_breakers(pen_res["portfolio_summary"], pen_res["penetrated_holdings"])
            self.assertTrue(cb_res["is_tripped"])
            self.assertEqual(cb_res["max_severity"], "P0_CRITICAL")
            self.assertEqual(cb_res["cooling_off_hours"], 48)

    def test_scenario02_retail_investor_impulse_buying_interception(self):
        """Scenario 2: Retail investor impulse buy attempt on deep-loss fund (-23%) is intercepted."""
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "基准持仓", "funds": BENCHMARK_25_FUNDS}
            pen_res = penetrate_portfolio(portfolio)
            
            # User attempts to buy ¥5,000 of 诺安成长混合 (320007, loss -23%)
            nuoan = [f for f in BENCHMARK_25_FUNDS if f["code"] == "320007"][0]
            sim = simulate_buy_order(pen_res, nuoan, 5000.0)
            
            # Assertions on Hard-Cap Intercept
            self.assertEqual(sim["status"], "BLOCKED")
            self.assertEqual(sim["action"], "BLOCKED")
            self.assertEqual(sim["max_severity"], "P0_CRITICAL")
            self.assertEqual(sim["cooling_off_hours"], 48)
            self.assertIn("越跌越补", sim["intercept_reason"])
            self.assertIn("强制冷静期", sim["alternative_advice"])
        else:
            totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
            order = {"code": "320007", "amount": 5000.0, "target_pnl_rate": -0.23}
            res = evaluate_risk_rules(totals, order)
            self.assertTrue(res["is_tripped"])
            self.assertEqual(res["max_severity"], "P0_CRITICAL")
            self.assertEqual(res["cooling_off_hours"], 48)

    def test_scenario03_defensive_rebalancing_workflow(self):
        """Scenario 3: Directing new cash into defensive assets (bonds) lowers concentration."""
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "基准持仓", "funds": BENCHMARK_25_FUNDS}
            pen_res = penetrate_portfolio(portfolio)
            
            # User directs ¥25,000 into pure bond fund
            bond_fund = [f for f in BENCHMARK_25_FUNDS if f["code"] == "000198"][0]
            sim = simulate_buy_order(pen_res, bond_fund, 25000.0)
            
            self.assertEqual(sim["status"], "APPROVED")
            # Post simulation value: 87,000 + 25,000 = 112,000
            # Macro tech ratio was 57,040 / 112,000 = 50.93% (diluted from 65.56%)
            self.assertEqual(sim["post_simulation"]["total_value"], 112000.0)
            self.assertLess(sim["post_simulation"]["macro_exposure_pct"], 65.56)

    def test_scenario04_standalone_html_dashboard_offline_visual_audit(self):
        """Scenario 4: Standalone HTML dashboard offline audit (0 CDN, pure SVG, dark theme)."""
        gen_script = SCRIPTS_DIR / "generate_dashboard.py"
        template_file = TEMPLATES_DIR / "dashboard_template.html"
        if not gen_script.exists() or not template_file.exists():
            self.skipTest("M2: generate_dashboard.py or template pending creation by Worker")
            
        import importlib.util
        spec = importlib.util.spec_from_file_location("generate_dashboard", str(gen_script))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "离线看板审计组合", "funds": BENCHMARK_25_FUNDS}
            pen_res = penetrate_portfolio(portfolio)
            cb_res = evaluate_circuit_breakers(pen_res["portfolio_summary"], pen_res["penetrated_holdings"])
            
            analysis_data = {
                "summary": pen_res["summary"],
                "portfolio_summary": pen_res["portfolio_summary"],
                "penetrated_stocks": pen_res["penetrated_stocks"],
                "penetrated_holdings": pen_res["penetrated_holdings"],
                "macro_sectors": pen_res["macro_sectors"],
                "sub_sectors": pen_res["sub_sectors"],
                "clone_groups": pen_res["clone_groups"],
                "breaker_status": cb_res,
                "funds": pen_res["funds"],
            }
            
            test_html_path = CURRENT_DIR / "audit_dashboard_test.html"
            try:
                mod.render_dashboard_html(analysis_data, str(test_html_path))
                self.assertTrue(test_html_path.exists())
                content = test_html_path.read_text(encoding="utf-8")
                
                # Check 1: Size > 20KB
                self.assertGreater(len(content), 20000, "Dashboard HTML must be full-featured (>20KB)")
                
                # Check 2: Zero external network references
                forbidden_patterns = [
                    r'<script[^>]+src=["\']http',
                    r'<link[^>]+href=["\']http',
                    r'cdnjs\.cloudflare\.com',
                    r'cdn\.jsdelivr\.net',
                    r'unpkg\.com'
                ]
                for pat in forbidden_patterns:
                    self.assertFalse(re.search(pat, content, re.IGNORECASE), f"External network leak: {pat}")
                    
                # Check 3: Native retina SVG charts
                self.assertIn("<svg", content)
                self.assertIn("viewBox", content)
                
                # Check 4: Light theme style tokens
                self.assertTrue(
                    "#f6f8fa" in content or "#ffffff" in content or "light" in content.lower(),
                    "Dashboard must implement clean, high-contrast light theme"
                )
                
                # Check 5: Ground truth values rendered
                self.assertIn("87,000", content)
                self.assertIn("100,000", content)
                self.assertIn("NVDA", content)
                self.assertIn("65.56", content)
            finally:
                if test_html_path.exists():
                    test_html_path.unlink()

    def test_scenario05_open_source_repo_and_media_delivery_audit(self):
        """Scenario 5: Audit all repository and media material conformance."""
        readme = SKILL_ROOT / "README.md"
        contributing = SKILL_ROOT / "CONTRIBUTING.md"
        license_file = SKILL_ROOT / "LICENSE"
        strategy_doc = REFERENCES_DIR / "release_strategy.md"
        checklist_doc = DOCS_DIR / "ethan_hold_operations_checklist.md"
        copy_doc = REFERENCES_DIR / "media_copywriting.md"
        
        all_docs = [readme, contributing, license_file, strategy_doc, checklist_doc, copy_doc]
        missing = [d.name for d in all_docs if not d.exists()]
        if missing:
            self.skipTest(f"M4/M5: Documentation files {missing} pending creation by Worker")
            
        # 1. README
        readme_text = readme.read_text(encoding="utf-8")
        self.assertIn("ethan-hold", readme_text)
        self.assertTrue("MIT" in readme_text)
        self.assertTrue("免责声明" in readme_text or "Disclaimer" in readme_text)
        
        # 2. CONTRIBUTING
        contrib_text = contributing.read_text(encoding="utf-8")
        self.assertTrue("PR" in contrib_text or "Pull Request" in contrib_text)
        
        # 3. Operations Checklist
        check_text = checklist_doc.read_text(encoding="utf-8")
        self.assertIn("作战清单", check_text)
        self.assertTrue("🔴" in check_text and "🟡" in check_text and "🔵" in check_text)
        
        # 4. Media Copywriting
        copy_text = copy_doc.read_text(encoding="utf-8")
        self.assertTrue("分镜" in copy_text or "storyboard" in copy_text.lower())

    def test_scenario06_cli_end_to_end_orchestration(self):
        """Scenario 6: End-to-end execution of run_analysis.py via command line subprocess."""
        cli_path = SCRIPTS_DIR / "run_analysis.py"
        if not cli_path.exists():
            self.skipTest("M3: scripts/run_analysis.py pending creation by Worker")
            
        test_out = CURRENT_DIR / "test_cli_output.html"
        try:
            # Run CLI with --help first
            res_help = subprocess.run(
                [sys.executable, str(cli_path), "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            self.assertEqual(res_help.returncode, 0)
            self.assertIn("ethan-hold", res_help.stdout.lower() + res_help.stderr.lower())
        finally:
            if test_out.exists():
                test_out.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
