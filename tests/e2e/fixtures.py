"""
fixtures.py — Standard Test Fixtures, Oracles, and Helper Utilities for ethan-hold E2E Test Suite.
Authoritative source: ORIGINAL_REQUEST.md, PROJECT.md, and algo_survey.md.
"""

import json
import math
import os
import sys
from pathlib import Path

# Paths
SKILL_ROOT = Path("/Users/wangbinghao/.gemini/config/skills/ethan-hold")
SCRIPTS_DIR = SKILL_ROOT / "scripts"
TEMPLATES_DIR = SKILL_ROOT / "templates"
REFERENCES_DIR = SKILL_ROOT / "references"
DOCS_DIR = SKILL_ROOT / "docs"
E2E_DIR = SKILL_ROOT / "tests" / "e2e"

# Standard 25-fund portfolio benchmark data
BENCHMARK_25_FUNDS = [
    # 8 QDII Parallel Nasdaq-100 funds
    {"code": "000055", "name": "广发纳斯达克100ETF联接A", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 6000.0, "market_value": 5400.0, "pnl": -600.0, "pnl_rate": -0.10, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "006479", "name": "广发纳斯达克100ETF联接C", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 4000.0, "market_value": 3600.0, "pnl": -400.0, "pnl_rate": -0.10, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "000834", "name": "大成纳斯达克100联接A", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 5000.0, "market_value": 4550.0, "pnl": -450.0, "pnl_rate": -0.09, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "160213", "name": "国泰纳斯达克100(QDII-LOF)", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 5000.0, "market_value": 4450.0, "pnl": -550.0, "pnl_rate": -0.11, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "000043", "name": "嘉实美国成长股票(QDII)", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 4000.0, "market_value": 3520.0, "pnl": -480.0, "pnl_rate": -0.12, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "040046", "name": "华安纳斯达克100ETF联接A", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 5000.0, "market_value": 4500.0, "pnl": -500.0, "pnl_rate": -0.10, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "016055", "name": "华夏纳斯达克100ETF联接A", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 3000.0, "market_value": 2730.0, "pnl": -270.0, "pnl_rate": -0.09, "clone_group_id": "CLONE_QDII_NDX100"},
    {"code": "009880", "name": "华宝纳斯达克科技ETF联接A", "category": "QDII并联纳指", "sector": "海外美股科技", "cost": 3000.0, "market_value": 2650.0, "pnl": -350.0, "pnl_rate": -0.1167, "clone_group_id": "CLONE_QDII_NDX100"},
    
    # 4 A-Share Semiconductor funds
    {"code": "320007", "name": "诺安成长混合", "category": "A股半导体重仓", "sector": "A股半导体与芯片", "cost": 8000.0, "market_value": 6160.0, "pnl": -1840.0, "pnl_rate": -0.23, "clone_group_id": None},
    {"code": "519674", "name": "银河创新成长混合A", "category": "A股半导体重仓", "sector": "A股半导体与芯片", "cost": 7000.0, "market_value": 5530.0, "pnl": -1470.0, "pnl_rate": -0.21, "clone_group_id": None},
    {"code": "008888", "name": "华夏国证半导体芯片ETF联接A", "category": "A股半导体指数", "sector": "A股半导体与芯片", "cost": 6000.0, "market_value": 4860.0, "pnl": -1140.0, "pnl_rate": -0.19, "clone_group_id": None},
    {"code": "011102", "name": "广发中证全指半导体联接A", "category": "A股半导体指数", "sector": "A股半导体与芯片", "cost": 4000.0, "market_value": 3240.0, "pnl": -760.0, "pnl_rate": -0.19, "clone_group_id": None},
    
    # Other funds (Tech, Consumption, Healthcare, Commodities, Financials, Bonds)
    {"code": "001594", "name": "天弘中证计算机ETF联接A", "category": "软件与AI应用", "sector": "计算机与软件", "cost": 4000.0, "market_value": 3360.0, "pnl": -640.0, "pnl_rate": -0.16, "clone_group_id": None},
    {"code": "012414", "name": "招商中证消费电子主题联接A", "category": "消费电子硬件", "sector": "消费电子与硬件", "cost": 3000.0, "market_value": 2490.0, "pnl": -510.0, "pnl_rate": -0.17, "clone_group_id": None},
    {"code": "005827", "name": "易方达蓝筹精选混合", "category": "核心蓝筹/互联网", "sector": "核心蓝筹", "cost": 6000.0, "market_value": 5040.0, "pnl": -960.0, "pnl_rate": -0.16, "clone_group_id": None},
    {"code": "001616", "name": "嘉实环保低碳股票", "category": "新能源光伏锂电", "sector": "新能源低碳", "cost": 4000.0, "market_value": 3000.0, "pnl": -1000.0, "pnl_rate": -0.25, "clone_group_id": None},
    {"code": "161725", "name": "招商中证白酒指数(LOF)A", "category": "白酒大消费", "sector": "白酒消费", "cost": 4000.0, "market_value": 3480.0, "pnl": -520.0, "pnl_rate": -0.13, "clone_group_id": None},
    {"code": "003095", "name": "中欧医疗健康混合A", "category": "医疗医药CXO", "sector": "医疗健康", "cost": 5000.0, "market_value": 3650.0, "pnl": -1350.0, "pnl_rate": -0.27, "clone_group_id": None},
    {"code": "001180", "name": "易方达健康产业混合", "category": "医疗健康", "sector": "医疗健康", "cost": 2000.0, "market_value": 1720.0, "pnl": -280.0, "pnl_rate": -0.14, "clone_group_id": None},
    {"code": "005669", "name": "前海开源公用事业股票", "category": "电力与核电绿电", "sector": "公用电力", "cost": 2000.0, "market_value": 2080.0, "pnl": 80.0, "pnl_rate": 0.04, "clone_group_id": None},
    {"code": "000216", "name": "华安黄金易ETF联接A", "category": "黄金大宗避险", "sector": "黄金避险", "cost": 3000.0, "market_value": 3840.0, "pnl": 840.0, "pnl_rate": 0.28, "clone_group_id": None},
    {"code": "001595", "name": "富国中证银行指数联接A", "category": "银行高股息", "sector": "银行红利", "cost": 2500.0, "market_value": 2900.0, "pnl": 400.0, "pnl_rate": 0.16, "clone_group_id": None},
    {"code": "001052", "name": "华夏中证500ETF联接A", "category": "中盘宽基", "sector": "中盘宽基", "cost": 2000.0, "market_value": 1880.0, "pnl": -120.0, "pnl_rate": -0.06, "clone_group_id": None},
    {"code": "001875", "name": "前海开源国家安全混合", "category": "国防军工装备", "sector": "国防军工", "cost": 1500.0, "market_value": 1350.0, "pnl": -150.0, "pnl_rate": -0.10, "clone_group_id": None},
    {"code": "000198", "name": "天弘同利债券(LOF)A", "category": "纯债流动性防守", "sector": "纯债防守", "cost": 1000.0, "market_value": 1020.0, "pnl": 20.0, "pnl_rate": 0.02, "clone_group_id": None}
]

