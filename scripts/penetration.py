"""
ethan-hold: 底层持仓穿透与合并算法引擎 (Penetration & Consolidation Engine)

实现多基金底层重仓股加权穿透合并、行业/宏观板块大类敞口归集、
QDII 并联限购同质化克隆识别与同质化冗余指数 (RI) 计算。
遵循 100% 本地离线计算，无任何第三方重依赖。
"""

import re
from typing import Any, Dict, List, Tuple


# 常用核心标的规范化别名字典 (支持中英文代码与全称聚合)
STOCK_ALIAS_MAP: Dict[str, Tuple[str, str, str, str]] = {
    # 格式: (canonical_name, stock_code, market, sector)
    "NVDA": ("NVDA (英伟达)", "NVDA", "美股", "芯片算力与GPU"),
    "英伟达": ("NVDA (英伟达)", "NVDA", "美股", "芯片算力与GPU"),
    "NVIDIA": ("NVDA (英伟达)", "NVDA", "美股", "芯片算力与GPU"),
    "AAPL": ("AAPL (苹果)", "AAPL", "美股", "消费电子与操作系统"),
    "苹果": ("AAPL (苹果)", "AAPL", "美股", "消费电子与操作系统"),
    "APPLE": ("AAPL (苹果)", "AAPL", "美股", "消费电子与操作系统"),
    "MSFT": ("MSFT (微软)", "MSFT", "美股", "软件与Azure云计算"),
    "微软": ("MSFT (微软)", "MSFT", "美股", "软件与Azure云计算"),
    "MICROSOFT": ("MSFT (微软)", "MSFT", "美股", "软件与Azure云计算"),
    "AMZN": ("AMZN (亚马逊)", "AMZN", "美股", "电商与AWS云计算"),
    "亚马逊": ("AMZN (亚马逊)", "AMZN", "美股", "电商与AWS云计算"),
    "AMAZON": ("AMZN (亚马逊)", "AMZN", "美股", "电商与AWS云计算"),
    "META": ("META (Meta)", "META", "美股", "社交网络与开源AI"),
    "FACEBOOK": ("META (Meta)", "META", "美股", "社交网络与开源AI"),
    "GOOGL": ("GOOGL (谷歌)", "GOOGL", "美股", "搜索与云服务"),
    "GOOG": ("GOOGL (谷歌)", "GOOGL", "美股", "搜索与云服务"),
    "谷歌": ("GOOGL (谷歌)", "GOOGL", "美股", "搜索与云服务"),
    "ALPHABET": ("GOOGL (谷歌)", "GOOGL", "美股", "搜索与云服务"),
    "AVGO": ("AVGO (博通)", "AVGO", "美股", "通信交换芯片与ASIC"),
    "博通": ("AVGO (博通)", "AVGO", "美股", "通信交换芯片与ASIC"),
    "BROADCOM": ("AVGO (博通)", "AVGO", "美股", "通信交换芯片与ASIC"),
    "TSLA": ("TSLA (特斯拉)", "TSLA", "美股", "新能源汽车与智驾AI"),
    "特斯拉": ("TSLA (特斯拉)", "TSLA", "美股", "新能源汽车与智驾AI"),
    "TESLA": ("TSLA (特斯拉)", "TSLA", "美股", "新能源汽车与智驾AI"),
    "北方华创": ("北方华创", "002371", "A股", "半导体设备龙头"),
    "中芯国际": ("中芯国际", "688981", "A股", "晶圆代工制造"),
    "海光信息": ("海光信息", "688041", "A股", "x86 CPU与DCU算力"),
    "韦尔股份": ("韦尔股份", "603501", "A股", "CIS图像传感器与模拟芯片"),
    "中微公司": ("中微公司", "688012", "A股", "刻蚀与MOCVD薄膜设备"),
    "贵州茅台": ("贵州茅台", "600519", "A股", "高端白酒"),
    "五粮液": ("五粮液", "000858", "A股", "浓香白酒"),
    "腾讯控股": ("腾讯控股", "00700", "港股", "社交与互联网科技"),
    "美团": ("美团-W", "03690", "港股", "本地生活与即时零售"),
    "快手": ("快手-W", "01024", "港股", "短视频与算法电商"),
    "阿里巴巴": ("阿里巴巴-W", "09988", "港股", "电商与阿里云计算"),
}


