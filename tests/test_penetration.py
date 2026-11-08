"""
Unit tests for penetration.py in ethan-hold
"""

import unittest
from scripts.penetration import (
    penetrate_portfolio,
    normalize_stock_identity,
    normalize_weight,
    map_macro_sector,
    detect_clone_groups,
)


class TestPenetrationEngine(unittest.TestCase):

    def test_empty_portfolio(self):
        """测试空持仓边界情况"""
        res = penetrate_portfolio({})
        self.assertEqual(res["summary"]["total_funds_count"], 0)
        self.assertEqual(res["summary"]["total_value"], 0.0)
        self.assertEqual(res["summary"]["floating_pnl"], 0.0)
        self.assertEqual(res["summary"]["redundancy_index"], 0.0)
        self.assertEqual(len(res["penetrated_stocks"]), 0)
        self.assertEqual(len(res["macro_sectors"]), 0)

    def test_single_fund_penetration(self):
        """测试单只基金穿透计算"""
        data = {
            "portfolio_name": "单基金测试",
            "funds": [
                {
                    "code": "000055",
                    "name": "广发纳指A",
                    "cost": 10000.0,
                    "market_value": 9000.0,
                    "category": "QDII并联纳指",
                    "sector": "海外美股科技",
                    "top_holdings": [
                        {"name": "NVDA", "weight": 0.088},
                        {"name": "AAPL", "weight": 0.082},
                    ],
                }
            ],
        }
        res = penetrate_portfolio(data)
        summary = res["summary"]
        self.assertEqual(summary["total_cost"], 10000.0)
        self.assertEqual(summary["total_value"], 9000.0)
        self.assertEqual(summary["floating_pnl"], -1000.0)
        self.assertEqual(summary["floating_pnl_rate"], -0.1)

        stocks = res["penetrated_stocks"]
        self.assertEqual(len(stocks), 2)
        # NVDA: 9000 * 0.088 = 792.0, 占比 8.8%
        nvda = next(s for s in stocks if "NVDA" in s["stock_name"])
        self.assertAlmostEqual(nvda["effective_value"], 792.0, places=2)
        self.assertAlmostEqual(nvda["effective_weight"], 8.8, places=1)
        self.assertEqual(nvda["source_funds_count"], 1)

    def test_multi_fund_overlap_and_alias_consolidation(self):
        """测试多只基金持仓穿透合并及中英文股票别名归集"""
        data = {
            "funds": [
                {
                    "code": "F1",
                    "name": "基金1",
                    "cost": 10000.0,
                    "market_value": 10000.0,
                    "category": "美股科技",
                    "sector": "海外美股科技",
                    "top_holdings": [
                        {"name": "NVDA", "weight": 0.10},  # 1000 元
                        {"name": "AAPL", "weight": 0.05},  # 500 元
                    ],
                },
                {
                    "code": "F2",
                    "name": "基金2",
                    "cost": 20000.0,
                    "market_value": 20000.0,
                    "category": "美股科技",
                    "sector": "海外美股科技",
                    "top_holdings": [
                        {"name": "英伟达", "weight": "5.0%"},  # 别名合并: 20000 * 5% = 1000 元
                        {"name": "微软", "weight": 0.06},     # 1200 元
                    ],
                },
                {
                    "code": "F3",
                    "name": "基金3",
                    "cost": 10000.0,
                    "market_value": 10000.0,
                    "category": "美股科技",
                    "sector": "海外美股科技",
                    "top_holdings": [
                        {"name": "NVDA (英伟达)", "weight": 8.0},  # 百分比数值: 10000 * 8% = 800 元
                    ],
                },
            ]
        }
        res = penetrate_portfolio(data)
        self.assertEqual(res["summary"]["total_value"], 40000.0)

        # 英伟达合计: 1000 + 1000 + 800 = 2800 元，占比 2800 / 40000 = 7.0%
        stocks = res["penetrated_stocks"]
        nvda = next(s for s in stocks if "NVDA" in s["stock_name"])
        self.assertAlmostEqual(nvda["effective_value"], 2800.0, places=2)
        self.assertAlmostEqual(nvda["effective_weight"], 7.0, places=2)
        self.assertEqual(nvda["source_funds_count"], 3)
        self.assertEqual(len(nvda["source_funds"]), 3)

    def test_parallel_qdii_feeder_funds_clustering(self):
        """测试 8 只并联 QDII 纳指基金的识别与克隆聚合"""
        funds = []
        codes = ["000055", "006479", "000834", "160213", "000043", "040046", "016055", "009880"]
        names = [
            "广发纳斯达克100ETF联接A",
            "广发纳斯达克100ETF联接C",
            "大成纳斯达克100联接A",
            "国泰纳斯达克100(QDII-LOF)",
            "嘉实美国成长股票(QDII)",
            "华安纳斯达克100ETF联接A",
            "华夏纳斯达克100ETF联接A",
            "华宝纳斯达克科技ETF联接A",
        ]
        for c, n in zip(codes, names):
            funds.append({
                "code": c,
                "name": n,
                "cost": 4000.0,
                "market_value": 3600.0,
                "category": "QDII并联纳指",
                "sector": "海外美股科技",
                "top_holdings": [
                    {"name": "NVDA", "weight": 0.088},
                    {"name": "AAPL", "weight": 0.082},
                    {"name": "MSFT", "weight": 0.078},
                ]
            })

        res = penetrate_portfolio({"funds": funds})
        summary = res["summary"]
        self.assertEqual(summary["total_funds_count"], 8)
        self.assertEqual(summary["parallel_fund_count"], 8)
        self.assertIn("CLONE_QDII_NDX100", res["clone_groups"])
        self.assertEqual(res["clone_groups"]["CLONE_QDII_NDX100"]["fund_count"], 8)
        self.assertEqual(res["clone_groups"]["CLONE_QDII_NDX100"]["total_market_value"], 8 * 3600.0)

        # 冗余指数验证: 8只基金各持有 3 个槽位 (共24个槽位)，仅有 3 只唯一个股
        # RI = 1 - 3 / 24 = 1 - 0.125 = 0.875
        self.assertAlmostEqual(summary["redundancy_index"], 0.875, places=3)

    def test_macro_sector_roll_up(self):
        """测试美股科技与 A 股半导体归并为泛科技大类"""
        data = {
            "funds": [
                {
                    "code": "000055",
                    "name": "广发纳斯达克100联接",
                    "cost": 10000.0,
                    "market_value": 10000.0,
                    "sector": "海外美股科技",
                    "category": "QDII",
                },
                {
                    "code": "320007",
                    "name": "诺安成长混合",
                    "cost": 10000.0,
                    "market_value": 10000.0,
                    "sector": "A股芯片半导体",
                    "category": "偏股混合型",
                },
                {
                    "code": "000216",
                    "name": "华安黄金易ETF联接",
                    "cost": 5000.0,
                    "market_value": 5000.0,
                    "sector": "黄金大宗避险",
                    "category": "商品",
                },
                {
                    "code": "000198",
                    "name": "天弘同利债券",
                    "cost": 5000.0,
                    "market_value": 5000.0,
                    "sector": "纯债流动性防守",
                    "category": "纯债",
                },
            ]
        }
        res = penetrate_portfolio(data)
        macro = res["macro_sectors"]
        # 总市值 30000
        # 泛科技 = 10000 + 10000 = 20000, 占比 20000 / 30000 = 66.67%
        self.assertIn("泛科技大类", macro)
        self.assertAlmostEqual(macro["泛科技大类"]["effective_value"], 20000.0, places=2)
        self.assertAlmostEqual(macro["泛科技大类"]["percentage"], 66.67, places=2)

        # 防御底线 = 5000 (黄金) + 5000 (纯债) = 10000, 占比 33.33%
        self.assertIn("防御底线 (纯债/现金/黄金)", macro)
        self.assertAlmostEqual(macro["防御底线 (纯债/现金/黄金)"]["effective_value"], 10000.0, places=2)
        self.assertAlmostEqual(macro["防御底线 (纯债/现金/黄金)"]["percentage"], 33.33, places=2)

    def test_benchmark_25_funds_full_math(self):
        """测试 25 只基金经典基准组合(-13%浮亏与65.56%科技敞口)全量数学验证"""
        funds = [
            # 8只并联纳指 (本金35000, 市值31400)
            {"code": "000055", "name": "广发纳斯达克100ETF联接A", "cost": 6000.0, "market_value": 5400.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "006479", "name": "广发纳斯达克100ETF联接C", "cost": 4000.0, "market_value": 3600.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "000834", "name": "大成纳斯达克100联接A", "cost": 5000.0, "market_value": 4550.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "160213", "name": "国泰纳斯达克100(QDII-LOF)", "cost": 5000.0, "market_value": 4450.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "000043", "name": "嘉实美国成长股票(QDII)", "cost": 4000.0, "market_value": 3520.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "040046", "name": "华安纳斯达克100ETF联接A", "cost": 5000.0, "market_value": 4500.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "016055", "name": "华夏纳斯达克100ETF联接A", "cost": 3000.0, "market_value": 2730.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            {"code": "009880", "name": "华宝纳斯达克科技ETF联接A", "cost": 3000.0, "market_value": 2650.0, "sector": "海外美股科技", "category": "QDII并联纳指", "clone_group_id": "CLONE_QDII_NDX100",
             "top_holdings": [{"name": "NVDA", "weight": 0.088}, {"name": "AAPL", "weight": 0.082}, {"name": "MSFT", "weight": 0.078}, {"name": "AMZN", "weight": 0.052}, {"name": "META", "weight": 0.048}, {"name": "GOOGL", "weight": 0.045}, {"name": "AVGO", "weight": 0.042}, {"name": "TSLA", "weight": 0.032}]},
            # 4只半导体芯片 (本金25000, 市值19790)
            {"code": "320007", "name": "诺安成长混合", "cost": 8000.0, "market_value": 6160.0, "sector": "A股芯片半导体", "category": "偏股混合型",
             "top_holdings": [{"name": "北方华创", "weight": 0.098}, {"name": "中芯国际", "weight": 0.095}, {"name": "韦尔股份", "weight": 0.082}]},
            {"code": "519674", "name": "银河创新成长混合A", "cost": 7000.0, "market_value": 5530.0, "sector": "A股芯片半导体", "category": "偏股混合型",
             "top_holdings": [{"name": "北方华创", "weight": 0.088}, {"name": "中微公司", "weight": 0.090}, {"name": "海光信息", "weight": 0.095}, {"name": "中芯国际", "weight": 0.060}]},
            {"code": "008888", "name": "华夏国证半导体芯片ETF联接A", "cost": 6000.0, "market_value": 4860.0, "sector": "A股芯片半导体", "category": "ETF联接",
             "top_holdings": [{"name": "中芯国际", "weight": 0.100}, {"name": "北方华创", "weight": 0.098}, {"name": "海光信息", "weight": 0.085}, {"name": "韦尔股份", "weight": 0.075}, {"name": "中微公司", "weight": 0.065}]},
            {"code": "011102", "name": "广发中证全指半导体联接A", "cost": 4000.0, "market_value": 3240.0, "sector": "A股芯片半导体", "category": "ETF联接",
             "top_holdings": [{"name": "中芯国际", "weight": 0.100}, {"name": "北方华创", "weight": 0.098}, {"name": "海光信息", "weight": 0.085}, {"name": "韦尔股份", "weight": 0.075}, {"name": "中微公司", "weight": 0.065}]},
            # 其他13只
            {"code": "001594", "name": "天弘中证计算机ETF联接A", "cost": 4000.0, "market_value": 3360.0, "sector": "软件与AI应用", "category": "ETF联接"},
            {"code": "012414", "name": "招商中证消费电子主题联接A", "cost": 3000.0, "market_value": 2490.0, "sector": "消费电子硬件", "category": "ETF联接"},
            {"code": "005827", "name": "易方达蓝筹精选混合", "cost": 6000.0, "market_value": 5040.0, "sector": "核心蓝筹/互联网", "category": "偏股混合型",
             "top_holdings": [{"name": "贵州茅台", "weight": 0.095}, {"name": "五粮液", "weight": 0.092}]},
            {"code": "001616", "name": "嘉实环保低碳股票", "cost": 4000.0, "market_value": 3000.0, "sector": "新能源与低碳", "category": "股票型"},
            {"code": "161725", "name": "招商中证白酒指数(LOF)A", "cost": 4000.0, "market_value": 3480.0, "sector": "食品饮料与白酒", "category": "指数型",
             "top_holdings": [{"name": "贵州茅台", "weight": 0.15}, {"name": "五粮液", "weight": 0.15}]},
            {"code": "003095", "name": "中欧医疗健康混合A", "cost": 5000.0, "market_value": 3650.0, "sector": "医疗医药CXO", "category": "偏股混合型"},
            {"code": "001180", "name": "易方达健康产业混合", "cost": 2000.0, "market_value": 1720.0, "sector": "医疗健康", "category": "偏股混合型"},
            {"code": "005669", "name": "前海开源公用事业股票", "cost": 2000.0, "market_value": 2080.0, "sector": "公用事业与电力", "category": "股票型"},
            {"code": "000216", "name": "华安黄金易ETF联接A", "cost": 3000.0, "market_value": 3840.0, "sector": "黄金大宗避险", "category": "黄金商品"},
            {"code": "001595", "name": "富国中证银行指数联接A", "cost": 2500.0, "market_value": 2900.0, "sector": "金融与银行高股息", "category": "指数型"},
            {"code": "001052", "name": "华夏中证500ETF联接A", "cost": 2000.0, "market_value": 1880.0, "sector": "中盘宽基", "category": "宽基"},
            {"code": "001875", "name": "前海开源国家安全混合", "cost": 1500.0, "market_value": 1350.0, "sector": "国防军工安全", "category": "偏股混合型"},
            {"code": "000198", "name": "天弘同利债券(LOF)A", "cost": 1000.0, "market_value": 1020.0, "sector": "纯债流动性防守", "category": "纯债"},
        ]
        res = penetrate_portfolio({"portfolio_name": "经典25只基金组合", "funds": funds})
        summary = res["summary"]

        # 1. 总量断言
        self.assertEqual(summary["total_cost"], 100000.0)
        self.assertEqual(summary["total_value"], 87000.0)
        self.assertEqual(summary["floating_pnl"], -13000.0)
        self.assertAlmostEqual(summary["floating_pnl_rate"], -0.13, places=2)
        self.assertEqual(summary["total_funds_count"], 25)

        # 2. 泛科技大类总敞口断言 (31400 + 19790 + 3360 + 2490 = 57040, 57040 / 87000 = 65.56%)
        macro = res["macro_sectors"]
        self.assertIn("泛科技大类", macro)
        self.assertAlmostEqual(macro["泛科技大类"]["effective_value"], 57040.0, places=1)
        self.assertAlmostEqual(macro["泛科技大类"]["percentage"], 65.56, places=1)

        # 3. 穿透核心个股断言
        stocks = {s["stock_name"]: s for s in res["penetrated_stocks"]}
        self.assertIn("NVDA (英伟达)", stocks)
        # NVDA穿透市值: 31400 * 0.088 = 2763.20 元 (3.18%)
        self.assertAlmostEqual(stocks["NVDA (英伟达)"]["effective_value"], 2763.2, places=1)
        self.assertAlmostEqual(stocks["NVDA (英伟达)"]["effective_weight"], 3.18, places=1)
        self.assertEqual(stocks["NVDA (英伟达)"]["source_funds_count"], 8)

        # 北方华创断言: 6160*0.098 + 5530*0.088 + 4860*0.098 + 3240*0.098 = 603.68 + 486.64 + 476.28 + 317.52 = 1884.12 元 (2.17%)
        self.assertIn("北方华创", stocks)
        self.assertAlmostEqual(stocks["北方华创"]["effective_value"], 1884.12, places=1)
        self.assertAlmostEqual(stocks["北方华创"]["effective_weight"], 2.17, places=1)
        self.assertEqual(stocks["北方华创"]["source_funds_count"], 4)

        # 4. 并联群组断言
        self.assertEqual(res["clone_groups"]["CLONE_QDII_NDX100"]["fund_count"], 8)
        self.assertEqual(res["clone_groups"]["CLONE_CN_SEMICONDUCTOR"]["fund_count"], 4)
        self.assertEqual(summary["parallel_fund_count"], 12)


if __name__ == "__main__":
    unittest.main()

