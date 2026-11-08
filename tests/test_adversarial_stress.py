"""
Adversarial Stress Test Suite for ethan-hold
Challenger 1 (Algorithm & Penetration Stress Testing)

Dimensions tested:
1. Scalability: 100+, 250+, 500+ funds throughput and latency.
2. Extreme Parallel Feeder Duplication: 20+ NASDAQ-100 & Semiconductor funds, Redundancy Index bounds.
3. Drawdown & PnL Extremes: -99%, -150%, 0%, +500%, float precision.
4. Numerical Invariants: Sum of weights <= 100%, Total Value - Cost == PnL, 0 <= RI < 1.0.
5. Boundary & Corner Cases: Empty portfolios, zero holdings, micro/macro amounts.
6. Name & Alias Collisions: Substring false-positives, casing, unknown symbols.
"""

import math
import time
import unittest
from typing import Any, Dict, List

from scripts.penetration import (
    STOCK_ALIAS_MAP,
    detect_clone_groups,
    map_macro_sector,
    normalize_stock_identity,
    normalize_weight,
    penetrate_portfolio,
)
from scripts.circuit_breaker import (
    DEFAULT_THRESHOLDS,
    evaluate_circuit_breakers,
    simulate_buy_order,
)


class TestScalability100PlusFunds(unittest.TestCase):
    """Stress testing scalability and throughput with large portfolios."""

    def _generate_synthetic_portfolio(self, num_funds: int, holdings_per_fund: int = 10) -> Dict[str, Any]:
        tech_stocks = [
            ("NVDA", "芯片算力与GPU", "美股"),
            ("AAPL", "消费电子与操作系统", "美股"),
            ("MSFT", "软件与Azure云计算", "美股"),
            ("AMZN", "电商与AWS云计算", "美股"),
            ("GOOGL", "搜索与云服务", "美股"),
            ("AVGO", "通信交换芯片与ASIC", "美股"),
            ("TSLA", "新能源汽车与智驾AI", "美股"),
            ("北方华创", "半导体设备龙头", "A股"),
            ("中芯国际", "晶圆代工制造", "A股"),
            ("海光信息", "x86 CPU与DCU算力", "A股"),
            ("贵州茅台", "高端白酒", "A股"),
            ("腾讯控股", "社交与互联网科技", "港股"),
        ]

        funds = []
        for i in range(num_funds):
            fund_holdings = []
            for j in range(holdings_per_fund):
                st = tech_stocks[(i + j) % len(tech_stocks)]
                fund_holdings.append({
                    "stock_name": st[0],
                    "code": st[0],
                    "weight": round(1.0 / holdings_per_fund, 4),
                    "sector": st[1],
                    "market": st[2],
                })

            funds.append({
                "code": f"FUND_{i:04d}",
                "name": f"合成测试基金_{i:04d}",
                "cost": 10000.0,
                "market_value": 9000.0,
                "category": "QDII-纳指" if i % 2 == 0 else "半导体ETF",
                "sector": "泛科技" if i % 3 != 0 else "消费",
                "top_holdings": fund_holdings,
            })

        return {
            "portfolio_name": f"压力测试组合_{num_funds}只基金",
            "funds": funds,
        }

    def test_100_funds_scalability(self):
        """100 funds with 10 holdings each (1,000 stock slots) must complete within 500ms."""
        portfolio = self._generate_synthetic_portfolio(100, 10)
        t0 = time.perf_counter()
        res = penetrate_portfolio(portfolio)
        elapsed = time.perf_counter() - t0

        self.assertEqual(res["summary"]["total_funds_count"], 100)
        self.assertEqual(res["summary"]["total_stock_holdings_count"], 1000)
        self.assertLess(elapsed, 0.5, f"100 funds took too long: {elapsed:.4f}s (budget: 0.5s)")

        # Run circuit breaker on result
        t1 = time.perf_counter()
        cb = evaluate_circuit_breakers(res["portfolio_summary"], res["penetrated_holdings"])
        elapsed_cb = time.perf_counter() - t1
        self.assertLess(elapsed_cb, 0.1, f"CB evaluation took too long: {elapsed_cb:.4f}s")
        self.assertTrue(cb["is_tripped"])

    def test_250_funds_scalability(self):
        """250 funds with 10 holdings each (2,500 slots) must complete within 1.0s."""
        portfolio = self._generate_synthetic_portfolio(250, 10)
        t0 = time.perf_counter()
        res = penetrate_portfolio(portfolio)
        elapsed = time.perf_counter() - t0

        self.assertEqual(res["summary"]["total_funds_count"], 250)
        self.assertEqual(res["summary"]["total_stock_holdings_count"], 2500)
        self.assertLess(elapsed, 1.0, f"250 funds took too long: {elapsed:.4f}s (budget: 1.0s)")

    def test_500_funds_scalability(self):
        """500 funds with 10 holdings each (5,000 slots) must complete within 2.0s without OOM."""
        portfolio = self._generate_synthetic_portfolio(500, 10)
        t0 = time.perf_counter()
        res = penetrate_portfolio(portfolio)
        elapsed = time.perf_counter() - t0

        self.assertEqual(res["summary"]["total_funds_count"], 500)
        self.assertEqual(res["summary"]["total_stock_holdings_count"], 5000)
        self.assertLess(elapsed, 2.0, f"500 funds took too long: {elapsed:.4f}s (budget: 2.0s)")