def normalize_stock_identity(raw_name: Any, raw_code: Any = "") -> Tuple[str, str, str, str]:
    """
    规范化底层股票的名称、代码、市场与细分赛道。
    具备对整数代码 (如 600519) 与 None 值的强健容错。
    """
    cleaned = str(raw_name if raw_name is not None else "").strip()
    code_str = str(raw_code if raw_code is not None else "").strip()
    upper_cleaned = cleaned.upper()

    # 1. 严格精确匹配 (全等名称或全等代码)
    for alias_key, (canon_name, canon_code, market, sector) in STOCK_ALIAS_MAP.items():
        if alias_key.upper() == upper_cleaned or (code_str and code_str.upper() == canon_code.upper()):
            return canon_name, canon_code or code_str, market, sector

    # 2. 实体消歧词界匹配 (避免 PINEAPPLE -> AAPL, METALLURGICAL -> META 等贪婪碰撞)
    for alias_key, (canon_name, canon_code, market, sector) in STOCK_ALIAS_MAP.items():
        if alias_key.isascii():
            if re.search(rf"\b{re.escape(alias_key.upper())}\b", upper_cleaned):
                return canon_name, canon_code or code_str, market, sector
        else:
            if alias_key in cleaned:
                return canon_name, canon_code or code_str, market, sector

    # 未在映射表中的常规处理
    market = "A股"
    if re.search(r"^[A-Z]{1,5}$", upper_cleaned) or "QDII" in upper_cleaned:
        market = "美股"
    elif re.match(r"^\d{5}$", code_str):
        market = "港股"

    code = code_str if code_str else cleaned
    return cleaned, code, market, "其他权益资产"


def normalize_weight(weight: Any, is_percentage_scale: bool = False) -> float:
    """
    将持仓权重标准化为 [0.0, 1.0] 的浮点小数。
    支持上下文标度指示 is_percentage_scale，彻底消除 [8.8, 1.0, 0.8] 阶跃失真。
    """
    if weight is None:
        return 0.0
    has_percent_sign = False
    if isinstance(weight, str):
        if "%" in weight:
            has_percent_sign = True
        weight = weight.replace("%", "").strip()
        try:
            val = float(weight)
        except ValueError:
            return 0.0
    else:
        try:
            val = float(weight)
        except (ValueError, TypeError):
            return 0.0

    # 若显式带有 %，或上下文识别为百分比表，或单个数值 > 1.0
    if has_percent_sign or is_percentage_scale or val > 1.0:
        return val / 100.0
    return max(0.0, val)


