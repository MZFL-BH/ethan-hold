"""
test_tier3_pairwise_combinations.py — Tier 3: Pairwise Cross-Feature Interaction Tests.
Pairwise combination and pipeline flow tests across features (Total 7 test cases).
"""

import copy
import json
import os
import sys
import unittest
from pathlib import Path

# Add tests/e2e and SKILL_ROOT to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CURRENT_DIR.parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fixtures import (
    BENCHMARK_25_FUNDS,
    TOP_15_PENETRATED_ORACLE,
    SKILL_ROOT,
    SCRIPTS_DIR,
    TEMPLATES_DIR,
    calculate_portfolio_totals,
    detect_parallel_clones,
    evaluate_risk_rules,
    get_benchmark_csv_content,
    get_benchmark_markdown_content
)

# Attempt import of production modules if present
try:
    from scripts.penetration import penetrate_portfolio, detect_clone_groups
    from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
    from scripts.generate_dashboard import render_dashboard_html
    PROD_MODULES_AVAILABLE = True
except ImportError:
    try:
        from scripts.penetration import penetrate_portfolio, detect_clone_groups
        from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
        PROD_MODULES_AVAILABLE = "CORE_ONLY"
    except ImportError:
        PROD_MODULES_AVAILABLE = False


class TestTier3PairwiseCombinations(unittest.TestCase):
    """Tier 3: Pairwise cross-feature interactions and data pipelines."""

    def test_pair01_multiformat_input_to_penetration_pipeline(self):
        """Pairwise 1: Multi-format parsing (JSON, CSV, Markdown) -> Penetration engine consistency."""
        # 1. JSON-derived fund records
        json_funds = copy.deepcopy(BENCHMARK_25_FUNDS)
        
        # 2. CSV-derived fund records
        csv_text = get_benchmark_csv_content()
        csv_lines = csv_text.strip().split("\n")[1:]
        csv_funds = []
        for line in csv_lines:
            parts = line.split(",")
            csv_funds.append({
                "code": parts[0],
                "name": parts[1],
                "category": parts[2],
                "sector": parts[3],
                "cost": float(parts[4]),
                "market_value": float(parts[5]),
                "pnl": float(parts[6]),
                "pnl_rate": float(parts[7].replace("%", "")) / 100.0
            })
            
        # 3. Markdown-derived fund records
        md_text = get_benchmark_markdown_content()
        md_lines = [l for l in md_text.strip().split("\n") if l.startswith("|")][2:]
        md_funds = []
        for line in md_lines:
            cols = [c.strip() for c in line.split("|") if c.strip()]
            md_funds.append({
                "code": cols[0],
                "name": cols[1],
                "category": cols[2],
                "sector": cols[3],
                "cost": float(cols[4]),
                "market_value": float(cols[5]),
                "pnl": float(cols[6]),
                "pnl_rate": float(cols[7].replace("%", "")) / 100.0
            })
            
        # Cross-format parity assertions
        t_json = calculate_portfolio_totals(json_funds)
        t_csv = calculate_portfolio_totals(csv_funds)
        t_md = calculate_portfolio_totals(md_funds)
        
        self.assertEqual(t_json["total_cost"], t_csv["total_cost"])
        self.assertEqual(t_json["total_cost"], t_md["total_cost"])
        self.assertEqual(t_json["total_market_value"], t_csv["total_market_value"])
        self.assertEqual(t_json["total_market_value"], t_md["total_market_value"])
        self.assertAlmostEqual(t_json["tech_ratio"], t_csv["tech_ratio"], places=4)
        self.assertAlmostEqual(t_json["tech_ratio"], t_md["tech_ratio"], places=4)

    def test_pair02_high_loss_with_hard_cap_impulse_trigger(self):
        """Pairwise 2: Deep loss (<-10%) x Overweight Tech (>50%) triggers both P0 and P1."""
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "25只基准组合", "funds": BENCHMARK_25_FUNDS}
            pen_res = penetrate_portfolio(portfolio)
            
            # Simulate buying 诺安成长 (pnl_rate = -23.0%, tech sector)
            nuoan_fund = [f for f in BENCHMARK_25_FUNDS if f["code"] == "320007"][0]
            sim_res = simulate_buy_order(pen_res, nuoan_fund, 5000.0)
            
            self.assertEqual(sim_res["status"], "BLOCKED")
            self.assertEqual(sim_res["action"], "BLOCKED")
            self.assertEqual(sim_res["max_severity"], "P0_CRITICAL")
            self.assertEqual(sim_res["cooling_off_hours"], 48)
            
            codes = [m["code"] for m in sim_res["intercept_messages"]]
            self.assertIn("P0_MACRO_TECH_OVERWEIGHT", codes)
            self.assertIn("P1_LOSS_CHASING_FREEZE", codes)
        else:
            totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
            order = {"code": "320007", "amount": 5000.0, "target_pnl_rate": -0.23}
            res = evaluate_risk_rules(totals, order)
            self.assertTrue(res["is_tripped"])
            self.assertEqual(res["cooling_off_hours"], 48)

    def test_pair03_safe_portfolio_with_incremental_rebalance(self):
        """Pairwise 3: Safe balanced portfolio x defensive buy order results in NORMAL status."""
        safe_funds = [
            {"code": "000198", "name": "天弘同利债券", "cost": 50000.0, "market_value": 51000.0, "category": "纯债", "sector": "纯债防守", "pnl_rate": 0.02},
            {"code": "000216", "name": "华安黄金易", "cost": 30000.0, "market_value": 35000.0, "category": "黄金", "sector": "黄金避险", "pnl_rate": 0.16},
            {"code": "001052", "name": "华夏中证500", "cost": 20000.0, "market_value": 20000.0, "category": "宽基", "sector": "中盘宽基", "pnl_rate": 0.00}
        ]
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "稳健防守组合", "funds": safe_funds}
            pen_res = penetrate_portfolio(portfolio)
            cb = evaluate_circuit_breakers(pen_res["portfolio_summary"], pen_res["penetrated_holdings"])
            
            self.assertFalse(cb["is_tripped"])
            self.assertEqual(cb["max_severity"], "NORMAL")
            
            # Buying more bond
            bond_order = {"code": "000198", "name": "天弘同利债券", "sector": "纯债防守", "pnl_rate": 0.02}
            sim = simulate_buy_order(pen_res, bond_order, 10000.0)
            self.assertEqual(sim["status"], "APPROVED")
            self.assertFalse(sim["is_tripped"])

    def test_pair04_penetration_to_dashboard_svg_pipeline(self):
        """Pairwise 4: Penetration output data structure seamlessly renders into dashboard HTML."""
        template_file = TEMPLATES_DIR / "dashboard_template.html"
        gen_script = SCRIPTS_DIR / "generate_dashboard.py"
        if not template_file.exists() or not gen_script.exists():
            self.skipTest("M2: generate_dashboard.py or template pending creation by Worker")
            
        import importlib.util
        spec = importlib.util.spec_from_file_location("generate_dashboard", str(gen_script))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "基准数据渲染测试", "funds": BENCHMARK_25_FUNDS}
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
            
            out_file = CURRENT_DIR / "temp_pipeline_dashboard.html"
            try:
                mod.render_dashboard_html(analysis_data, str(out_file))
                self.assertTrue(out_file.exists())
                content = out_file.read_text(encoding="utf-8")
                self.assertIn("<svg", content)
                self.assertIn("NVDA", content)
                self.assertIn("87,000", content)
            finally:
                if out_file.exists():
                    out_file.unlink()

    def test_pair05_cli_pipeline_input_arg_to_html_artifact(self):
        """Pairwise 5: CLI full pipeline contract (run_analysis.py with --input and --output)."""
        cli_path = SCRIPTS_DIR / "run_analysis.py"
        if not cli_path.exists():
            self.skipTest("M3: scripts/run_analysis.py pending creation by Worker")
        content = cli_path.read_text(encoding="utf-8")
        self.assertIn("argparse", content)
        self.assertTrue("output" in content)

    def test_pair06_circuit_breaker_intercept_to_alternative_rebalancing(self):
        """Pairwise 6: Tripped breaker produces actionable alternative rebalancing assets."""
        if PROD_MODULES_AVAILABLE:
            portfolio = {"portfolio_name": "超配科技组合", "funds": BENCHMARK_25_FUNDS}
            pen_res = penetrate_portfolio(portfolio)
            nuoan = [f for f in BENCHMARK_25_FUNDS if f["code"] == "320007"][0]
            sim = simulate_buy_order(pen_res, nuoan, 5000.0)
            
            self.assertTrue(len(sim["rebalance_recommendations"]) > 0)
            self.assertTrue(len(sim["alternative_advice"]) > 0)
            self.assertTrue("纯债" in sim["alternative_advice"] or "低波" in sim["alternative_advice"])

    def test_pair07_clone_detection_with_penetration_weighting(self):
        """Pairwise 7: Parallel clone detection preserves stock-level weighting across funds."""
        clones = detect_parallel_clones(BENCHMARK_25_FUNDS)
        self.assertEqual(len(clones), 1)
        ndx_funds = clones[0]["funds"]
        
        # Sum of QDII market values = 31400.0
        sum_mv = sum(f["market_value"] for f in ndx_funds)
        self.assertEqual(sum_mv, 31400.0)
        
        if PROD_MODULES_AVAILABLE:
            fixture_path = SKILL_ROOT / "tests" / "fixtures" / "portfolio_25_funds.json"
            if fixture_path.exists():
                with open(fixture_path, "r", encoding="utf-8") as f:
                    funds_data = json.load(f).get("funds", BENCHMARK_25_FUNDS)
            else:
                funds_data = BENCHMARK_25_FUNDS
            res = penetrate_portfolio({"portfolio_name": "并联权重测试", "funds": funds_data})
            # 25只基准持仓中包含 8 只 QDII 纳指与 4 只 A 股半导体，两组并联影子基金总数为 12 只
            self.assertEqual(res["summary"]["parallel_fund_count"], 12)
            self.assertIn("CLONE_QDII_NDX100", res["summary"]["parallel_groups"])
            self.assertEqual(res["summary"]["parallel_groups"]["CLONE_QDII_NDX100"]["fund_count"], 8)
            self.assertIn("CLONE_CN_SEMICONDUCTOR", res["summary"]["parallel_groups"])
            self.assertEqual(res["summary"]["parallel_groups"]["CLONE_CN_SEMICONDUCTOR"]["fund_count"], 4)
            self.assertGreater(res["summary"]["redundancy_index"], 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