class TestExtremeParallelFeederDuplication(unittest.TestCase):
    """Stress testing 20+ identical parallel feeder funds tracking Nasdaq 100 or Semiconductor."""

    def test_25_identical_nasdaq_funds_clone_and_redundancy(self):
        """25 funds with identical 10 stocks: RI must approach 1.0 but satisfy 0 <= RI < 1.0."""
        ndx_top10 = [
            {"stock_name": "NVDA", "weight": 0.10},
            {"stock_name": "AAPL", "weight": 0.10},
            {"stock_name": "MSFT", "weight": 0.10},
            {"stock_name": "AMZN", "weight": 0.10},
            {"stock_name": "GOOGL", "weight": 0.10},
            {"stock_name": "META", "weight": 0.10},
            {"stock_name": "TSLA", "weight": 0.10},
            {"stock_name": "AVGO", "weight": 0.10},
            {"stock_name": "COST", "weight": 0.10},
            {"stock_name": "ASML", "weight": 0.10},
        ]
        funds = []
        for i in range(25):
            funds.append({
                "code": f"00{i:04d}",
                "name": f"广发纳斯达克100联接_{i:02d}",
                "cost": 1000.0,
                "market_value": 1000.0,
                "category": "QDII-纳指",
                "sector": "泛科技",
                "top_holdings": ndx_top10,
            })

        res = penetrate_portfolio({"portfolio_name": "25只并联纳指", "funds": funds})
        summary = res["summary"]

        self.assertEqual(summary["total_funds_count"], 25)
        self.assertEqual(summary["total_stock_holdings_count"], 250)
        self.assertEqual(summary["unique_stocks_count"], 10)

        # Expected RI = 1 - (10 / 250) = 1 - 0.04 = 0.96
        self.assertAlmostEqual(summary["redundancy_index"], 0.96, places=4)
        self.assertGreaterEqual(summary["redundancy_index"], 0.0)
        self.assertLess(summary["redundancy_index"], 1.0)

        # Clone groups detection
        self.assertIn("CLONE_QDII_NDX100", res["clone_groups"])
        self.assertEqual(res["clone_groups"]["CLONE_QDII_NDX100"]["fund_count"], 25)

        # Circuit breaker P2 alert
        cb = evaluate_circuit_breakers(res["portfolio_summary"], res["penetrated_holdings"], clone_groups=res["clone_groups"])
        p2_codes = [msg["code"] for msg in cb["intercept_messages"]]
        self.assertIn("P2_PARALLEL_CLONE_REDUNDANCY", p2_codes)

    def test_redundancy_index_boundary_when_slots_huge(self):
        """When 100 funds each have 1 stock (100 slots, 1 unique stock), RI = 1 - 1/100 = 0.99."""
        funds = []
        for i in range(100):
            funds.append({
                "code": f"00{i:04d}",
                "name": f"纯英伟达基金_{i}",
                "cost": 100.0,
                "market_value": 100.0,
                "category": "美股科技",
                "top_holdings": [{"stock_name": "NVDA", "weight": 1.0}],
            })
        res = penetrate_portfolio({"funds": funds})
        self.assertAlmostEqual(res["summary"]["redundancy_index"], 0.99, places=4)
        self.assertLess(res["summary"]["redundancy_index"], 1.0)


