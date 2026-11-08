"""
ethan-hold: 防冲动买入硬顶熔断与风控规则引擎 (Circuit Breaker Engine)

实现 P0 阻塞级硬顶熔断、P1 逆势浮亏加仓冷冻、P2 碎片化冗余预警，
以及买入前模拟试算 (Pre-Trade Simulation)。
遵循 100% 离线计算与务实、生活化的工位同事交流语气。
"""

from typing import Any, Dict, List, Optional
import copy

# 标准风控硬顶阈值配置
DEFAULT_THRESHOLDS = {
    "macro_tech_cap": 50.0,          # 宏观泛科技大类硬顶 (50.0%)
    "sub_sector_cap": 35.0,          # 单一细分赛道硬顶 (35.0%)
    "single_stock_cap": 15.0,        # 单一底层个股硬顶 (15.0%)
    "loss_freeze_threshold": -10.0,  # 逆势追跌加仓冷冻门槛 (-10.0%)
    "defensive_floor": 8.0,          # 纯债/黄金/防守资产最低底线 (8.0%)
    "parallel_clone_warning": 5,     # 并联同质化基金数量门槛 (>= 5 只)
}

DEFENSIVE_SECTORS = {
    "防御底线 (纯债/现金/黄金)",
    "固定收益与纯债",
    "纯债防守",
    "纯债",
    "债券",
    "债基",
    "短债",
    "货币",
    "现金",
    "黄金",
    "黄金避险",
    "固收",
}


def is_defensive_sector(sec_name: str) -> bool:
    """判断是否属于防守型安全垫资产（纯债/现金/黄金等，不受35%单一权益行业硬顶限制）。"""
    if not sec_name:
        return False
    if sec_name in DEFENSIVE_SECTORS:
        return True
    s = sec_name.lower()
    return any(k in s for k in ["纯债", "债券", "债基", "短债", "货币", "黄金", "避险", "现金", "固收", "防御底线"])


def extract_pnl_rate_pct(portfolio_summary: Dict[str, Any]) -> float:
    """
    从组合汇总中稳健提取浮亏百分比 (例如 -13.0 表示 -13.0%)。
    优先基于金额进行无歧义数学推导，避免 abs(rate) <= 1.0 启发式失真。
    """
    total_cost = float(portfolio_summary.get("total_cost", 0.0))
    floating_pnl = portfolio_summary.get("floating_pnl")
    total_value = portfolio_summary.get("total_value")

    # 1. 优先基于准确成本与盈亏金额推导
    if total_cost > 0:
        if floating_pnl is not None:
            return (float(floating_pnl) / total_cost) * 100.0
        if total_value is not None:
            return ((float(total_value) - total_cost) / total_cost) * 100.0

    # 2. 字段提取与字符串容错
    raw_rate = portfolio_summary.get("floating_pnl_rate")
    if raw_rate is None:
        raw_rate = portfolio_summary.get("pnl_rate", 0.0)

    if isinstance(raw_rate, str):
        if "%" in raw_rate:
            try:
                return float(raw_rate.replace("%", "").strip())
            except ValueError:
                return 0.0

    try:
        rate_val = float(raw_rate)
    except (ValueError, TypeError):
        return 0.0

    # 3. 刻度推导：penetration 契约中 floating_pnl_rate 为标准小数比率。
    # 仅当数值绝对值 > 2.0 (如 -13.0 或 50.0) 且未带本金时，才视为已是百分比数值。
    # 对于 -1.20 (-120% 极端巨亏)，abs(-1.20) <= 2.0 正确放大为 -120.0%。
    if abs(rate_val) <= 2.0:
        return rate_val * 100.0
    return rate_val