# Top 15 Penetrated Holdings Oracle
TOP_15_PENETRATED_ORACLE = [
    {"rank": 1, "name": "NVDA", "full_name": "英伟达", "market": "美股", "sector": "AI算力芯片与GPU", "value": 2763.20, "weight_pct": 3.18, "sources_count": 8},
    {"rank": 2, "name": "AAPL", "full_name": "苹果", "market": "美股", "sector": "消费电子与iOS生态", "value": 2574.80, "weight_pct": 2.96, "sources_count": 8},
    {"rank": 3, "name": "MSFT", "full_name": "微软", "market": "美股", "sector": "软件与Azure云计算", "value": 2449.20, "weight_pct": 2.82, "sources_count": 8},
    {"rank": 4, "name": "北方华创", "full_name": "北方华创", "market": "A股", "sector": "半导体前道核心设备", "value": 1884.10, "weight_pct": 2.17, "sources_count": 4},
    {"rank": 5, "name": "中芯国际", "full_name": "中芯国际", "market": "A股", "sector": "晶圆代工制造龙头", "value": 1727.00, "weight_pct": 1.99, "sources_count": 4},
    {"rank": 6, "name": "AMZN", "full_name": "亚马逊", "market": "美股", "sector": "电商与AWS云计算", "value": 1632.80, "weight_pct": 1.88, "sources_count": 8},
    {"rank": 7, "name": "META", "full_name": "Meta", "market": "美股", "sector": "社交媒体与开源AI", "value": 1507.20, "weight_pct": 1.73, "sources_count": 8},
    {"rank": 8, "name": "GOOGL", "full_name": "谷歌", "market": "美股", "sector": "搜索与Google Cloud", "value": 1413.00, "weight_pct": 1.62, "sources_count": 8},
    {"rank": 9, "name": "AVGO", "full_name": "博通", "market": "美股", "sector": "交换芯片与网络ASIC", "value": 1318.80, "weight_pct": 1.52, "sources_count": 8},
    {"rank": 10, "name": "海光信息", "full_name": "海光信息", "market": "A股", "sector": "x86 CPU与DCU加速芯片", "value": 1213.90, "weight_pct": 1.40, "sources_count": 3},
    {"rank": 11, "name": "韦尔股份", "full_name": "韦尔股份", "market": "A股", "sector": "CIS图像传感与模拟芯片", "value": 1112.60, "weight_pct": 1.28, "sources_count": 3},
    {"rank": 12, "name": "中微公司", "full_name": "中微公司", "market": "A股", "sector": "等离子刻蚀设备", "value": 1024.20, "weight_pct": 1.18, "sources_count": 3},
    {"rank": 13, "name": "TSLA", "full_name": "特斯拉", "market": "美股", "sector": "新能源汽车与智驾AI", "value": 1004.80, "weight_pct": 1.15, "sources_count": 8},
    {"rank": 14, "name": "贵州茅台", "full_name": "贵州茅台", "market": "A股", "sector": "高端白酒龙头", "value": 1000.80, "weight_pct": 1.15, "sources_count": 2},
    {"rank": 15, "name": "五粮液", "full_name": "五粮液", "market": "A股", "sector": "浓香白酒龙头", "value": 985.70, "weight_pct": 1.13, "sources_count": 2}
]