def map_macro_sector(sector: str, fund_name: str = "", category: str = "") -> str:
    """
    将细分行业或基金分类聚合映射为宏观大类板块。
    核心映射遵循：
    - 泛科技大类: 美股科技、QDII纳指、A股芯片半导体、计算机软件、消费电子、互联网
    - 医药与大健康: 医疗、医药、CXO、生物医药
    - 消费与白酒: 食品饮料、白酒、家电、零售
    - 新能源与低碳: 光伏、锂电、新能源车、环保
    - 金融与高股息: 银行、保险、证券、红利
    - 公用事业与电力: 电力、核电、绿电、公用
    - 周期与军工安全: 军工、国防、资源、化工、有色
    - 防御底线 (纯债/现金/黄金): 纯债、短债、黄金、货币、现金
    - 中盘与宽基: 沪深300、中证500、宽基
    """
    combined_text = f"{sector} {fund_name} {category}".lower()

    # 1. 防御底线 (黄金、纯债、货币) - 优先判断避免与科技/周期误触
    if any(k in combined_text for k in ["纯债", "债券", "债基", "短债", "货币", "黄金", "避险", "现金", "固收"]):
        return "防御底线 (纯债/现金/黄金)"

    # 2. 核心蓝筹与核心资产 (如易方达蓝筹精选，持有茅五等蓝筹消费与港股互联网)
    if any(k in combined_text for k in ["蓝筹", "核心资产"]):
        return "核心资产/港股互联网"

    # 3. 泛科技大类
    if any(k in combined_text for k in [
        "科技", "半导体", "芯片", "纳指", "纳斯达克", "nasdaq", "美股科技",
        "计算机", "算力", "软件", "电子", "消费电子", "人工智能", "ai", "互联网", "通信"
    ]):
        return "泛科技大类"

    # 3. 医药与大健康
    if any(k in combined_text for k in ["医药", "医疗", "健康", "生物", "cxo", "药"]):
        return "医药与大健康"

    # 4. 消费与白酒
    if any(k in combined_text for k in ["白酒", "酒", "消费", "食品", "饮料", "零售"]):
        return "消费与白酒"

    # 5. 新能源与低碳
    if any(k in combined_text for k in ["新能源", "光伏", "锂电", "电池", "低碳", "环保", "储能"]):
        return "新能源与低碳"

    # 6. 金融与高股息
    if any(k in combined_text for k in ["银行", "高股息", "红利", "证券", "保险", "金融"]):
        return "金融与高股息"

    # 7. 公用事业与电力
    if any(k in combined_text for k in ["公用事业", "电力", "绿电", "核电", "电网"]):
        return "公用事业与电力"

    # 8. 周期与军工安全
    if any(k in combined_text for k in ["军工", "国防", "安全", "有色", "煤炭", "钢铁", "化工"]):
        return "周期与军工安全"

    # 9. 中盘与宽基
    if any(k in combined_text for k in ["500", "300", "1000", "50", "宽基", "指增"]):
        return "中盘与宽基"

    return "其他分散资产"


