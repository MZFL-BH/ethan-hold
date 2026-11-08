"""
Unit tests for circuit_breaker.py in ethan-hold
"""

import unittest
from pathlib import Path
from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order


class TestCircuitBreakerEngine(unittest.TestCase):

    def test_normal_healthy_portfolio(self):
        """测试健康均衡组合放行 (NORMAL)"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 105000.0,
            "floating_pnl": 5000.0,
            "floating_pnl_rate": 0.05,
            "sector_exposures": {
                "泛科技大类": 25.0,
                "消费与白酒": 20.0,
                "医药与大健康": 20.0,
                "防御底线 (纯债/现金/黄金)": 20.0,
                "金融与高股息": 15.0,
            },
        }
        holdings = [
            {"stock_name": "AAPL (苹果)", "effective_weight": 4.5, "effective_value": 4725.0},
            {"stock_name": "贵州茅台", "effective_weight": 4.0, "effective_value": 4200.0},
        ]
        result = evaluate_circuit_breakers(summary, holdings)
        self.assertFalse(result["is_tripped"])
        self.assertEqual(result["max_severity"], "NORMAL")
        self.assertEqual(result["cooling_off_hours"], 0)
        self.assertEqual(len(result["intercept_messages"]), 0)

    def test_p0_macro_tech_overweight_intercept(self):
        """测试泛科技大类 >= 50% 触发 P0 阻塞级硬顶熔断"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 87000.0,
            "floating_pnl": -13000.0,
            "floating_pnl_rate": -0.13,
            "sector_exposures": {
                "泛科技大类": 65.56,
                "医药与大健康": 15.0,
                "防御底线 (纯债/现金/黄金)": 10.0,
            },
        }
        holdings = [
            {"stock_name": "NVDA (英伟达)", "effective_weight": 3.18, "effective_value": 2763.2},
        ]
        result = evaluate_circuit_breakers(summary, holdings)
        self.assertTrue(result["is_tripped"])
        self.assertEqual(result["max_severity"], "P0_CRITICAL")
        codes = [m["code"] for m in result["intercept_messages"]]
        self.assertIn("P0_MACRO_TECH_OVERWEIGHT", codes)

    def test_p0_single_stock_overweight_intercept(self):
        """测试单一底层股票 >= 15% 触发 P0 阻塞级硬顶熔断"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 100000.0,
            "floating_pnl": 0.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {
                "泛科技大类": 30.0,
                "防御底线 (纯债/现金/黄金)": 20.0,
            },
        }
        holdings = [
            {"stock_name": "NVDA (英伟达)", "effective_weight": 18.5, "effective_value": 18500.0},
        ]
        result = evaluate_circuit_breakers(summary, holdings)
        self.assertTrue(result["is_tripped"])
        self.assertEqual(result["max_severity"], "P0_CRITICAL")
        codes = [m["code"] for m in result["intercept_messages"]]
        self.assertIn("P0_SINGLE_STOCK_OVERWEIGHT", codes)

    def test_p1_loss_chasing_freeze_and_cooling_off(self):
        """测试浮亏 <= -10% 且科技集中度 >= 40% 触发 P1 48小时情绪冷静期"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 85000.0,
            "floating_pnl": -15000.0,
            "floating_pnl_rate": -0.15,
            "sector_exposures": {
                "泛科技大类": 45.0,  # 未触碰 50% 硬顶，但已超 40%
                "医药与大健康": 25.0,
                "防御底线 (纯债/现金/黄金)": 15.0,
            },
        }
        holdings = [
            {"stock_name": "AAPL (苹果)", "effective_weight": 4.0, "effective_value": 3400.0},
        ]
        result = evaluate_circuit_breakers(summary, holdings)
        self.assertTrue(result["is_tripped"])
        self.assertEqual(result["max_severity"], "P1_WARNING")
        self.assertEqual(result["cooling_off_hours"], 48)
        codes = [m["code"] for m in result["intercept_messages"]]
        self.assertIn("P1_LOSS_CHASING_FREEZE", codes)

    def test_p2_parallel_clone_redundancy_notice(self):
        """测试并联同质化基金 >= 5 只触发 P2 归并预警"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 100000.0,
            "floating_pnl": 0.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {
                "泛科技大类": 35.0,
                "防御底线 (纯债/现金/黄金)": 20.0,
            },
        }
        clones = {
            "CLONE_QDII_NDX100": {
                "group_id": "CLONE_QDII_NDX100",
                "fund_count": 8,
                "total_market_value": 31400.0,
            }
        }
        result = evaluate_circuit_breakers(summary, [], clone_groups=clones)
        self.assertEqual(result["max_severity"], "P2_NOTICE")
        codes = [m["code"] for m in result["intercept_messages"]]
        self.assertIn("P2_PARALLEL_CLONE_REDUNDANCY", codes)

    def test_defensive_floor_warning(self):
        """测试纯债/黄金防御底线 < 8% 触发安全垫匮乏提示"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 100000.0,
            "floating_pnl": 0.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {
                "泛科技大类": 30.0,
                "消费与白酒": 30.0,
                "防御底线 (纯债/现金/黄金)": 3.0,  # 严重不足 8%
            },
        }
        result = evaluate_circuit_breakers(summary, [])
        codes = [m["code"] for m in result["intercept_messages"]]
        self.assertIn("NOTICE_DEFENSIVE_FLOOR_BREACH", codes)

    def test_pre_trade_simulation_blocks_impulse_tech_buy(self):
        """测试加仓模拟器：在科技已超标且浮亏时阻断加仓并激活 48h 冷静期"""
        current_state = {
            "summary": {
                "total_cost": 100000.0,
                "total_value": 87000.0,
                "floating_pnl": -13000.0,
                "floating_pnl_rate": -0.13,
                "sector_exposures": {
                    "泛科技大类": 65.56,
                    "防御底线 (纯债/现金/黄金)": 8.0,
                },
            },
            "penetrated_stocks": [
                {"stock_name": "北方华创", "effective_value": 1884.1, "effective_weight": 2.17},
            ],
        }
        # 拟买入重度套牢的半导体基金 (浮亏 -23%)
        proposed_fund = {
            "code": "320007",
            "name": "诺安成长混合",
            "sector": "A股芯片半导体",
            "category": "偏股混合型",
            "pnl_rate": -0.23,
            "top_holdings": [
                {"name": "北方华创", "weight": 0.098},
            ],
        }
        res = simulate_buy_order(current_state, proposed_fund, buy_amount=5000.0)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["action"], "BLOCKED")
        self.assertTrue(res["is_tripped"])
        self.assertEqual(res["max_severity"], "P0_CRITICAL")
        self.assertEqual(res["cooling_off_hours"], 48)
        self.assertTrue(res["post_simulation"]["macro_exposure_pct"] > 65.56)
        self.assertIn("越跌越补", res["intercept_reason"])

    def test_pre_trade_simulation_allows_defensive_bond_buy(self):
        """测试加仓模拟器：向纯债等防守资产配置予以放行"""
        current_state = {
            "summary": {
                "total_cost": 100000.0,
                "total_value": 87000.0,
                "floating_pnl": -13000.0,
                "floating_pnl_rate": -0.13,
                "sector_exposures": {
                    "泛科技大类": 65.56,
                    "防御底线 (纯债/现金/黄金)": 5.0,
                },
            },
            "penetrated_stocks": [],
        }
        bond_fund = {
            "code": "000198",
            "name": "天弘同利纯债",
            "sector": "纯债流动性防守",
            "category": "纯债",
            "pnl_rate": 0.02,
            "top_holdings": [],
        }
        res = simulate_buy_order(current_state, bond_fund, buy_amount=20000.0)
        # 买入纯债稀释泛科技，且纯债本身不属于泛科技
        self.assertEqual(res["status"], "APPROVED")
        self.assertEqual(res["action"], "PASS")

    def test_pre_trade_simulation_allows_sell_or_rebalancing(self):
        """测试加仓模拟器：卖出/减仓操作 (buy_amount < 0) 视为健康再平衡放行"""
        current_state = {
            "summary": {
                "total_cost": 100000.0,
                "total_value": 87000.0,
                "floating_pnl": -13000.0,
                "floating_pnl_rate": -0.13,
                "sector_exposures": {"泛科技大类": 65.56},
            },
            "penetrated_stocks": [],
        }
        tech_fund = {
            "code": "320007",
            "name": "诺安成长混合",
            "sector": "A股芯片半导体",
        }
        res = simulate_buy_order(current_state, tech_fund, buy_amount=-3000.0)
        self.assertEqual(res["status"], "APPROVED")
        self.assertEqual(res["action"], "PASS")
        self.assertFalse(res["is_tripped"])
        self.assertIn("健康", res["message"])

    def test_p0_sub_sector_overweight_intercept(self):
        """测试单一细分赛道 >= 35% 触发 P0 阻塞级熔断"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 100000.0,
            "floating_pnl": 0.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {
                "白酒消费": 38.0,  # 细分赛道超标 35%
                "防御底线 (纯债/现金/黄金)": 20.0,
            },
        }
        res = evaluate_circuit_breakers(summary, [])
        self.assertTrue(res["is_tripped"])
        self.assertEqual(res["max_severity"], "P0_CRITICAL")
        codes = [m["code"] for m in res["intercept_messages"]]
        self.assertIn("P0_SUB_SECTOR_OVERWEIGHT", codes)

    def test_pre_trade_simulation_blocks_single_stock_breach(self):
        """测试加仓模拟器：当买入导致某单只个股穿透权重 >= 15% 时拦截"""
        current_state = {
            "summary": {
                "total_cost": 50000.0,
                "total_value": 50000.0,
                "floating_pnl": 0.0,
                "floating_pnl_rate": 0.0,
                "sector_exposures": {"消费与白酒": 20.0},
            },
            "penetrated_stocks": [
                {"stock_name": "贵州茅台", "effective_value": 6000.0, "effective_weight": 12.0},
            ],
        }
        liquor_fund = {
            "code": "161725",
            "name": "招商白酒指数",
            "sector": "白酒大消费",
            "category": "消费",
            "pnl_rate": 0.0,
            "top_holdings": [
                {"name": "贵州茅台", "weight": 0.50},  # 拟买入中茅台权重高达 50%
            ],
        }
        # 加仓 10,000 元，其中茅台增加 5,000 元。
        # 加仓后总市值 = 60,000 元，茅台总市值 = 11,000 元，占比 11000 / 60000 = 18.33% (>= 15%)
        res = simulate_buy_order(current_state, liquor_fund, buy_amount=10000.0)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["action"], "BLOCKED")
        self.assertIn("单股穿透拦截", res["intercept_reason"])

    def test_custom_thresholds_support(self):
        """测试支持自定义更严苛的风控硬顶阈值"""
        summary = {
            "total_cost": 100000.0,
            "total_value": 100000.0,
            "floating_pnl": 0.0,
            "floating_pnl_rate": 0.0,
            "sector_exposures": {
                "泛科技大类": 32.0,
                "防御底线 (纯债/现金/黄金)": 20.0,
            },
        }
        # 默认宏观科技硬顶 50%，此时 32% 不触发
        res_default = evaluate_circuit_breakers(summary, [])
        self.assertFalse(res_default["is_tripped"])

        # 自定义更严苛硬顶: 30% 熔断
        res_strict = evaluate_circuit_breakers(summary, [], thresholds={"macro_tech_cap": 30.0})
        self.assertTrue(res_strict["is_tripped"])
        self.assertEqual(res_strict["max_severity"], "P0_CRITICAL")

    def test_p1_loss_chasing_freeze_when_macro_tech_under_cap(self):
        """测试在泛科技总敞口未超 50% 硬顶时，拟买入浮亏超 -10% 的科技标的仍被 P1 追跌熔断拦截"""
        current_state = {
            "summary": {
                "total_cost": 22000.0,
                "total_value": 20000.0,
                "floating_pnl": -2000.0,
                "floating_pnl_rate": -0.0909,
                "sector_exposures": {
                    "泛科技大类": 33.47,  # 低于 50% 宏观硬顶
                    "防御底线 (纯债/现金/黄金)": 40.66,
                },
            },
            "penetrated_stocks": [],
        }
        # 拟买入浮亏 -36.57% 的东方人工智能
        ai_fund = {
            "code": "001019",
            "name": "东方人工智能主题混合C",
            "sector": "人工智能/AI应用",
            "category": "人工智能",
            "cost": 254.0,
            "market_value": 161.09,
            "pnl_rate": -0.3657,
        }
        res = simulate_buy_order(current_state, ai_fund, buy_amount=1000.0)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["action"], "BLOCKED")
        self.assertTrue(res["is_tripped"])
        self.assertEqual(res["cooling_off_hours"], 48)
        self.assertIn("逆势追跌拦截", res["intercept_reason"])
        self.assertIn("-36.6%", res["intercept_reason"])

    def test_pre_trade_simulation_on_real_ethan_portfolio(self):
        """测试在 Ethan 真实持仓（26 只基金）下模拟加仓的裁决准确性"""
        from scripts.run_analysis import parse_portfolio_file
        from scripts.penetration import penetrate_portfolio
        
        real_json_path = Path(__file__).resolve().parent.parent / "portfolio_ethan_real.json"
        data = parse_portfolio_file(real_json_path)
        pen_res = penetrate_portfolio(data)

        # 1. 加仓深度浮亏的华夏全球科技先锋 (-39.79%) -> 拦截并激活 48h 冷静期
        f_hx = next(f for f in pen_res["funds"] if f["code"] == "001008")
        res_hx = simulate_buy_order(pen_res, f_hx, 1000.0)
        self.assertEqual(res_hx["status"], "BLOCKED")
        self.assertEqual(res_hx["cooling_off_hours"], 48)

        # 2. 加仓未大幅浮亏的广发纳指 (-0.05%) -> 放行
        f_gf = next(f for f in pen_res["funds"] if f["code"] == "001004")
        res_gf = simulate_buy_order(pen_res, f_gf, 1000.0)
        self.assertEqual(res_gf["status"], "APPROVED")
        self.assertEqual(res_gf["action"], "PASS")

        # 3. 加仓建信上海金 (防守资产) -> 放行并稀释泛科技
        f_gold = next(f for f in pen_res["funds"] if f["code"] == "001000")
        res_gold = simulate_buy_order(pen_res, f_gold, 2000.0)
        self.assertEqual(res_gold["status"], "APPROVED")
        self.assertEqual(res_gold["action"], "PASS")
        self.assertIn("预检放行", res_gold["message"])

        # 4. 加仓深度浮亏的瑕疵固收+ 融通稳信增益 (-15.43%) -> 拦截并激活 48h 冷静期
        f_ct = next(f for f in pen_res["funds"] if f["code"] == "012525")
        res_ct = simulate_buy_order(pen_res, f_ct, 2000.0)
        self.assertEqual(res_ct["status"], "BLOCKED")
        self.assertEqual(res_ct["action"], "BLOCKED")
        self.assertEqual(res_ct["cooling_off_hours"], 48)
        self.assertIn("P1 逆势追跌拦截", res_ct["intercept_reason"])
        self.assertIn("-14.9%", res_ct["intercept_reason"])

        # 5. 加仓深度浮亏的新能源板块 银华中证光伏产业 (-14.78%) -> 拦截并激活 48h 冷静期
        f_pv = next(f for f in pen_res["funds"] if f["code"] == "001009")
        res_pv = simulate_buy_order(pen_res, f_pv, 1000.0)
        self.assertEqual(res_pv["status"], "BLOCKED")
        self.assertEqual(res_pv["cooling_off_hours"], 48)
        self.assertIn("P1 逆势追跌拦截", res_pv["intercept_reason"])

        # 6. 加仓重度套牢的财通成长优选 (-52.00%) -> 拦截并激活 48h 冷静期
        f_growth = next(f for f in pen_res["funds"] if f["code"] == "001022")
        res_growth = simulate_buy_order(pen_res, f_growth, 1000.0)
        self.assertEqual(res_growth["status"], "BLOCKED")
        self.assertEqual(res_growth["cooling_off_hours"], 48)
        self.assertIn("-52.0%", res_growth["intercept_reason"])


if __name__ == "__main__":
    unittest.main()