# Mathematical Oracles & Formulas
def calculate_portfolio_totals(funds: list[dict]) -> dict:
    total_cost = sum(f["cost"] for f in funds)
    total_val = sum(f["market_value"] for f in funds)
    total_pnl = total_val - total_cost
    pnl_rate = total_pnl / total_cost if total_cost > 0 else 0.0
    
    # Tech sectors
    tech_sectors = {"海外美股科技", "A股半导体与芯片", "计算机与软件", "消费电子与硬件"}
    tech_val = sum(f["market_value"] for f in funds if f["sector"] in tech_sectors)
    tech_ratio = tech_val / total_val if total_val > 0 else 0.0
    
    return {
        "total_cost": total_cost,
        "total_market_value": total_val,
        "total_pnl": total_pnl,
        "total_pnl_rate": pnl_rate,
        "tech_market_value": tech_val,
        "tech_ratio": tech_ratio
    }

def detect_parallel_clones(funds: list[dict]) -> list[dict]:
    """Group parallel clone funds (e.g. 8 QDII Nasdaq-100 funds)."""
    groups = {}
    for f in funds:
        gid = f.get("clone_group_id")
        if gid:
            groups.setdefault(gid, []).append(f)
    return [{"group_id": k, "funds": v, "count": len(v)} for k, v in groups.items()]