def evaluate_circuit_breakers(
    portfolio_summary: Dict[str, Any],
    penetrated_holdings: List[Dict[str, Any]],
    proposed_order: Optional[Dict[str, Any]] = None,
    clone_groups: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    组合硬顶熔断规则校验主入口。

    参数:
        portfolio_summary: 包含 total_cost, total_value, floating_pnl, floating_pnl_rate, sector_exposures
        penetrated_holdings: 穿透后底层个股列表，每项含 stock_code, stock_name, effective_weight, effective_value
        proposed_order: 拟下单字典 (可选)
        clone_groups: 识别出的并联基金集群 (可选)
        thresholds: 自定义阈值 (可选)

    返回契约:
        {
            "is_tripped": bool,
            "max_severity": "P0_CRITICAL" | "P1_WARNING" | "P2_NOTICE" | "NORMAL",
            "intercept_messages": list[dict],
            "cooling_off_hours": int,
            "rebalance_recommendations": list[str]
        }
    """
    th = copy.deepcopy(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    total_value = float(portfolio_summary.get("total_value", 0.0))
    total_cost = float(portfolio_summary.get("total_cost", 0.0))
    pnl_rate_pct = extract_pnl_rate_pct(portfolio_summary)

    sector_exposures = portfolio_summary.get("sector_exposures") or {}

    intercept_messages: List[Dict[str, Any]] = []
    rebalance_recommendations: List[str] = []
    cooling_off_hours = 0
    max_severity = "NORMAL"

    # 若持仓为空且无拟加仓单，正常放行
    if total_value <= 0.0 and total_cost <= 0.0 and not proposed_order:
        return {
            "is_tripped": False,
            "max_severity": "NORMAL",
            "intercept_messages": [],
            "cooling_off_hours": 0,
            "rebalance_recommendations": [],
        }

    # =========================================================================
    # 规则 1: 🔴 P0 宏观泛科技大类硬顶拦截 (Macro Tech Sector Cap >= 50%)
    # =========================================================================
    tech_exposure = sector_exposures.get("泛科技大类", 0.0)
    if tech_exposure >= th["macro_tech_cap"]:
        max_severity = "P0_CRITICAL"
        excess = round(tech_exposure - th["macro_tech_cap"], 2)
        intercept_messages.append({
            "code": "P0_MACRO_TECH_OVERWEIGHT",
            "severity": "P0_CRITICAL",
            "title": "🔴 触发宏观泛科技大类硬顶熔断 (CRITICAL HARD-CAP)",
            "detail": (
                f"当前泛科技大类（美股科技+A股半导体与电子）穿透敞口已达 {tech_exposure:.2f}%，"
                f"击穿了 {th['macro_tech_cap']:.1f}% 的安全硬顶（超标 +{excess:.2f}%）。"
                f"这相当于把全家桶筹码全押在单一科技贝塔上，极易遭遇戴维斯双杀。"
            ),
            "action": "ACTION: BLOCKED（强制拦截，严禁任何形式的泛科技标的增持）",
        })
        rebalance_recommendations.append(
            f"泛科技总敞口高达 {tech_exposure:.1f}%，已进入非理性重仓区。后续有增量资金时，"
            f"严禁再向科技/半导体加仓，必须分流至纯债、固收或红利低波资产以被动稀释风险。"
        )

    # =========================================================================
    # 规则 2: 🔴 P0 细分赛道硬顶拦截 (Sub-sector Cap >= 35%)
    # =========================================================================
    for sec_name, sec_pct in sector_exposures.items():
        if sec_name == "泛科技大类" or is_defensive_sector(sec_name):
            continue
        if sec_pct >= th["sub_sector_cap"]:
            if max_severity != "P0_CRITICAL":
                max_severity = "P0_CRITICAL"
            intercept_messages.append({
                "code": "P0_SUB_SECTOR_OVERWEIGHT",
                "severity": "P0_CRITICAL",
                "title": f"🔴 细分行业【{sec_name}】击穿硬顶红线",
                "detail": (
                    f"【{sec_name}】当前占总资产比重已达 {sec_pct:.2f}%，"
                    f"超过了 {th['sub_sector_cap']:.1f}% 的单一行业持仓上限。"
                ),
                "action": f"ACTION: BLOCKED（停止向【{sec_name}】注入任何新增买入指令）",
            })

    # =========================================================================
    # 规则 3: 🔴 P0 单一底层股票硬顶拦截 (Single Stock Cap >= 15%)
    # =========================================================================
    for stock in penetrated_holdings:
        st_weight = float(stock.get("effective_weight", 0.0))
        # 兼容权重为小数的情况
        if st_weight <= 1.0 and total_value > 0 and stock.get("effective_value"):
            st_weight = (float(stock["effective_value"]) / total_value) * 100

        if st_weight >= th["single_stock_cap"]:
            if max_severity != "P0_CRITICAL":
                max_severity = "P0_CRITICAL"
            st_name = stock.get("stock_name", "未知个股")
            sources = stock.get("source_funds", [])
            source_desc = f"（由 {len(sources)} 只基金共同持有）" if sources else ""
            intercept_messages.append({
                "code": "P0_SINGLE_STOCK_OVERWEIGHT",
                "severity": "P0_CRITICAL",
                "title": f"🔴 底层个股【{st_name}】穿透占比过高",
                "detail": (
                    f"底层个股【{st_name}】穿透合并后权重达 {st_weight:.2f}% {source_desc}，"
                    f"触碰了单一股票 {th['single_stock_cap']:.1f}% 的风控红线。"
                ),
                "action": "ACTION: BLOCKED（禁止买入任何重仓该个股的基金）",
            })

    # =========================================================================
    # 规则 4: 🟠 P1 逆势浮亏加仓钝刀熔断 (Floating Loss <= -10% + 高集中度)
    # =========================================================================
    if pnl_rate_pct <= th["loss_freeze_threshold"] and tech_exposure >= 40.0:
        if max_severity not in ["P0_CRITICAL"]:
            max_severity = "P1_WARNING"
        cooling_off_hours = max(cooling_off_hours, 48)
        intercept_messages.append({
            "code": "P1_LOSS_CHASING_FREEZE",
            "severity": "P1_WARNING",
            "title": "🟠 触发逆势钝刀补仓冷却门禁 (COOL-DOWN ACTIVATED)",
            "detail": (
                f"当前组合总浮亏已达 {pnl_rate_pct:.2f}%，且高波动泛科技敞口高达 {tech_exposure:.1f}%。"
                f"在单边阴跌或行业周期下行阶段，越跌越买往往是心理沉没成本作祟，属于『拉低均价』的认知陷阱。"
            ),
            "action": f"强制激活 {cooling_off_hours} 小时冷静期倒计时。建议关闭交易页面，切忌徒手接飞刀。",
        })
        rebalance_recommendations.append(
            f"组合目前浮亏 {pnl_rate_pct:.1f}%。请强制执行 48 小时冷冻期，冷静复盘是行业基本面恶化还是纯情绪杀估值。"
        )

    # =========================================================================
    # 规则 5: 🟡 P2 碎片化并联同质冗余告警 (Parallel Clones >= 5)
    # =========================================================================
    parallel_count = 0
    if clone_groups:
        for cg in clone_groups.values():
            c_cnt = cg.get("fund_count", 0)
            if c_cnt >= th["parallel_clone_warning"]:
                parallel_count += c_cnt
                if max_severity not in ["P0_CRITICAL", "P1_WARNING"]:
                    max_severity = "P2_NOTICE"
                g_id = cg.get("group_id", "同质并联组")
                intercept_messages.append({
                    "code": "P2_PARALLEL_CLONE_REDUNDANCY",
                    "severity": "P2_NOTICE",
                    "title": f"🟡 并联影子基金冗余警示：{c_cnt} 只基金高度同质化",
                    "detail": (
                        f"检测到【{g_id}】名下开立了 {c_cnt} 只跟踪同一指数的并联基金。"
                        f"因单日外汇额度限购而开设过多影子基金，制造了『假分散』幻觉，大幅推高交易手续费与打理精力。"
                    ),
                    "action": "建议停止新开同质化代码；后续待大额限购放开时，逐步向 1~2 只费率最低的头部联接基金归集。",
                })
                rebalance_recommendations.append(
                    f"针对并联的 {c_cnt} 只同质纳指基金，建议对比管理费与托管费明细，保留规模最大、综合费率最低的 1~2 只即可。"
                )

    # =========================================================================
    # 规则 6: 🟡 防御底线资产占比预警 (Defensive Floor < 8%)
    # =========================================================================
    defensive_pct = sector_exposures.get("防御底线 (纯债/现金/黄金)", 0.0)
    if defensive_pct < th["defensive_floor"] and total_value > 0:
        intercept_messages.append({
            "code": "NOTICE_DEFENSIVE_FLOOR_BREACH",
            "severity": "P2_NOTICE",
            "title": "🟡 防守底线资产配置严重匮乏",
            "detail": (
                f"纯债/现金/避险黄金等防守底线资产占比仅为 {defensive_pct:.2f}%，"
                f"低于 {th['defensive_floor']:.1f}% 的基础安全垫要求。组合缺乏流动性缓冲屏障。"
            ),
            "action": "建议将后续定投或现金结余优先配置于中短债纯债或同业存单基金。",
        })
        rebalance_recommendations.append(
            "防御底线资产严重不足（不足 8%）。一旦权益市场剧烈震荡，组合将毫无缓冲垫，建议配置纯债以平抑波动。"
        )

    # 汇总熔断触发标志
    is_tripped = max_severity in ["P0_CRITICAL", "P1_WARNING"]

    return {
        "is_tripped": is_tripped,
        "max_severity": max_severity,
        "intercept_messages": intercept_messages,
        "cooling_off_hours": cooling_off_hours,
        "rebalance_recommendations": rebalance_recommendations,
    }


def simulate_buy_order(
    current_state: Dict[str, Any],
    proposed_fund: Dict[str, Any],
    buy_amount: float,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    加仓前 What-If 模拟试算与硬顶拦截检验。

    参数:
        current_state: 穿透计算后的组合状态 (包含 summary / portfolio_summary, penetrated_stocks / penetrated_holdings, macro_sectors, clone_groups)
        proposed_fund: 拟买入基金信息字典 (包含 code, name, sector, category, pnl_rate, top_holdings)
        buy_amount: 拟买入金额 (元)，若 <= 0 视为卖出或健康再平衡
        thresholds: 自定义阈值 (可选)

    返回:
        模拟计算结果，包含是否拦截、加仓前后敞口对比、风控裁决与建议文案。
    """
    th = copy.deepcopy(DEFAULT_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    summary = current_state.get("portfolio_summary") or current_state.get("summary") or {}
    total_value_pre = float(summary.get("total_value", 0.0))
    total_cost_pre = float(summary.get("total_cost", 0.0))
    sector_exposures_pre = copy.deepcopy(summary.get("sector_exposures") or {})

    # 若传入的是减仓 / 卖出操作 (buy_amount < 0)
    if buy_amount < 0:
        return {
            "status": "APPROVED",
            "is_tripped": False,
            "max_severity": "NORMAL",
            "action": "PASS",
            "message": "🟢 减仓/赎回操作通过：该交易会主动降低敞口，属于健康的风险再平衡动作，风控予以放行。",
            "cooling_off_hours": 0,
            "pre_simulation": {
                "total_value": total_value_pre,
                "macro_tech_pct": sector_exposures_pre.get("泛科技大类", 0.0),
            },
            "post_simulation": {
                "total_value": max(0.0, total_value_pre + buy_amount),
                "macro_tech_pct": sector_exposures_pre.get("泛科技大类", 0.0),
            },
            "rebalance_recommendations": ["卖出减仓操作有助于平抑组合波动，回笼现金可作为防御储备。"],
        }

    # 零金额加仓
    if buy_amount == 0:
        return {
            "status": "APPROVED",
            "is_tripped": False,
            "max_severity": "NORMAL",
            "action": "PASS",
            "message": "加仓金额为 0，组合敞口无变化。",
            "cooling_off_hours": 0,
            "pre_simulation": {"total_value": total_value_pre},
            "post_simulation": {"total_value": total_value_pre},
            "rebalance_recommendations": [],
        }

    # 1. 模拟买入后的总市值与总成本
    total_value_post = total_value_pre + buy_amount
    total_cost_post = total_cost_pre + buy_amount

    # 2. 判断拟买入基金所属宏观大类板块
    from .penetration import map_macro_sector, normalize_stock_identity, normalize_weight

    fund_name = proposed_fund.get("name", "拟买入基金")
    fund_code = proposed_fund.get("code", "000000")
    fund_sector = proposed_fund.get("sector") or proposed_fund.get("category") or "泛科技"
    fund_macro = map_macro_sector(fund_sector, fund_name, proposed_fund.get("category", ""))
    fund_cost = float(proposed_fund.get("cost", 0.0))
    fund_mv = float(proposed_fund.get("market_value", 0.0))
    if fund_cost > 0 and fund_mv > 0:
        fund_pnl_rate_pct = ((fund_mv - fund_cost) / fund_cost) * 100.0
    else:
        fund_pnl_rate = float(proposed_fund.get("pnl_rate", 0.0))
        fund_pnl_rate_pct = fund_pnl_rate * 100.0 if abs(fund_pnl_rate) <= 2.0 else fund_pnl_rate

    # 3. 测算模拟后的行业与宏观敞口 (全行业准确重估)
    simulated_sector_exposures: Dict[str, float] = {}
    for sec_name, sec_pct in sector_exposures_pre.items():
        sec_val = (sec_pct / 100.0) * total_value_pre
        if sec_name == fund_macro:
            sec_val += buy_amount
        simulated_sector_exposures[sec_name] = round((sec_val / total_value_post * 100), 2) if total_value_post > 0 else 0.0

    if fund_macro not in simulated_sector_exposures:
        simulated_sector_exposures[fund_macro] = round((buy_amount / total_value_post * 100), 2) if total_value_post > 0 else 0.0

    macro_pct_pre = round(sector_exposures_pre.get(fund_macro, 0.0), 2)
    macro_pct_post = simulated_sector_exposures.get(fund_macro, 0.0)

    # 4. 测算模拟后的底层重仓个股权重
    holdings_pre = current_state.get("penetrated_stocks") or current_state.get("penetrated_holdings") or []
    stock_value_map: Dict[str, float] = {}
    for st in holdings_pre:
        st_name = st.get("stock_name", "")
        st_val = float(st.get("effective_value", 0.0))
        stock_value_map[st_name] = st_val

    fund_top_holdings = proposed_fund.get("top_holdings") or proposed_fund.get("underlying_holdings") or []
    has_val_gt_one = False
    numeric_weights = []
    for th_item in fund_top_holdings:
        raw_w = th_item.get("weight") or th_item.get("ratio")
        try:
            w_num = float(str(raw_w).replace("%", "").strip())
            numeric_weights.append(w_num)
            if w_num > 1.0:
                has_val_gt_one = True
        except (ValueError, TypeError):
            pass
    is_pct_table = has_val_gt_one or (len(numeric_weights) >= 2 and sum(numeric_weights) > 1.05)

    for th_item in fund_top_holdings:
        raw_name = th_item.get("name") or th_item.get("asset") or th_item.get("stock_name") or ""
        raw_code = th_item.get("code") or th_item.get("stock_code") or ""
        canon_name, canon_code, _, _ = normalize_stock_identity(raw_name, raw_code)
        w = normalize_weight(th_item.get("weight") or th_item.get("ratio"), is_percentage_scale=is_pct_table)
        add_val = buy_amount * w
        stock_value_map[canon_name] = stock_value_map.get(canon_name, 0.0) + add_val

    simulated_penetrated_holdings = []
    for s_name, s_val in stock_value_map.items():
        s_pct = round((s_val / total_value_post * 100), 2) if total_value_post > 0 else 0.0
        simulated_penetrated_holdings.append({
            "stock_name": s_name,
            "effective_value": round(s_val, 2),
            "effective_weight": s_pct,
        })

    # 5. 执行模拟后全组合风控状态扫描
    simulated_summary = {
        "total_cost": total_cost_post,
        "total_value": total_value_post,
        "floating_pnl": total_value_post - total_cost_post,
        "floating_pnl_rate": (total_value_post - total_cost_post) / total_cost_post if total_cost_post > 0 else 0.0,
        "sector_exposures": simulated_sector_exposures,
    }

    eval_result = evaluate_circuit_breakers(
        portfolio_summary=simulated_summary,
        penetrated_holdings=simulated_penetrated_holdings,
        proposed_order={"fund": proposed_fund, "amount": buy_amount},
        clone_groups=current_state.get("clone_groups"),
        thresholds=th,
    )

    # 6. 拟加仓指令针对性拦截裁决 (Order-level Intercept Decision)
    is_intercepted = False
    intercept_reason = ""
    alternative_advice = ""
    cooling_off = 0

    # 检验 A: 拟买入标的加剧泛科技超标
    if fund_macro == "泛科技大类" and (macro_pct_pre >= th["macro_tech_cap"] or macro_pct_post >= th["macro_tech_cap"]):
        is_intercepted = True
        if fund_pnl_rate_pct <= th["loss_freeze_threshold"]:
            cooling_off = 48
            intercept_reason = (
                f"【拦截警告】：您拟加仓的【{fund_name} ({fund_code})】当前浮亏已达 {fund_pnl_rate_pct:.1f}%，"
                f"且其所属的【泛科技大类】在组合中当前敞口已达 {macro_pct_pre:.1f}%（硬顶上限 {th['macro_tech_cap']:.1f}%）。"
                f"若再加仓 ¥{buy_amount:,.2f}，科技敞口将进一步飙升至 {macro_pct_post:.1f}%。"
                f"此操作属于典型的『越跌越补、深陷泥潭』追跌冲动，风控系统予以强制硬顶熔断！"
            )
        else:
            intercept_reason = (
                f"【硬顶拦截】：拟加仓的【{fund_name}】所属【泛科技大类】加仓后敞口将达 {macro_pct_post:.1f}%，"
                f"突破了 {th['macro_tech_cap']:.1f}% 的风控上限。严禁向超标板块继续堆积风险暴露。"
            )
        alternative_advice = (
            "建议关闭交易软件进入 48 小时强制冷静期。若手头确有闲置资金需要配置，"
            "建议强制分流至【固定收益纯债】或【红利低波】标的，以稀释泛科技高风险敞口。"
        )
    # 检验 B: 拟加仓标的自身浮亏超 -10%（P1 逆势追跌防冲动冷冻，涵盖所有赛道标的与瑕疵固收+）
    elif fund_pnl_rate_pct <= th["loss_freeze_threshold"]:
        is_intercepted = True
        cooling_off = 48
        intercept_reason = (
            f"【P1 逆势追跌拦截】：拟加仓的【{fund_name} ({fund_code})】当前浮亏已达 {fund_pnl_rate_pct:.1f}%，"
            f"触碰了 {th['loss_freeze_threshold']:.1f}% 逆势补仓冷冻线。系统已启动情绪防冲动闸口，阻断非理性摊薄成本！"
        )
        alternative_advice = (
            "建议关闭交易软件进入 48 小时强制冷静期，切忌徒手接飞刀。手头若有增量资金，"
            "建议分流配置于防守型纯债或稳健红利资产以平抑波动。"
        )

    # 检验 B: 拟买入标的导致单一细分行业超标 (防守底线资产不设 35% 上限限制)
    if not is_intercepted and fund_macro != "泛科技大类" and not is_defensive_sector(fund_macro):
        if simulated_sector_exposures.get(fund_macro, 0.0) >= th["sub_sector_cap"]:
            is_intercepted = True
            intercept_reason = (
                f"【细分赛道拦截】：买入后【{fund_macro}】板块占比将达 {simulated_sector_exposures[fund_macro]:.1f}%，"
                f"突破了单一赛道 {th['sub_sector_cap']:.1f}% 的硬顶上限。"
            )

    # 检验 C: 拟买入标的导致其底层某只个股超标
    if not is_intercepted and fund_top_holdings:
        for st in simulated_penetrated_holdings:
            if st["effective_weight"] >= th["single_stock_cap"]:
                # 检查该超标个股是否来自拟加仓基金
                is_st_in_proposed = any(
                    normalize_stock_identity(h.get("name") or h.get("asset") or "")[0] == st["stock_name"]
                    for h in fund_top_holdings
                )
                if is_st_in_proposed:
                    is_intercepted = True
                    intercept_reason = (
                        f"【单股穿透拦截】：买入后底层个股【{st['stock_name']}】穿透权重将达 {st['effective_weight']:.1f}%，"
                        f"突破了单一股票 {th['single_stock_cap']:.1f}% 的风控红线。"
                    )
                    break

    # 7. 构建最终模拟结论与文案
    if is_intercepted:
        status = "BLOCKED"
        action = "BLOCKED"
        cooling_off_final = max(cooling_off, 48 if "冷静期" in intercept_reason else 0)
        message = intercept_reason
    else:
        status = "APPROVED"
        action = "PASS"
        cooling_off_final = 0
        tech_pre = sector_exposures_pre.get("泛科技大类", 0.0)
        tech_post = simulated_sector_exposures.get("泛科技大类", 0.0)
        if tech_pre >= th["macro_tech_cap"] and fund_macro != "泛科技大类":
            message = (
                f"🟢 资产再平衡放行：本次买入【{fund_name}】注入非科技/防守资产，"
                f"有效将泛科技大类敞口从 {tech_pre:.1f}% 稀释降至 {tech_post:.1f}%，符合风控分流建议。"
            )
        else:
            message = f"🟢 预检放行：拟加仓【{fund_name}】¥{buy_amount:,.2f} 未触碰任何风控硬顶，准予执行。"

    return {
        "status": status,
        "is_tripped": is_intercepted or eval_result["is_tripped"],
        "max_severity": "P0_CRITICAL" if is_intercepted else eval_result["max_severity"],
        "action": action,
        "message": message,
        "intercept_reason": intercept_reason,
        "alternative_advice": alternative_advice,
        "cooling_off_hours": cooling_off_final,
        "intercept_messages": eval_result["intercept_messages"],
        "rebalance_recommendations": eval_result["rebalance_recommendations"],
        "pre_simulation": {
            "total_value": total_value_pre,
            "macro_exposure_pct": macro_pct_pre,
            "macro_sector_name": fund_macro,
        },
        "post_simulation": {
            "total_value": total_value_post,
            "macro_exposure_pct": macro_pct_post,
            "macro_sector_name": fund_macro,
        },
    }