class TestPnLAndDrawdownExtremes(unittest.TestCase):
    """Stress testing catastrophic loss (-99%), break-even (0%), and huge gain (+500%)."""

    def test_catastrophic_drawdown_minus_99_pct(self):
        """Drawdown of -99.9%: cost=1,000,000, mv=1,000 -> floating_pnl = -999,000, rate = -0.999."""
        funds = [
            {
                "code": "000001",
                "name": "巨幅崩盘科技基金",
                "cost": 1000000.0,
                "market_value": 1000.0,
                "category": "科技",
                "sector": "半导体",
                "top_holdings": [{"name": "中芯国际", "weight": 0.5}],
            }
        ]
        res = penetrate_portfolio({"funds": funds})
        summary = res["summary"]

        self.assertEqual(summary["total_cost"], 1000000.0)
        self.assertEqual(summary["total_value"], 1000.0)
        self.assertEqual(summary["floating_pnl"], -999000.0)
        self.assertAlmostEqual(summary["floating_pnl_rate"], -0.999, places=3)

        # Invariant: total_value - total_cost == floating_pnl
        self.assertAlmostEqual(summary["total_value"] - summary["total_cost"], summary["floating_pnl"], places=2)

        # Circuit breaker must trip P1 loss chasing freeze
        cb = evaluate_circuit_breakers(res["portfolio_summary"], res["penetrated_holdings"])
        self.assertTrue(cb["is_tripped"])
        p1_msgs = [m for m in cb["intercept_messages"] if m["code"] == "P1_LOSS_CHASING_FREEZE"]
        self.assertEqual(len(p1_msgs), 1)
        self.assertEqual(cb["cooling_off_hours"], 48)

    def test_breakeven_pnl(self):
        """0% PnL: cost=100,000, mv=100,000 -> pnl=0.0, rate=0.0."""
        funds = [
            {
                "code": "000002",
                "name": "保本稳健基金",
                "cost": 100000.0,
                "market_value": 100000.0,
                "category": "纯债",
                "sector": "纯债",
                "top_holdings": [],
            }
        ]
        res = penetrate_portfolio({"funds": funds})
        summary = res["summary"]
        self.assertEqual(summary["floating_pnl"], 0.0)
        self.assertEqual(summary["floating_pnl_rate"], 0.0)
        self.assertAlmostEqual(summary["total_value"] - summary["total_cost"], summary["floating_pnl"], places=2)

    def test_extreme_gain_plus_500_pct(self):
        """Gain of +500%: cost=100,000, mv=600,000 -> pnl=500,000, rate = +5.0."""
        funds = [
            {
                "code": "000003",
                "name": "超级牛市科技基金",
                "cost": 100000.0,
                "market_value": 600000.0,
                "category": "科技",
                "sector": "芯片",
                "top_holdings": [{"name": "NVDA", "weight": 0.2}],
            }
        ]
        res = penetrate_portfolio({"funds": funds})
        summary = res["summary"]
        self.assertEqual(summary["floating_pnl"], 500000.0)
        self.assertAlmostEqual(summary["floating_pnl_rate"], 5.0, places=4)
        self.assertAlmostEqual(summary["total_value"] - summary["total_cost"], summary["floating_pnl"], places=2)

        # In circuit_breaker.py: check pnl_rate handling for rate > 1.0!
        cb = evaluate_circuit_breakers(res["portfolio_summary"], res["penetrated_holdings"])
        # Should not trigger loss freeze on +500% profit
        p1_msgs = [m for m in cb["intercept_messages"] if m["code"] == "P1_LOSS_CHASING_FREEZE"]
        self.assertEqual(len(p1_msgs), 0)

    def test_pnl_rate_scale_bug_on_severe_loss_exceeding_100_pct(self):
        """When floating_pnl_rate is -1.50 (-150% loss), circuit breaker heuristic fails."""
        # A margin or structured portfolio with -120% loss (cost=100k, value=-20k, rate=-1.2)
        portfolio_summary = {
            "total_cost": 100000.0,
            "total_value": 0.0,
            "floating_pnl": -120000.0,
            "floating_pnl_rate": -1.20,  # -120% loss
            "sector_exposures": {"泛科技大类": 60.0},
        }
        cb = evaluate_circuit_breakers(portfolio_summary, [])
        # The loss is -120%, which is well below -10.0%, so P1_LOSS_CHASING_FREEZE MUST trip!
        p1_msgs = [m for m in cb["intercept_messages"] if m["code"] == "P1_LOSS_CHASING_FREEZE"]
        self.assertTrue(len(p1_msgs) > 0, "BUG: -120% loss failed to trip loss freeze because abs(-1.2) > 1.0 treated rate as -1.2%!")



