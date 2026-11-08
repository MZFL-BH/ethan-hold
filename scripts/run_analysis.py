#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_analysis.py — ethan-hold 仓位罗盘 CLI 分析与离线看板生成总入口

Usage:
    python3 scripts/run_analysis.py --input tests/fixtures/portfolio_25_funds.json --output portfolio_dashboard.html
    python3 scripts/run_analysis.py --simulate-buy 320007,5000
    python3 scripts/run_analysis.py --json
"""

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# 动态确保当前脚本目录及 skill 根目录在 sys.path 中
CURRENT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CURRENT_DIR.parent

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from scripts.penetration import penetrate_portfolio, normalize_weight, map_macro_sector
    from scripts.circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
    from scripts.generate_dashboard import generate_dashboard_html
except ImportError:
    from penetration import penetrate_portfolio, normalize_weight, map_macro_sector
    from circuit_breaker import evaluate_circuit_breakers, simulate_buy_order
    from generate_dashboard import generate_dashboard_html


def clean_financial_number(val: Any) -> float:
    """
    清洗金融文本数值：支持货币符号（¥, $）、千分位逗号（半角与全角）、百分号、
    会计负数括号 (1,840.00) 以及带正负号数值。
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = (
        str(val)
        .strip()
        .replace("¥", "")
        .replace("$", "")
        .replace(",", "")
        .replace("，", "")
        .replace("元", "")
    )
    if s.endswith("%"):
        s = s[:-1].strip()
        try:
            return float(s) / 100.0
        except ValueError:
            return 0.0
    # 会计负数括号格式: (600.00) -> -600.00
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1].strip()
    if s.startswith("+"):
        s = s[1:].strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_portfolio_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    智能解析持仓输入文件，支持 JSON、CSV 以及 Markdown 表格格式。
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"持仓输入文件不存在: {path}")

    content = path.read_text(encoding="utf-8").strip()

    # 1. 优先尝试解析为 JSON
    if path.suffix.lower() == ".json" or content.startswith("{") or content.startswith("["):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                return data
            if isinstance(data, list):
                return {"portfolio_name": path.stem, "funds": data}
        except json.JSONDecodeError:
            pass  # 继续尝试其他格式

    # 2. Markdown 表格解析 (| 基金代码 | 基金名称 | ...)
    if "|" in content:
        lines = [line.strip() for line in content.splitlines() if line.strip().startswith("|")]
        if len(lines) >= 3:  # 包含表头、分割行、至少一行数据
            raw_headers = [c.strip() for c in lines[0].split("|")[1:-1]]
            funds = []
            for row_line in lines[2:]:
                cols = [c.strip() for c in row_line.split("|")[1:-1]]
                if not cols or all(not c for c in cols):
                    continue
                row_dict = dict(zip(raw_headers, cols))
                fund_obj = convert_dict_to_fund(row_dict)
                if fund_obj:
                    funds.append(fund_obj)
            if funds:
                return {"portfolio_name": path.stem, "funds": funds}

    # 3. CSV 格式解析
    raw_lines = [line.strip() for line in content.splitlines() if line.strip()]
    if raw_lines:
        first_line = raw_lines[0]
        # 智能判定分隔符：若首行包含中文全角逗号且数量多于半角逗号，采用中文逗号作为 delimiter
        csv_delim = "，" if ("，" in first_line and first_line.count("，") > first_line.count(",")) else ","

        csv_reader = csv.DictReader(raw_lines, delimiter=csv_delim)
        funds = []
        for row in csv_reader:
            fund_obj = convert_dict_to_fund(row)
            if fund_obj:
                funds.append(fund_obj)

        if funds:
            return {"portfolio_name": path.stem, "funds": funds}

    raise ValueError(f"无法识别输入文件的持仓数据格式: {path}")