def detect_clone_groups(funds: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    识别同质化并联基金集群（如因外汇额度限购而并联开立的多只纳指 100 联接基金）。
    返回各并联组的基金列表、占用总金额及重叠特征。
    """
    clone_groups: Dict[str, List[Dict[str, Any]]] = {}

    for fund in funds:
        name = fund.get("name", "")
        category = fund.get("category", "")
        clone_id = fund.get("clone_group_id")
        sec = fund.get("sector", "")
        group_key = None
        if clone_id:
            group_key = clone_id
        elif "纳斯达克" in name or "纳指" in name or "QDII-纳指" in category or "QDII并联纳指" in category:
            group_key = "CLONE_QDII_NDX100"
        elif "半导体" in name or "芯片" in name or "半导体" in category or "芯片" in category or "半导体" in sec or "芯片" in sec:
            group_key = "CLONE_CN_SEMICONDUCTOR"

        if group_key:
            if group_key not in clone_groups:
                clone_groups[group_key] = []
            clone_groups[group_key].append(fund)

    result_groups = {}
    for g_id, g_funds in clone_groups.items():
        if len(g_funds) >= 2:
            total_mv = sum(float(f.get("market_value", f.get("value", 0.0))) for f in g_funds)
            total_cost = sum(float(f.get("cost", f.get("cost_value", 0.0))) for f in g_funds)
            result_groups[g_id] = {
                "group_id": g_id,
                "fund_count": len(g_funds),
                "funds": [
                    {
                        "code": f.get("code", ""),
                        "name": f.get("name", ""),
                        "market_value": float(f.get("market_value", f.get("value", 0.0))),
                    }
                    for f in g_funds
                ],
                "total_market_value": round(total_mv, 2),
                "total_cost": round(total_cost, 2),
            }

    return result_groups


def penetrate_portfolio(portfolio_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    全量持仓穿透与合并核心计算函数。

    输入契约:
        portfolio_data: dict, 包含 funds (或 holdings) 列表。
        每个基金包含代码、名称、市值、成本以及底层前十大股票持仓 (top_holdings / underlying_holdings)。

    计算输出:
        - summary: 包含总成本、总市值、总浮亏、浮亏率、基金数量、独立标的数、冗余指数 RI
        - penetrated_stocks: 穿透后按穿透暴露金额/比例降序排列的底层个股列表 (Top 15+长尾)
        - macro_sectors: 宏观大类板块敞口分布 (泛科技、消费、医药、防御底线等)
        - sub_sectors: 细分行业敞口分布
        - clone_groups: 识别出的并联同质化基金集群
        - funds: 带有权重与盈亏清洗后的基金明细列表
    """
    funds_raw = portfolio_data.get("funds") or portfolio_data.get("holdings") or []

    # 边界情况：空持仓数据
    if not funds_raw:
        return {
            "summary": {
                "portfolio_name": portfolio_data.get("portfolio_name", "默认投资组合"),
                "total_cost": 0.0,
                "total_value": 0.0,
                "floating_pnl": 0.0,
                "floating_pnl_rate": 0.0,
                "total_funds_count": 0,
                "unique_stocks_count": 0,
                "total_stock_holdings_count": 0,
                "redundancy_index": 0.0,
                "parallel_fund_count": 0,
                "parallel_groups": {},
                "sector_exposures": {},
            },
            "portfolio_summary": {
                "total_cost": 0.0,
                "total_value": 0.0,
                "floating_pnl": 0.0,
                "floating_pnl_rate": 0.0,
                "sector_exposures": {},
            },
            "penetrated_stocks": [],
            "penetrated_holdings": [],
            "macro_sectors": {},
            "sub_sectors": {},
            "clone_groups": {},
            "funds": [],
        }

    # 1. 规范化并清洗各基金基础指标
    clean_funds: List[Dict[str, Any]] = []
    total_cost = 0.0
    total_value = 0.0

    for f in funds_raw:
        cost = float(f.get("cost", f.get("cost_value", 0.0)))
        mv = float(f.get("market_value", f.get("value", 0.0)))

        # 若未显式提供成本但提供了市值和浮亏
        if cost <= 0.0 and "pnl" in f:
            cost = mv - float(f.get("pnl", 0.0))
        elif cost <= 0.0 and "unrealized_pnl" in f:
            cost = mv - float(f.get("unrealized_pnl", 0.0))
        elif cost <= 0.0 and "pnl_rate" in f:
            rate = normalize_weight(f.get("pnl_rate"))
            if 1.0 + rate != 0:
                cost = mv / (1.0 + rate)

        pnl = float(f.get("pnl", f.get("unrealized_pnl", mv - cost)))
        pnl_rate = pnl / cost if cost > 0 else 0.0

        fund_info = {
            "code": str(f.get("code", "")).strip(),
            "name": str(f.get("name", "")).strip(),
            "cost": round(cost, 2),
            "market_value": round(mv, 2),
            "pnl": round(pnl, 2),
            "pnl_rate": round(pnl_rate, 4),
            "category": str(f.get("category", "")).strip(),
            "sector": str(f.get("sector", "")).strip(),
            "clone_group_id": f.get("clone_group_id"),
            "daily_limit_cny": f.get("daily_limit_cny"),
            "top_holdings": f.get("top_holdings") or f.get("underlying_holdings") or [],
        }
        clean_funds.append(fund_info)
        total_cost += cost
        total_value += mv

    # 容错处理：若外部直接传入了准确的总市值与总成本（防止浮点累计误差）
    if "total_cost" in portfolio_data and portfolio_data["total_cost"] is not None:
        total_cost = float(portfolio_data["total_cost"])
    if "total_market_value" in portfolio_data and portfolio_data["total_market_value"] is not None:
        total_value = float(portfolio_data["total_market_value"])

    total_floating_pnl = total_value - total_cost
    total_floating_pnl_rate = total_floating_pnl / total_cost if total_cost > 0 else 0.0

    # 2. 基金组合资金权重计算 w_i = V_i / V_total
    for f in clean_funds:
        f["weight_in_portfolio"] = f["market_value"] / total_value if total_value > 0 else 0.0

    # 3. 逐只基金穿透至底层资产 E_k = sum(V_i * f_i,k)
    # stock_map: canonical_name -> dict
    stock_map: Dict[str, Dict[str, Any]] = {}
    total_stock_slots = 0

    for f in clean_funds:
        f_mv = f["market_value"]
        f_code = f["code"]
        f_name = f["name"]
        holdings = f["top_holdings"] or []

        # 扫描该基金持仓列表的权重标度
        has_val_gt_one = False
        numeric_weights = []
        for h in holdings:
            raw_w = h.get("weight") or h.get("ratio")
            try:
                w_num = float(str(raw_w).replace("%", "").strip())
                numeric_weights.append(w_num)
                if w_num > 1.0:
                    has_val_gt_one = True
            except (ValueError, TypeError):
                pass
        is_pct_table = has_val_gt_one or (len(numeric_weights) >= 2 and sum(numeric_weights) > 1.05)

        for h in holdings:
            total_stock_slots += 1
            raw_name = h.get("name") or h.get("asset") or h.get("stock_name") or ""
            raw_code = h.get("code") or h.get("stock_code") or ""
            weight = normalize_weight(h.get("weight") or h.get("ratio"), is_percentage_scale=is_pct_table)

            canon_name, canon_code, market, sector = normalize_stock_identity(raw_name, raw_code)
            # 若持仓明细自带了更具体的行业或市场
            if h.get("market"):
                market = h["market"]
            if h.get("sector"):
                sector = h["sector"]

            contributed_value = f_mv * weight

            if canon_name not in stock_map:
                stock_map[canon_name] = {
                    "stock_name": canon_name,
                    "stock_code": canon_code,
                    "market": market,
                    "sector": sector,
                    "effective_value": 0.0,
                    "source_funds": [],
                    "contributing_fund_codes": set(),
                }

            entry = stock_map[canon_name]
            entry["effective_value"] += contributed_value
            if f_code not in entry["contributing_fund_codes"]:
                entry["contributing_fund_codes"].add(f_code)
                entry["source_funds"].append({
                    "fund_code": f_code,
                    "fund_name": f_name,
                    "fund_weight": round(weight * 100, 2),
                    "contributed_value": round(contributed_value, 2),
                })
            else:
                # 相同基金多次出现时合并
                for sf in entry["source_funds"]:
                    if sf["fund_code"] == f_code:
                        sf["contributed_value"] = round(sf["contributed_value"] + contributed_value, 2)
                        sf["fund_weight"] = round(sf["fund_weight"] + weight * 100, 2)

    # 4. 构建穿透个股排行列表
    penetrated_stocks: List[Dict[str, Any]] = []
    penetrated_holdings_contract: List[Dict[str, Any]] = []

    for name, data in stock_map.items():
        eff_val = round(data["effective_value"], 2)
        eff_weight_ratio = eff_val / total_value if total_value > 0 else 0.0
        eff_weight_pct = round(eff_weight_ratio * 100, 2)

        stock_item = {
            "stock_code": data["stock_code"],
            "stock_name": data["stock_name"],
            "market": data["market"],
            "sector": data["sector"],
            "effective_value": eff_val,
            "effective_weight": eff_weight_pct,  # 百分比 0-100
            "effective_weight_ratio": round(eff_weight_ratio, 6),  # 浮点 0-1
            "source_funds_count": len(data["source_funds"]),
            "source_funds": sorted(data["source_funds"], key=lambda x: x["contributed_value"], reverse=True),
        }
        penetrated_stocks.append(stock_item)

        # 契约格式适配 (PROJECT.md)
        penetrated_holdings_contract.append({
            "stock_code": data["stock_code"],
            "stock_name": data["stock_name"],
            "effective_weight": eff_weight_pct,
            "effective_value": eff_val,
            "source_funds": [sf["fund_name"] for sf in data["source_funds"]],
        })

    # 按有效市值降序排列
    penetrated_stocks.sort(key=lambda x: x["effective_value"], reverse=True)
    penetrated_holdings_contract.sort(key=lambda x: x["effective_value"], reverse=True)

    for idx, s in enumerate(penetrated_stocks, start=1):
        s["rank"] = idx

    # 5. 行业敞口与宏观大类板块归集 (Sector Roll-up)
    sub_sector_map: Dict[str, float] = {}
    macro_sector_map: Dict[str, float] = {}

    for f in clean_funds:
        f_mv = f["market_value"]
        sec = f["sector"] or f["category"] or "其他"
        sub_sector_map[sec] = sub_sector_map.get(sec, 0.0) + f_mv

        macro_name = map_macro_sector(sec, f["name"], f["category"])
        macro_sector_map[macro_name] = macro_sector_map.get(macro_name, 0.0) + f_mv

    macro_sectors: Dict[str, Dict[str, Any]] = {}
    sector_exposures_contract: Dict[str, float] = {}

    for m_name, m_val in sorted(macro_sector_map.items(), key=lambda x: x[1], reverse=True):
        pct = round((m_val / total_value * 100), 2) if total_value > 0 else 0.0
        macro_sectors[m_name] = {
            "name": m_name,
            "effective_value": round(m_val, 2),
            "percentage": pct,
        }
        sector_exposures_contract[m_name] = pct

    sub_sectors: Dict[str, Dict[str, Any]] = {}
    for s_name, s_val in sorted(sub_sector_map.items(), key=lambda x: x[1], reverse=True):
        pct = round((s_val / total_value * 100), 2) if total_value > 0 else 0.0
        sub_sectors[s_name] = {
            "name": s_name,
            "effective_value": round(s_val, 2),
            "percentage": pct,
        }

    # 6. 并联基金识别与同质化冗余指数 (Redundancy Index)
    clone_groups = detect_clone_groups(clean_funds)
    unique_stocks_count = len(stock_map)

    # 冗余指数 RI = 1 - (Unique Stocks / Total Holdings Count)
    if total_stock_slots > 0:
        redundancy_index = round(1.0 - (unique_stocks_count / total_stock_slots), 4)
    else:
        redundancy_index = 0.0
    redundancy_index = max(0.0, min(1.0, redundancy_index))

    # 并联基金总数统计
    parallel_fund_count = 0
    for cg in clone_groups.values():
        parallel_fund_count += cg.get("fund_count", 0)

    summary = {
        "portfolio_name": portfolio_data.get("portfolio_name", "默认投资组合"),
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "floating_pnl": round(total_floating_pnl, 2),
        "floating_pnl_rate": round(total_floating_pnl_rate, 4),
        "total_funds_count": len(clean_funds),
        "unique_stocks_count": unique_stocks_count,
        "total_stock_holdings_count": total_stock_slots,
        "redundancy_index": redundancy_index,
        "parallel_fund_count": parallel_fund_count,
        "parallel_groups": clone_groups,
        "sector_exposures": sector_exposures_contract,
    }

    return {
        "summary": summary,
        "portfolio_summary": {
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "floating_pnl": round(total_floating_pnl, 2),
            "floating_pnl_rate": round(total_floating_pnl_rate, 4),
            "sector_exposures": sector_exposures_contract,
        },
        "penetrated_stocks": penetrated_stocks,
        "penetrated_holdings": penetrated_holdings_contract,
        "macro_sectors": macro_sectors,
        "sub_sectors": sub_sectors,
        "clone_groups": clone_groups,
        "funds": clean_funds,
    }