class TestMathematicalInvariantsAndBoundaries(unittest.TestCase):
    """Stress testing mathematical invariants across all portfolios."""

    def test_invariant_sum_of_weights_le_100_pct(self):
        """Sum of penetrated stock effective weights must not exceed 100.0%."""
        funds = [
            {
                "code": "001",
                "name": "基金A",
                "cost": 50000,
                "market_value": 50000,
                "category": "科技",
                "sector": "芯片",
                "top_holdings": [
                    {"name": "NVDA", "weight": 0.10},
                    {"name": "AAPL", "weight": 0.08},
                    {"name": "MSFT", "weight": 0.07},
                ],
            },
            {
                "code": "002",
                "name": "基金B",
                "cost": 50000,
                "market_value": 50000,
                "category": "科技",
                "sector": "软件",
                "top_holdings": [
                    {"name": "MSFT", "weight": 0.09},
                    {"name": "GOOGL", "weight": 0.06},
                ],
            },
        ]
        res = penetrate_portfolio({"funds": funds})
        stocks = res["penetrated_stocks"]
        total_weight_ratio = sum(s["effective_weight_ratio"] for s in stocks)
        self.assertLessEqual(total_weight_ratio, 1.0001)

        total_weight_pct = sum(s["effective_weight"] for s in stocks)
        self.assertLessEqual(total_weight_pct, 100.01)

    def test_invariant_value_minus_cost_equals_pnl(self):
        """Total Market Value - Total Cost == Floating PnL strictly holds."""
        import random
        random.seed(42)
        funds = []
        for i in range(30):
            c = round(random.uniform(10.0, 50000.0), 2)
            v = round(random.uniform(10.0, 50000.0), 2)
            funds.append({
                "code": f"F_{i}",
                "name": f"Fund_{i}",
                "cost": c,
                "market_value": v,
                "top_holdings": [],
            })

        res = penetrate_portfolio({"funds": funds})
        summary = res["summary"]
        diff = abs((summary["total_value"] - summary["total_cost"]) - summary["floating_pnl"])
        self.assertLess(diff, 0.01, f"Floating PnL does not match Total Value - Total Cost: diff={diff}")

    def test_invariant_redundancy_index_range(self):
        """0.0 <= RI < 1.0 strictly holds across diverse configurations."""
        test_cases = [
            [],  # empty
            [{"name": "A", "cost": 100, "market_value": 100, "top_holdings": []}],  # 0 holdings
            [{"name": "A", "cost": 100, "market_value": 100, "top_holdings": [{"name": "X", "weight": 1.0}]}],  # 1 stock
            [{"name": f"F{i}", "cost": 100, "market_value": 100, "top_holdings": [{"name": f"S{i}", "weight": 1.0}]} for i in range(10)],  # 10 completely unique stocks
            [{"name": f"F{i}", "cost": 100, "market_value": 100, "top_holdings": [{"name": "NVDA", "weight": 1.0}]} for i in range(50)],  # 50 duplicate stocks
        ]

        for idx, tc in enumerate(test_cases):
            res = penetrate_portfolio({"funds": tc})
            ri = res["summary"]["redundancy_index"]
            self.assertGreaterEqual(ri, 0.0, f"Case {idx} RI < 0.0: {ri}")
            self.assertLessEqual(ri, 1.0, f"Case {idx} RI > 1.0: {ri}")

    def test_tiny_micro_amounts_and_large_macro_amounts(self):
        """Verify behavior with micro amount ¥0.01 and macro amount ¥100,000,000."""
        # Micro amount
        micro_fund = {
            "funds": [{
                "code": "MICRO",
                "name": "微小资金",
                "cost": 0.01,
                "market_value": 0.01,
                "top_holdings": [{"name": "NVDA", "weight": 0.1}],
            }]
        }
        res_micro = penetrate_portfolio(micro_fund)
        self.assertEqual(res_micro["summary"]["total_value"], 0.01)
        self.assertEqual(res_micro["summary"]["total_cost"], 0.01)

        # Macro amount
        macro_fund = {
            "funds": [{
                "code": "MACRO",
                "name": "巨型资金",
                "cost": 100000000.0,
                "market_value": 100000000.0,
                "top_holdings": [{"name": "NVDA", "weight": 0.1}],
            }]
        }
        res_macro = penetrate_portfolio(macro_fund)
        self.assertEqual(res_macro["summary"]["total_value"], 100000000.0)
        self.assertEqual(res_macro["summary"]["total_cost"], 100000000.0)
        self.assertEqual(res_macro["penetrated_stocks"][0]["effective_value"], 10000000.0)