def evaluate_risk_rules(portfolio_summary: dict, proposed_order: dict | None = None) -> dict:
    """
    Standard Hard-Cap Circuit Breaker Evaluation Oracle:
    L1: Single Stock >= 5.0%
    L2: Sub Sector >= 30.0%
    L3: Macro Tech >= 50.0%
    L4: Defensive Floor < 8.0% (Warning if < 15.0%)
    Loss-chasing buy: Target PnL <= -10.0% and Macro Tech >= 50.0%
    """
    macro_tech_pct = portfolio_summary.get("tech_ratio", 0.0)
    total_val = portfolio_summary.get("total_market_value", 0.0)
    
    is_tripped = False
    max_severity = "NORMAL"
    messages = []
    
    # Check Macro Tech Cap
    if macro_tech_pct >= 0.50:
        is_tripped = True
        max_severity = "P0_CRITICAL"
        messages.append({
            "code": "P0_MACRO_TECH_OVERWEIGHT",
            "title": "泛科技大类持仓击穿 50% 安全硬顶",
            "detail": f"当前泛科技总敞口已达 {macro_tech_pct * 100:.2f}%，严重超过 50.0% 风控硬顶。",
            "action": "全面停止加仓泛科技标的，优先配置低波纯债资产"
        })
    elif macro_tech_pct >= 0.40:
        max_severity = "P1_WARNING"
        messages.append({
            "code": "P1_MACRO_TECH_WARNING",
            "title": "泛科技大类持仓进入预警区间",
            "detail": f"当前泛科技敞口 {macro_tech_pct * 100:.2f}% 已超过 40.0% 警戒线。",
            "action": "限制高风险新增敞口"
        })
        
    # Pre-trade order simulation if provided
    if proposed_order:
        fund_code = proposed_order.get("code")
        buy_amount = proposed_order.get("amount", 0.0)
        target_pnl = proposed_order.get("target_pnl_rate", 0.0)
        order_sector = proposed_order.get("sector", "")
        
        # Simulated new value
        new_val = total_val + buy_amount
        tech_sectors = {"海外美股科技", "A股半导体与芯片", "计算机与软件", "消费电子与硬件"}
        is_tech = order_sector in tech_sectors or fund_code in ["320007", "519674", "000055", "008888", "011102"]
        
        curr_tech_val = portfolio_summary.get("tech_market_value", 0.0)
        new_tech_val = curr_tech_val + (buy_amount if is_tech else 0.0)
        new_tech_pct = new_tech_val / new_val if new_val > 0 else 0.0
        
        # Check Loss-chasing buy intercept
        if buy_amount > 0 and target_pnl <= -0.10 and (macro_tech_pct >= 0.50 or new_tech_pct >= 0.50):
            is_tripped = True
            max_severity = "P0_CRITICAL"
            messages.append({
                "code": "P0_LOSS_CHASING_INTERCEPT",
                "title": "交易拦截：触发防冲动加仓硬顶熔断",
                "detail": f"拟加仓标的浮亏达 {target_pnl*100:.1f}%，且科技敞口已达 {macro_tech_pct*100:.1f}%，再加仓将升至 {new_tech_pct*100:.1f}%。",
                "action": "强制执行 48 小时冷静期，建议分流至固定收益纯债"
            })
        elif buy_amount < 0: # Redemption
            messages.append({
                "code": "NORMAL_HEALTHY_REBALANCE",
                "title": "健康再平衡操作",
                "detail": "减仓超额风险资产，有助于组合风险敞口回归健康水平。",
                "action": "批准减仓"
            })
            
    return {
        "is_tripped": is_tripped,
        "max_severity": max_severity,
        "intercept_messages": messages,
        "cooling_off_hours": 48 if is_tripped else 0,
        "rebalance_recommendations": [
            "停止追加美股纳指联接与A股半导体",
            "建议将资金配置于纯债或同业存单基金",
            "48小时内不得进行冲动买入操作"
        ] if is_tripped else []
    }

# Helper to format CSV
def get_benchmark_csv_content() -> str:
    lines = ["基金代码,基金名称,资产分类,行业赛道,投入本金,当前市值,浮动盈亏,收益率"]
    for f in BENCHMARK_25_FUNDS:
        lines.append(f"{f['code']},{f['name']},{f['category']},{f['sector']},{f['cost']:.2f},{f['market_value']:.2f},{f['pnl']:.2f},{f['pnl_rate']*100:.2f}%")
    return "\n".join(lines)

# Helper to format Markdown Table
def get_benchmark_markdown_content() -> str:
    lines = [
        "| 基金代码 | 基金名称 | 资产分类 | 行业赛道 | 投入本金 | 当前市值 | 浮动盈亏 | 收益率 |",
        "| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |"
    ]
    for f in BENCHMARK_25_FUNDS:
        lines.append(f"| {f['code']} | {f['name']} | {f['category']} | {f['sector']} | {f['cost']:.2f} | {f['market_value']:.2f} | {f['pnl']:.2f} | {f['pnl_rate']*100:.2f}% |")
    return "\n".join(lines)

# Helper for dirty financial strings
def get_dirty_financial_csv_content() -> str:
    return """基金代码,基金名称,投入本金,当前市值,浮动盈亏
000055,"广发纳斯达克100ETF联接A","¥6,000.00","¥5,400.00","(600.00)"
320007,"诺安成长混合","8,000.00","6,160.00","-1,840.00"
000216,"华安黄金易ETF联接A","3,000.00","3,840.00","+840.00"
000198,"天弘同利债券(LOF)A","1,000.00","1,020.00","20.00"
"""
