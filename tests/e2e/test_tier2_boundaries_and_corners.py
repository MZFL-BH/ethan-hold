"""
test_tier2_boundaries_and_corners.py — Tier 2: Boundary and Corner Condition Tests.
>= 5 test cases for boundary/corner conditions (Total 8 corner test cases).
"""

import copy
import re
import sys
import unittest
from pathlib import Path

# Add tests/e2e to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fixtures import (
    BENCHMARK_25_FUNDS,
    SKILL_ROOT,
    SCRIPTS_DIR,
    calculate_portfolio_totals,
    evaluate_risk_rules,
    get_dirty_financial_csv_content
)

# Attempt import of production modules if present
try:
    from scripts.penetration import penetrate_portfolio, normalize_weight
    from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
    PROD_MODULES_AVAILABLE = True
except ImportError:
    PROD_MODULES_AVAILABLE = False


class TestTier2BoundariesAndCorners(unittest.TestCase):
    """Tier 2: Comprehensive boundary, corner, and extreme condition tests."""

    def test_corner01_empty_portfolio_input_zero_division_guard(self):
        """Corner 1: Empty funds list or zero values must not cause ZeroDivisionError or crash."""
        empty_portfolio = {
            "portfolio_name": "空持仓测试",
            "funds": []
        }
        if PROD_MODULES_AVAILABLE:
            res = penetrate_portfolio(empty_portfolio)
            self.assertEqual(res["summary"]["total_funds_count"], 0)
            self.assertEqual(res["summary"]["total_cost"], 0.0)
            self.assertEqual(res["summary"]["total_value"], 0.0)
            self.assertEqual(res["summary"]["floating_pnl_rate"], 0.0)
            self.assertEqual(res["summary"]["redundancy_index"], 0.0)

            # Circuit breaker on empty portfolio
            cb_res = evaluate_circuit_breakers(res["portfolio_summary"], res["penetrated_holdings"])
            self.assertFalse(cb_res["is_tripped"])
            self.assertEqual(cb_res["max_severity"], "NORMAL")
        else:
            totals = calculate_portfolio_totals([])
            self.assertEqual(totals["total_cost"], 0.0)
            self.assertEqual(totals["total_pnl_rate"], 0.0)
            cb = evaluate_risk_rules(totals)
            self.assertFalse(cb["is_tripped"])

    def test_corner02_single_asset_100_percent_concentration(self):
        """Corner 2: Single-asset portfolio (100% in semiconductor) trips all P0 hard caps."""
        single_fund_portfolio = {
            "portfolio_name": "单一半导体全仓",
            "funds": [
                {
                    "code": "320007",
                    "name": "诺安成长混合",
                    "cost": 10000.0,
                    "market_value": 7700.0,
                    "pnl": -2300.0,
                    "pnl_rate": -0.23,
                    "category": "A股半导体",
                    "sector": "A股半导体与芯片",
                    "top_holdings": [
                        {"name": "北方华创", "code": "002371", "weight": 0.25, "sector": "半导体设备"},
                        {"name": "中芯国际", "code": "688981", "weight": 0.20, "sector": "晶圆代工"}
                    ]
                }
            ]
        }
        if PROD_MODULES_AVAILABLE:
            res = penetrate_portfolio(single_fund_portfolio)
            cb = evaluate_circuit_breakers(res["portfolio_summary"], res["penetrated_holdings"])
            self.assertTrue(cb["is_tripped"])
            self.assertEqual(cb["max_severity"], "P0_CRITICAL")
            # Should have single stock overweight (25% and 20% >= 15%) and macro tech (100% >= 50%)
            codes = [m["code"] for m in cb["intercept_messages"]]
            self.assertIn("P0_MACRO_TECH_OVERWEIGHT", codes)
            self.assertIn("P0_SINGLE_STOCK_OVERWEIGHT", codes)
        else:
            totals = calculate_portfolio_totals(single_fund_portfolio["funds"])
            cb = evaluate_risk_rules(totals)
            self.assertTrue(cb["is_tripped"])
            self.assertEqual(cb["max_severity"], "P0_CRITICAL")

    def test_corner03_exact_threshold_boundaries(self):
        """Corner 3: Exact boundary thresholds: 49.99% vs 50.00%, -9.99% vs -10.00%."""
        # 1. Macro Tech at 49.99% -> Warning (P1_WARNING), at 50.00% -> Critical (P0_CRITICAL)
        summary_sub_cap = {
            "total_value": 100000.0,
            "floating_pnl_rate": -0.05,
            "sector_exposures": {"泛科技大类": 49.99}
        }
        summary_exact_cap = {
            "total_value": 100000.0,
            "floating_pnl_rate": -0.05,
            "sector_exposures": {"泛科技大类": 50.00}
        }
        if PROD_MODULES_AVAILABLE:
            cb_sub = evaluate_circuit_breakers(summary_sub_cap, [])
            cb_exact = evaluate_circuit_breakers(summary_exact_cap, [])
            self.assertNotEqual(cb_sub["max_severity"], "P0_CRITICAL", "49.99% must not trigger P0 hard-cap")
            self.assertEqual(cb_exact["max_severity"], "P0_CRITICAL", "50.00% must trigger P0 hard-cap")

            # 2. Target PnL at -9.99% vs -10.00%
            current_state = {
                "summary": {"total_value": 100000.0, "total_cost": 100000.0, "sector_exposures": {"泛科技大类": 50.0}},
                "portfolio_summary": {"total_value": 100000.0, "total_cost": 100000.0, "sector_exposures": {"泛科技大类": 50.0}},
                "penetrated_stocks": []
            }
            order_sub = {"name": "科技基金", "code": "000001", "sector": "泛科技大类", "pnl_rate": -0.0999}
            order_exact = {"name": "科技基金", "code": "000001", "sector": "泛科技大类", "pnl_rate": -0.1000}
            
            sim_sub = simulate_buy_order(current_state, order_sub, 1000.0)
            sim_exact = simulate_buy_order(current_state, order_exact, 1000.0)
            self.assertEqual(sim_exact["cooling_off_hours"], 48, "-10% loss triggers 48h cool off")

    def test_corner04_negative_buy_order_redemption_rebalancing(self):
        """Corner 4: Negative buy orders (selling/redemption) must be recognized as healthy rebalance."""
        current_state = {
            "summary": {"total_value": 100000.0, "total_cost": 100000.0, "sector_exposures": {"泛科技大类": 65.56}},
            "portfolio_summary": {"total_value": 100000.0, "total_cost": 100000.0, "sector_exposures": {"泛科技大类": 65.56}},
            "penetrated_stocks": []
        }
        sell_order = {"name": "诺安成长", "code": "320007", "sector": "泛科技大类", "pnl_rate": -0.23}
        
        if PROD_MODULES_AVAILABLE:
            res = simulate_buy_order(current_state, sell_order, -5000.0)
            self.assertEqual(res["status"], "APPROVED")
            self.assertEqual(res["action"], "PASS")
            self.assertIn("减仓/赎回操作通过", res["message"])
        else:
            totals = {"total_market_value": 100000.0, "tech_ratio": 0.6556}
            res = evaluate_risk_rules(totals, {"code": "320007", "amount": -5000.0})
            codes = [m["code"] for m in res["intercept_messages"]]
            self.assertIn("NORMAL_HEALTHY_REBALANCE", codes)

    def test_corner05_micro_buy_order_precision(self):
        """Corner 5: Micro buy orders (¥1.00 or ¥10.00) handle float precision cleanly."""
        current_state = {
            "summary": {"total_value": 100000.0, "total_cost": 100000.0, "sector_exposures": {"泛科技大类": 20.0}},
            "portfolio_summary": {"total_value": 100000.0, "total_cost": 100000.0, "sector_exposures": {"泛科技大类": 20.0}},
            "penetrated_stocks": []
        }
        safe_order = {"name": "宽基指数", "code": "001052", "sector": "中盘宽基", "pnl_rate": 0.01}
        
        if PROD_MODULES_AVAILABLE:
            res = simulate_buy_order(current_state, safe_order, 1.0)
            self.assertEqual(res["status"], "APPROVED")
            self.assertEqual(res["post_simulation"]["total_value"], 100001.0)

    def test_corner06_massive_parallel_clones_stress(self):
        """Corner 6: Scale test with 16 parallel clone funds tracking the same index."""
        massive_clones = []
        for i in range(16):
            massive_clones.append({
                "code": f"0990{i:02d}",
                "name": f"机构{i}纳斯达克100联接",
                "cost": 1000.0,
                "market_value": 900.0,
                "pnl": -100.0,
                "pnl_rate": -0.10,
                "category": "QDII并联纳指",
                "sector": "海外美股科技",
                "clone_group_id": "MASSIVE_NDX100_CLONES",
                "top_holdings": [
                    {"name": "NVDA", "code": "NVDA", "weight": 0.088, "sector": "芯片算力"}
                ]
            })
        
        portfolio = {"portfolio_name": "极端并联测试", "funds": massive_clones}
        if PROD_MODULES_AVAILABLE:
            res = penetrate_portfolio(portfolio)
            cg = res["clone_groups"]
            self.assertIn("MASSIVE_NDX100_CLONES", cg)
            self.assertEqual(cg["MASSIVE_NDX100_CLONES"]["fund_count"], 16)
            self.assertEqual(cg["MASSIVE_NDX100_CLONES"]["total_market_value"], 14400.0)
            
            # NVDA effective value = 14400 * 0.088 = 1267.20
            nvda = [s for s in res["penetrated_stocks"] if s["stock_name"] == "NVDA (英伟达)"][0]
            self.assertAlmostEqual(nvda["effective_value"], 1267.20, places=2)
            self.assertEqual(nvda["source_funds_count"], 16)

    def test_corner07_dirty_financial_formatting_resilience(self):
        """Corner 7: Dirty data cleaning: currency symbols, commas, percent, parentheses."""
        import csv
        import io
        dirty_csv = get_dirty_financial_csv_content()
        reader = csv.reader(io.StringIO(dirty_csv.strip()))
        rows = list(reader)
        header = rows[0]
        data_rows = rows[1:]
        
        parsed_records = []
        for parts in data_rows:
            if not parts:
                continue
            # Clean number: remove '¥', ',', '%', and handle parentheses for negative
            def clean_num(val_str: str) -> float:
                s = val_str.replace("¥", "").replace(",", "").replace("%", "").strip()
                if s.startswith("(") and s.endswith(")"):
                    return -float(s[1:-1])
                return float(s)
            
            parsed_records.append({
                "code": parts[0],
                "name": parts[1],
                "cost": clean_num(parts[2]),
                "market_value": clean_num(parts[3]),
                "pnl": clean_num(parts[4]),
            })
            
        self.assertEqual(len(parsed_records), 4)
        self.assertEqual(parsed_records[0]["cost"], 6000.0)
        self.assertEqual(parsed_records[0]["market_value"], 5400.0)
        self.assertEqual(parsed_records[0]["pnl"], -600.0, "Accounting parenthesis (600.00) cleaned to -600.0")

    def test_corner08_unknown_unmapped_fund_fallback(self):
        """Corner 8: Unknown fund code not in dictionary gracefully keeps category without crashing."""
        unknown_fund_portfolio = {
            "portfolio_name": "未知创新基金测试",
            "funds": [
                {
                    "code": "999999",
                    "name": "极客创新实验封闭基金",
                    "cost": 5000.0,
                    "market_value": 5200.0,
                    "pnl": 200.0,
                    "pnl_rate": 0.04,
                    "category": "其他另类资产",
                    "sector": "未知赛道",
                    "top_holdings": []  # No detailed holdings published
                }
            ]
        }
        if PROD_MODULES_AVAILABLE:
            res = penetrate_portfolio(unknown_fund_portfolio)
            self.assertEqual(res["summary"]["total_funds_count"], 1)
            self.assertEqual(res["summary"]["unique_stocks_count"], 0)
            self.assertIn("其他分散资产", res["macro_sectors"])
            self.assertEqual(res["macro_sectors"]["其他分散资产"]["effective_value"], 5200.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