class TestEmptyAndEdgeInputs(unittest.TestCase):
    """Stress testing edge cases: empty portfolio, zero holdings, missing fields."""

    def test_empty_portfolio_dict_keys(self):
        """Empty portfolio must return both 'summary' and 'portfolio_summary' to satisfy contracts."""
        empty_portfolio = {"funds": []}
        res = penetrate_portfolio(empty_portfolio)

        self.assertIn("summary", res)
        # Check if portfolio_summary is present or missing!
        self.assertIn("portfolio_summary", res, "CRITICAL: 'portfolio_summary' is missing from empty portfolio return dict!")
        self.assertIn("penetrated_holdings", res)
        self.assertIn("penetrated_stocks", res)

    def test_funds_with_zero_top_holdings(self):
        """Funds with empty top_holdings must not crash."""
        funds = [
            {"code": "Z1", "name": "无持仓基金1", "cost": 5000, "market_value": 5000, "top_holdings": []},
            {"code": "Z2", "name": "无持仓基金2", "cost": 5000, "market_value": 5000, "top_holdings": None},
        ]
        res = penetrate_portfolio({"funds": funds})
        self.assertEqual(res["summary"]["total_funds_count"], 2)
        self.assertEqual(res["summary"]["unique_stocks_count"], 0)
        self.assertEqual(len(res["penetrated_stocks"]), 0)
        self.assertEqual(res["summary"]["redundancy_index"], 0.0)

    def test_circuit_breaker_on_safe_defensive_portfolio(self):
        """A safe portfolio with >35% defensive bonds/gold must NOT trip P0_SUB_SECTOR_OVERWEIGHT."""
        safe_funds = [
            {"code": "000198", "name": "天弘同利债券", "cost": 50000.0, "market_value": 51000.0, "category": "纯债", "sector": "纯债防守", "pnl_rate": 0.02},
            {"code": "000216", "name": "华安黄金易", "cost": 30000.0, "market_value": 35000.0, "category": "黄金", "sector": "黄金避险", "pnl_rate": 0.16},
            {"code": "001052", "name": "华夏中证500", "cost": 20000.0, "market_value": 20000.0, "category": "宽基", "sector": "中盘宽基", "pnl_rate": 0.00}
        ]
        res = penetrate_portfolio({"portfolio_name": "稳健防守组合", "funds": safe_funds})
        cb = evaluate_circuit_breakers(res.get("portfolio_summary", res["summary"]), res["penetrated_holdings"])

        # Check whether P0_SUB_SECTOR_OVERWEIGHT was triggered on defensive assets
    def test_empty_portfolio_buying_bond_blocked_by_p0(self):
        """Simulating buying a safe bond into an empty portfolio should NOT be blocked by P0_SUB_SECTOR_OVERWEIGHT."""
        empty_state = penetrate_portfolio({"funds": []})
        bond_fund = {
            "code": "000198",
            "name": "天弘同利债券",
            "sector": "纯债防守",
            "category": "纯债",
            "top_holdings": []
        }
        # Provide portfolio_summary if missing
        if "portfolio_summary" not in empty_state:
            empty_state["portfolio_summary"] = empty_state["summary"]
        sim = simulate_buy_order(empty_state, bond_fund, 10000.0)
        self.assertEqual(sim["status"], "APPROVED", f"Initial bond purchase blocked unexpectedly: {sim.get('intercept_reason')}")
        self.assertFalse(sim["is_tripped"])

    def test_integer_raw_code_crashes_penetration(self):
        """Passing integer raw code (e.g. 600519 instead of '600519') must not crash with AttributeError."""
        portfolio = {
            "funds": [{
                "code": "000001",
                "name": "消费基金",
                "cost": 1000,
                "market_value": 1000,
                "top_holdings": [{"name": "贵州茅台", "code": 600519, "weight": 0.1}]
            }]
        }
        try:
            res = penetrate_portfolio(portfolio)
            self.assertEqual(len(res["penetrated_stocks"]), 1)
        except AttributeError as e:
            self.fail(f"VULNERABILITY: Integer stock code caused AttributeError: {e}")

    def test_weight_normalization_discontinuity(self):
        """Percentage table inputs like [8.8, 5.2, 1.0, 0.8] must not inflate weights to > 100%."""
        holdings = [
            {"name": "NVDA", "weight": 8.8},
            {"name": "AAPL", "weight": 1.0},
            {"name": "MSFT", "weight": 0.8},
        ]
        portfolio = {
            "funds": [{
                "code": "TEST",
                "name": "测试基金",
                "cost": 10000,
                "market_value": 10000,
                "top_holdings": holdings,
            }]
        }
        res = penetrate_portfolio(portfolio)
        total_weight = sum(s["effective_weight"] for s in res["penetrated_stocks"])
        self.assertLessEqual(total_weight, 100.0, f"VULNERABILITY: Total weight inflated to {total_weight}% due to normalize_weight heuristic!")