def convert_dict_to_fund(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    将 CSV / Markdown 行字典规范化为基金标准结构。
    """
    cleaned_row = {k.strip(): v for k, v in row.items() if k}
    code = (
        cleaned_row.get("基金代码")
        or cleaned_row.get("代码")
        or cleaned_row.get("code")
        or cleaned_row.get("fund_code")
        or ""
    ).strip()
    name = (
        cleaned_row.get("基金名称")
        or cleaned_row.get("基金全称")
        or cleaned_row.get("名称")
        or cleaned_row.get("name")
        or cleaned_row.get("fund_name")
        or ""
    ).strip()

    if not code and not name:
        return None

    cost = clean_financial_number(
        cleaned_row.get("投入本金")
        or cleaned_row.get("本金")
        or cleaned_row.get("成本")
        or cleaned_row.get("cost")
        or cleaned_row.get("cost_value")
    )
    market_val = clean_financial_number(
        cleaned_row.get("当前市值")
        or cleaned_row.get("市值")
        or cleaned_row.get("价值")
        or cleaned_row.get("market_value")
        or cleaned_row.get("value")
    )
    pnl = clean_financial_number(
        cleaned_row.get("浮动盈亏")
        or cleaned_row.get("盈亏")
        or cleaned_row.get("pnl")
        or cleaned_row.get("unrealized_pnl")
    )
    pnl_rate = clean_financial_number(
        cleaned_row.get("收益率")
        or cleaned_row.get("浮亏率")
        or cleaned_row.get("盈亏率")
        or cleaned_row.get("pnl_rate")
        or cleaned_row.get("return_rate")
    )

    # 字段补全与相互推导
    if market_val == 0.0 and cost > 0.0 and pnl != 0.0:
        market_val = cost + pnl
    elif cost == 0.0 and market_val > 0.0 and pnl != 0.0:
        cost = market_val - pnl
    elif pnl == 0.0 and cost > 0.0 and market_val > 0.0:
        pnl = market_val - cost

    if pnl_rate == 0.0 and cost > 0.0:
        pnl_rate = pnl / cost

    category = (
        cleaned_row.get("资产分类")
        or cleaned_row.get("分类")
        or cleaned_row.get("category")
        or ""
    ).strip()
    sector = (
        cleaned_row.get("行业赛道")
        or cleaned_row.get("行业")
        or cleaned_row.get("sector")
        or ""
    ).strip()
    clone_group_id = cleaned_row.get("clone_group_id") or None

    return {
        "code": code,
        "name": name,
        "category": category,
        "sector": sector,
        "cost": round(cost, 2),
        "market_value": round(market_val, 2),
        "pnl": round(pnl, 2),
        "pnl_rate": round(pnl_rate, 4),
        "clone_group_id": clone_group_id,
        "top_holdings": cleaned_row.get("top_holdings") or [],
    }


def format_currency(val: float) -> str:
    """格式化人民币金额."""
    sign = "-" if val < 0 else ""
    return f"{sign}¥{abs(val):,.2f}"


def print_cli_summary(
    pen_res: Dict[str, Any],
    cb_res: Dict[str, Any],
    html_output_path: str,
    sim_res: Optional[Dict[str, Any]] = None,
) -> None:
    """
    在终端打印清晰、结构化且符合工位同事语气的高效分析摘要。
    """
    summary = pen_res["summary"]
    total_cost = summary["total_cost"]
    total_val = summary["total_value"]
    pnl = summary["floating_pnl"]
    pnl_rate_pct = summary["floating_pnl_rate"] * 100.0

    tech_exp = summary.get("sector_exposures", {}).get("泛科技大类", 0.0)
    if tech_exp == 0.0 and "泛科技大类" in pen_res.get("macro_sectors", {}):
        tech_exp = pen_res["macro_sectors"]["泛科技大类"].get("percentage", 0.0)

    print("\n" + "=" * 78)
    print("  🧭 ethan-hold (仓位罗盘) · 资产穿透与硬顶熔断诊断报告")
    print("=" * 78)

    # 1. 资产大盘
    print(f"  ● 组合总投入: {format_currency(total_cost):<14}  总当前市值: {format_currency(total_val):<14}")
    pnl_color = "🔴" if pnl < 0 else "🟢"
    print(f"  ● 累计浮动盈亏: {pnl_color} {format_currency(pnl)} ({pnl_rate_pct:+.2f}%)")
    print(f"  ● 纳入分析基金: {summary['total_funds_count']} 只  穿透底层资产: {summary['unique_stocks_count']} 项")

    # 2. 泛科技集中度与并联诊断
    tech_status = "🔴 严重击穿硬顶 (50%)" if tech_exp >= 50.0 else "🟢 正常安全"
    print(f"  ● 泛科技穿透敞口: {tech_exp:.2f}% [{tech_status}]")

    clones = pen_res.get("clone_groups", {})
    if clones:
        for g_id, g_info in clones.items():
            f_count = g_info.get("fund_count", len(g_info.get("funds", [])))
            f_mv = g_info.get("total_market_value", 0.0)
            f_pct = (f_mv / total_val * 100.0) if total_val > 0 else 0.0
            print(f"  ● 并联同质化集群: {g_id} 包含 {f_count} 只影子基金，占用 {format_currency(f_mv)} ({f_pct:.1f}%)")

    # 2.5 高占比核心重仓宏观透视 (Top Core Holdings Macro & Volatility Insights)
    funds = pen_res.get("funds", [])
    if funds and total_val > 0:
        sorted_funds = sorted(funds, key=lambda x: float(x.get("market_value", 0.0)), reverse=True)
        top_funds = [f for f in sorted_funds if (float(f.get("market_value", 0.0)) / total_val * 100.0) >= 10.0]
        if top_funds:
            print("-" * 78)
            print("  🌐 高占比核心重仓透视 (社会宏观背景 / 1~3月波动前瞻 / 实操应对建议):")
            for f in top_funds[:4]:
                f_mv = float(f.get("market_value", 0.0))
                f_pct = (f_mv / total_val) * 100.0
                f_code = f.get("code", "")
                f_name = f.get("name", "")
                f_pnl_rate = f.get("pnl_rate", 0.0)
                pnl_s = f"{f_pnl_rate*100:+.2f}%" if abs(f_pnl_rate) <= 1.0 else f"{f_pnl_rate:+.2f}%"

                print(f"  ● 【{f_name} ({f_code})】占比 {f_pct:.1f}% ({format_currency(f_mv)}, 盈亏率: {pnl_s})")
                if "金" in f_name or "001000" in f_code:
                    print("    - 🏛️ 背景: 全球央行去美元化购金长周期，降息周期实际利率走低，国内资产荒定投热。")
                    print("    - 🔮 预测: 逼近历史 95% 超买高位，防范降息预期反复引发 5%~10% 回调与多头踩踏。")
                    print("    - 💡 建议: 严禁追高；若占比超 28% 倒金字塔止盈 20% 浮盈再平衡至红利，底仓 20% 锁死。")
                elif "红利" in f_name or "001001" in f_code:
                    print("    - 🏛️ 背景: 新“国九条”重塑红利生态，强化分红与市值考核，低利率长债破 2.2% 险资刚需。")
                    print("    - 🔮 预测: 下行抗跌极佳（预期回撤 < 5%），但牛市或顺周期强刺激期面临风格轮动跑输。")
                    print("    - 💡 建议: 作为定盘星长期持有，开启分红再投资；逢市场疯炒成长、红利回调时逆势增配。")
                elif "稳进" in f_name or "001002" in f_code:
                    print("    - 🏛️ 背景: “固收+”变“固收-”行业暗雷，过度配置权益可转债发生非对称亏损；6个月锁仓陷阱。")
                    print("    - 🔮 预测: 净值修复极其缓慢，反弹仅 2%~5%，面临二次下探与长期跑输纯债基准风险。")
                    print("    - 💡 建议: 绝对硬顶冷冻，严禁追加一分钱；6 个月解锁后分批赎回，置换为真纯债彻底清洗。")
                elif "纳指" in f_name or "纳斯达克" in f_name or "科技" in f_name or "001004" in f_code:
                    print("    - 🏛️ 背景: 生成式 AI 算力军备竞赛，北美云巨头百亿 CAPEX 支撑；外汇限额外汇并联假分散。")
                    print("    - 🔮 预测: PE 处于 32~35 倍高位，财报容错低，防美债利率反弹引发 8%~15% 快速回撤。")
                    print("    - 💡 建议: 严守 50% 科技硬顶，坚决不新开第 7 只代码，待限额放开向广发纳指单只归集。")

    # 3. 熔断判定
    print("-" * 78)
    if cb_res.get("is_tripped"):
        print(f"  🚨 风控状态: {cb_res.get('max_severity')} (硬顶熔断已激活)")
        for msg in cb_res.get("intercept_messages", []):
            print(f"    - {msg.get('title', '')}")
            print(f"      原因: {msg.get('detail', '')}")
            if msg.get("action"):
                print(f"      处置: {msg.get('action')}")
        if cb_res.get("cooling_off_hours"):
            print(f"    - ⏳ 强制冷静期: 必须冷静 {cb_res['cooling_off_hours']} 小时，禁止继续追跌加仓！")
    else:
        print("  🟢 风控状态: 正常放行 (未触发任何硬顶拦截)")

    # 4. 模拟买入结果展示
    if sim_res:
        print("-" * 78)
        print("  🎯 拟加仓风控预检结果 (Pre-Trade Simulation):")
        sim_status = sim_res.get("status", "UNKNOWN")
        if sim_status == "BLOCKED":
            print(f"    - 判定: 🛑 BLOCKED (强制拦截！触发防冲动加仓硬顶熔断)")
            if sim_res.get("intercept_reason"):
                print(f"      理由: {sim_res['intercept_reason']}")
            if sim_res.get("alternative_advice"):
                print(f"      建议: {sim_res['alternative_advice']}")
        else:
            print(f"    - 判定: 🟢 APPROVED (风控放行)")
            if sim_res.get("message"):
                print(f"      说明: {sim_res['message']}")

    print("-" * 78)
    print(f"  📄 离线单文件看板已生成: {html_output_path}")
    print("=" * 78 + "\n")


def infer_fund_sector_and_category(
    target_identifier: str,
    explicit_sector: Optional[str] = None,
) -> Tuple[str, str]:
    """
    针对持仓库外拟买入标的，进行行业赛道与宏观资产分类推断：
    1. 优先使用用户在命令行显式指定的第三参数 (如: --simulate-buy 000009,10000,纯债)；
    2. 基于标的代码或名称中的关键词智能推断所属行业；
    3. 纯数字代码且无显式指定时，保守归入 '其他分散资产'，严禁武断归入 '泛科技' 造成虚假熔断拦截。
    """
    # 1. 显式指定优先
    if explicit_sector and explicit_sector.strip():
        sec = explicit_sector.strip()
        macro = map_macro_sector(sec, target_identifier, "")
        return sec, macro

    text = target_identifier.strip().lower()

    # 2. 关键词智能推断
    # 防御底线 (纯债/现金/黄金)
    if any(k in text for k in ["纯债", "债券", "债", "短债", "中短债", "国债", "固收", "现金", "货币", "理财", "保本"]):
        return "纯债防守", "防御底线 (纯债/现金/黄金)"
    if any(k in text for k in ["黄金", "黄金etf", "金", "大宗", "贵金属", "避险"]):
        return "黄金避险", "防御底线 (纯债/现金/黄金)"

    # 泛科技大类
    if any(k in text for k in [
        "科技", "半导体", "芯片", "纳指", "纳斯达克", "nasdaq", "美股科技",
        "计算机", "算力", "软件", "电子", "消费电子", "人工智能", "ai", "互联网", "通信"
    ]):
        return "泛科技", "泛科技大类"

    # 医药与大健康
    if any(k in text for k in ["医药", "医疗", "健康", "生物", "cxo", "药", "创新药"]):
        return "医疗健康", "医药与大健康"

    # 消费与白酒
    if any(k in text for k in ["白酒", "酒", "消费", "食品", "饮料", "零售", "农业"]):
        return "白酒消费", "消费与白酒"

    # 新能源与低碳
    if any(k in text for k in ["新能源", "光伏", "锂电", "电池", "低碳", "环保", "储能", "汽车"]):
        return "新能源低碳", "新能源与低碳"

    # 金融与高股息
    if any(k in text for k in ["银行", "高股息", "红利", "证券", "券商", "保险", "金融"]):
        return "银行红利", "金融与高股息"

    # 公用事业与电力
    if any(k in text for k in ["公用事业", "电力", "绿电", "核电", "电网"]):
        return "公用电力", "公用事业与电力"

    # 周期与军工安全
    if any(k in text for k in ["军工", "国防", "安全", "有色", "煤炭", "钢铁", "化工"]):
        return "国防军工", "周期与军工安全"

    # 中盘与宽基
    if any(k in text for k in ["500", "300", "1000", "50", "宽基", "指增", "沪深", "中证"]):
        return "中盘宽基", "中盘与宽基"

    # 3. 无法匹配特征的未知数字代码或标的，归入 '其他分散资产'
    return "其他分散资产", "其他分散资产"


def run_pipeline(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    simulate_buy: Optional[str] = None,
    output_json: bool = False,
    quiet: bool = False,
) -> Dict[str, Any]:
    """
    全流程执行管线：读取数据 -> 穿透计算 -> 熔断检验 -> 模拟试算 -> 看板生成。
    """
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()

    # 1. 摄取持仓数据
    raw_data = parse_portfolio_file(input_path)

    # 2. 核心穿透合并算法
    pen_res = penetrate_portfolio(raw_data)

    # 3. 评估组合现有状态的硬顶熔断
    cb_res = evaluate_circuit_breakers(
        portfolio_summary=pen_res["portfolio_summary"],
        penetrated_holdings=pen_res["penetrated_holdings"],
        clone_groups=pen_res.get("clone_groups"),
    )

    # 4. 拟加仓模拟预检 (若用户指定了 --simulate-buy)
    sim_res = None
    if simulate_buy:
        # 兼容全角中文逗号 '，' 统一映射为半角英文逗号 ','
        normalized_sim = simulate_buy.replace("，", ",")
        parts = [p.strip() for p in normalized_sim.split(",") if p.strip()]
        if len(parts) >= 2:
            target_identifier = parts[0]
            try:
                buy_amount = float(parts[1])
            except ValueError:
                print(f"⚠️ 模拟加仓金额无法解析为有效数值: '{parts[1]}'", file=sys.stderr)
                buy_amount = 0.0

            explicit_sector = parts[2] if len(parts) >= 3 else None

            # 在持仓中检索匹配基金
            target_fund = None
            for f in pen_res["funds"]:
                if f["code"] == target_identifier or f["name"] == target_identifier or target_identifier in f["name"]:
                    target_fund = f
                    break

            if not target_fund:
                inferred_sector, inferred_category = infer_fund_sector_and_category(
                    target_identifier=target_identifier,
                    explicit_sector=explicit_sector,
                )
                target_fund = {
                    "code": target_identifier,
                    "name": target_identifier,
                    "category": inferred_category,
                    "sector": inferred_sector,
                    "pnl_rate": 0.0,
                    "market_value": 0.0,
                    "cost": 0.0,
                }

            sim_res = simulate_buy_order(pen_res, target_fund, buy_amount)
        else:
            print(
                f"⚠️ 模拟加仓参数格式错误: '{simulate_buy}'，有效格式为 '代码或名称,拟买入金额[,行业赛道]' (支持中英文逗号)",
                file=sys.stderr,
            )

    # 5. 组装看板生成所需要的数据对象
    dashboard_data = {
        "portfolio_name": pen_res["summary"].get("portfolio_name", "Ethan-Hold 投资组合"),
        "portfolio_summary": pen_res["portfolio_summary"],
        "summary": pen_res["summary"],
        "penetrated_stocks": pen_res["penetrated_stocks"],
        "penetrated_holdings": pen_res["penetrated_holdings"],
        "macro_sectors": pen_res["macro_sectors"],
        "sub_sectors": pen_res["sub_sectors"],
        "clone_groups": pen_res["clone_groups"],
        "funds": pen_res["funds"],
        "fund_list": pen_res["funds"],
        "breaker_status": cb_res,
        "simulation_result": sim_res,
    }

    # 6. 生成纯原生 100% 离线单文件 HTML 看板
    generated_html_file = generate_dashboard_html(dashboard_data, str(output_path))

    # 7. 控制台输出控制
    if output_json:
        # 净化输出 JSON
        json_output = {
            "portfolio_summary": pen_res["portfolio_summary"],
            "circuit_breaker": cb_res,
            "top_10_stocks": pen_res["penetrated_stocks"][:10],
            "macro_sectors": pen_res["macro_sectors"],
            "simulation_result": sim_res,
            "generated_dashboard": generated_html_file,
        }
        print(json.dumps(json_output, ensure_ascii=False, indent=2))
    elif not quiet:
        print_cli_summary(pen_res, cb_res, generated_html_file, sim_res)

    return {
        "penetration": pen_res,
        "circuit_breaker": cb_res,
        "simulation": sim_res,
        "dashboard_path": generated_html_file,
    }


def build_cli_parser() -> argparse.ArgumentParser:
    """构建 CLI 命令行解析器."""
    parser = argparse.ArgumentParser(
        prog="ethan-hold",
        description="ethan-hold (仓位罗盘) — 个人投资组合底层持仓穿透、防冲动买入硬顶熔断与离线 HTML 看板生成器",
        epilog="遵循零外部依赖 (Zero-CDN) 原则与纯本地离线隐私计算。",
    )
    default_input = SKILL_ROOT / "tests" / "fixtures" / "portfolio_25_funds.json"
    default_output = SKILL_ROOT / "portfolio_dashboard.html"

    parser.add_argument(
        "-i", "--input",
        dest="input_file",
        default=str(default_input),
        help=f"持仓数据输入文件路径 (支持 JSON / CSV / Markdown 表格，默认: {default_input.name})",
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        default=str(default_output),
        help=f"生成的单文件离线 HTML 仪表盘输出路径 (默认: {default_output.name})",
    )
    parser.add_argument(
        "-s", "--simulate-buy",
        dest="simulate_buy",
        default=None,
        metavar="CODE,AMOUNT[,SECTOR]",
        help="加仓前测模拟试算，格式为 '基金代码或名称,拟买入金额[,行业赛道]' (例如: '320007,5000' 或 '000009,10000,纯债'，支持中英文逗号)",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="以标准 JSON 格式输出分析与风控结果到 stdout",
    )
    parser.add_argument(
        "-q", "--quiet",
        dest="quiet",
        action="store_true",
        help="静默模式，不输出终端文字摘要",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI 主程序入口点，返回整数退出码 (0 表示成功)。
    """
    parser = build_cli_parser()
    args = parser.parse_args(argv)

    try:
        run_pipeline(
            input_path=args.input_file,
            output_path=args.output_file,
            simulate_buy=args.simulate_buy,
            output_json=args.output_json,
            quiet=args.quiet,
        )
        return 0
    except Exception as e:
        print(f"❌ 运行错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