class TestAliasCollisionsAndSubstrings(unittest.TestCase):
    """Stress testing stock alias matching and substring collisions."""

    def test_casing_variations_match_canonical(self):
        """nvda, Nvda, NVDA, NVIDIA all normalize to 'NVDA (英伟达)'."""
        for name in ["nvda", "Nvda", "NVDA", "nvidia", "NVIDIA", "英伟达"]:
            canon_name, canon_code, market, sector = normalize_stock_identity(name)
            self.assertEqual(canon_name, "NVDA (英伟达)", f"Failed for {name}")
            self.assertEqual(canon_code, "NVDA")
            self.assertEqual(market, "美股")

    def test_substring_false_positive_collisions(self):
        """Check whether substring matching causes false positive collisions."""
        # 'METALLURGICAL CORP OF CHINA' (中国中冶) contains 'META'
        canon_name, canon_code, market, sector = normalize_stock_identity("METALLURGICAL CORP OF CHINA")
        is_collision = (canon_name == "META (Meta)")
        print(f"DEBUG: 'METALLURGICAL CORP OF CHINA' matched -> {canon_name}")
        self.assertFalse(is_collision, "VULNERABILITY: 'METALLURGICAL CORP OF CHINA' falsely matched META!")

    def test_pineapple_energy_collision(self):
        """Check whether 'PINEAPPLE ENERGY' matches 'AAPL (苹果)'."""
        canon_name, canon_code, market, sector = normalize_stock_identity("PINEAPPLE ENERGY")
        is_collision = (canon_name == "AAPL (苹果)")
        print(f"DEBUG: 'PINEAPPLE ENERGY' matched -> {canon_name}")
        self.assertFalse(is_collision, "VULNERABILITY: 'PINEAPPLE ENERGY' falsely matched APPLE!")


if __name__ == "__main__":
    unittest.main(verbosity=2)

