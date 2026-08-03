"""
风控保护模块
在执行交易前进行多项风控检查，防止异常操作和过度交易。

风控规则：
1. 最大持仓数限制（默认 5 笔）
2. 最大总手数限制（默认 2.0 手）
3. 单笔最大手数限制（默认 1.0 手）
4. 单笔最小手数限制（默认 0.01 手）
5. 日亏损限制（默认余额的 5%）
6. 保证金比例检查（默认不低于 200%）
7. 价格异常检查（报价为 0 或负数时拒绝）
8. 止损止盈合理性检查（方向与价格关系）
"""

import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TZ_UTC8 = timezone(timedelta(hours=8))

# ── 风控参数（可外部调整）──
RISK_GUARD_CONFIG = {
    "max_positions": 5,          # 最大同时持仓数
    "max_total_volume": 2.0,     # 最大总手数
    "max_single_volume": 1.0,    # 单笔最大手数
    "min_single_volume": 0.01,   # 单笔最小手数
    "max_daily_loss_pct": 5.0,   # 日亏损上限（余额百分比）
    "min_margin_level": 200.0,   # 最低保证金比例（%）
    "max_spread": 5.0,           # 最大点差（$），超过则拒绝交易
}


def check_trade_risk(
    direction: str,
    volume: float,
    bid: float,
    ask: float,
    account_info: dict | None = None,
    positions: list[dict] | None = None,
    daily_loss: float = 0.0,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    symbol: str = "XAUUSD",
    config: dict | None = None,
) -> dict:
    """交易前风控检查。

    Args:
        direction: "buy" 或 "sell"。
        volume: 下单手数。
        bid: 当前买价。
        ask: 当前卖价。
        account_info: 账户信息 dict（None 则自动获取）。
        positions: 当前持仓列表（None 则自动获取）。
        daily_loss: 今日已实现亏损（USD）。
        stop_loss: 止损价。
        take_profit: 止盈价。
        symbol: 交易品种。
        config: 自定义风控参数（None 用默认）。

    Returns:
        {
            "passed": bool,          # 是否通过风控
            "rejected_reason": str,  # 未通过时的原因（通过时为空）
            "warnings": list[str],   # 警告信息（不阻止交易但需注意）
            "checks": list[dict],    # 逐项检查明细
        }
    """
    cfg = config or RISK_GUARD_CONFIG
    warnings = []
    checks = []

    # ── 延迟导入避免循环依赖 ──
    if account_info is None:
        from src.trading.executor import get_account_info
        account_info = get_account_info()
    if positions is None:
        from src.trading.executor import get_positions
        positions = get_positions(symbol)

    entry_price = ask if direction == "buy" else bid

    # ── 检查 1：价格有效性 ──
    price_valid = bid > 0 and ask > 0 and ask >= bid
    checks.append({
        "name": "价格有效性",
        "passed": price_valid,
        "detail": f"bid={bid}, ask={ask}" if not price_valid else "正常",
    })
    if not price_valid:
        return _result(False, "报价异常（bid/ask 为 0 或倒挂）", warnings, checks)

    # ── 检查 2：点差检查 ──
    spread = round(ask - bid, 2)
    spread_ok = spread <= cfg["max_spread"]
    checks.append({
        "name": "点差检查",
        "passed": spread_ok,
        "detail": f"点差=${spread}（上限${cfg['max_spread']}）",
    })
    if not spread_ok:
        return _result(False, f"点差过大：${spread} > ${cfg['max_spread']}，可能滑点严重", warnings, checks)

    # ── 检查 3：单笔手数范围 ──
    vol_ok = cfg["min_single_volume"] <= volume <= cfg["max_single_volume"]
    checks.append({
        "name": "单笔手数",
        "passed": vol_ok,
        "detail": f"{volume}手（范围 {cfg['min_single_volume']}~{cfg['max_single_volume']}）",
    })
    if not vol_ok:
        if volume < cfg["min_single_volume"]:
            return _result(False, f"手数 {volume} 低于最小限制 {cfg['min_single_volume']}", warnings, checks)
        return _result(False, f"手数 {volume} 超过单笔上限 {cfg['max_single_volume']}", warnings, checks)

    # ── 检查 4：MT5 连接 / 账户 ──
    if "error" in account_info:
        checks.append({"name": "账户状态", "passed": False, "detail": "无法获取账户信息"})
        return _result(False, "无法获取账户信息，MT5 可能未连接", warnings, checks)

    balance = account_info.get("balance", 0)
    equity = account_info.get("equity", 0)
    margin = account_info.get("margin", 0)
    free_margin = account_info.get("free_margin", 0)
    margin_level = (equity / margin * 100) if margin > 0 else 9999.0

    checks.append({
        "name": "账户状态",
        "passed": True,
        "detail": f"余额=${balance:.2f}, 净值=${equity:.2f}",
    })

    # ── 检查 5：保证金比例 ──
    if margin > 0:
        ml_ok = margin_level >= cfg["min_margin_level"]
        checks.append({
            "name": "保证金比例",
            "passed": ml_ok,
            "detail": f"{margin_level:.1f}%（下限 {cfg['min_margin_level']}%）",
        })
        if not ml_ok:
            return _result(False, f"保证金比例 {margin_level:.1f}% 低于下限 {cfg['min_margin_level']}%", warnings, checks)

    # ── 检查 6：最大持仓数 ──
    pos_count = len(positions) if positions else 0
    pos_ok = pos_count < cfg["max_positions"]
    checks.append({
        "name": "持仓数限制",
        "passed": pos_ok,
        "detail": f"当前 {pos_count} 笔（上限 {cfg['max_positions']}）",
    })
    if not pos_ok:
        return _result(False, f"持仓数 {pos_count} 已达上限 {cfg['max_positions']}", warnings, checks)

    # ── 检查 7：最大总手数 ──
    current_total_vol = sum(p.get("volume", 0) for p in (positions or []))
    new_total = current_total_vol + volume
    vol_total_ok = new_total <= cfg["max_total_volume"]
    checks.append({
        "name": "总手数限制",
        "passed": vol_total_ok,
        "detail": f"当前 {current_total_vol:.2f} + 新增 {volume:.2f} = {new_total:.2f}手（上限 {cfg['max_total_volume']}）",
    })
    if not vol_total_ok:
        return _result(False, f"总手数 {new_total:.2f} 超过上限 {cfg['max_total_volume']}", warnings, checks)

    # ── 检查 8：日亏损限制 ──
    if daily_loss > 0:
        max_daily_loss = balance * cfg["max_daily_loss_pct"] / 100
        loss_ok = daily_loss < max_daily_loss
        checks.append({
            "name": "日亏损限制",
            "passed": loss_ok,
            "detail": f"今日亏损 ${daily_loss:.2f}（上限 ${max_daily_loss:.2f} = 余额的{cfg['max_daily_loss_pct']}%）",
        })
        if not loss_ok:
            return _result(False, f"今日亏损 ${daily_loss:.2f} 超过上限 ${max_daily_loss:.2f}，停止交易", warnings, checks)
    else:
        checks.append({"name": "日亏损限制", "passed": True, "detail": "今日无亏损"})

    # ── 检查 9：止损止盈合理性 ──
    if stop_loss is not None and stop_loss > 0:
        if direction == "buy":
            sl_ok = stop_loss < entry_price
            checks.append({
                "name": "止损合理性",
                "passed": sl_ok,
                "detail": f"买入止损 {stop_loss} 应 < 入场价 {entry_price}",
            })
            if not sl_ok:
                return _result(False, f"买入方向止损 {stop_loss} 应低于入场价 {entry_price}", warnings, checks)
        else:
            sl_ok = stop_loss > entry_price
            checks.append({
                "name": "止损合理性",
                "passed": sl_ok,
                "detail": f"卖出止损 {stop_loss} 应 > 入场价 {entry_price}",
            })
            if not sl_ok:
                return _result(False, f"卖出方向止损 {stop_loss} 应高于入场价 {entry_price}", warnings, checks)

    if take_profit is not None and take_profit > 0:
        if direction == "buy":
            tp_ok = take_profit > entry_price
            checks.append({
                "name": "止盈合理性",
                "passed": tp_ok,
                "detail": f"买入止盈 {take_profit} 应 > 入场价 {entry_price}",
            })
            if not tp_ok:
                return _result(False, f"买入方向止盈 {take_profit} 应高于入场价 {entry_price}", warnings, checks)
        else:
            tp_ok = take_profit < entry_price
            checks.append({
                "name": "止盈合理性",
                "passed": tp_ok,
                "detail": f"卖出止盈 {take_profit} 应 < 入场价 {entry_price}",
            })
            if not tp_ok:
                return _result(False, f"卖出方向止盈 {take_profit} 应低于入场价 {entry_price}", warnings, checks)

    # ── 警告（不阻止交易）──
    floating = account_info.get("profit", 0)
    if floating < 0:
        warnings.append(f"当前浮动亏损 ${floating:.2f}，注意风险")
    if free_margin < balance * 0.3:
        warnings.append(f"可用保证金 ${free_margin:.2f} 不足余额的30%")

    return _result(True, "", warnings, checks)


def get_risk_status() -> dict:
    """获取当前风控状态摘要（用于界面展示）。

    Returns:
        {
            "max_positions": int,
            "current_positions": int,
            "max_total_volume": float,
            "current_total_volume": float,
            "max_single_volume": float,
            "min_margin_level": float,
            "current_margin_level": float or None,
            "max_daily_loss_pct": float,
            "daily_loss": float,
            "status": "正常" / "警告" / "危险",
        }
    """
    from src.trading.executor import get_account_info, get_positions
    from src.trading.logger import get_trade_stats

    cfg = RISK_GUARD_CONFIG
    account = get_account_info()
    positions = get_positions()

    balance = account.get("balance", 0) if "error" not in account else 0
    equity = account.get("equity", 0) if "error" not in account else 0
    margin = account.get("margin", 0) if "error" not in account else 0
    margin_level = (equity / margin * 100) if margin > 0 else None

    current_vol = sum(p.get("volume", 0) for p in (positions or []))

    # 从交易日志统计今日亏损
    stats = get_trade_stats()
    daily_loss = abs(min(0, stats.get("total_profit", 0)))

    # 状态判定
    status = "正常"
    if len(positions or []) >= cfg["max_positions"]:
        status = "危险"
    elif margin_level is not None and margin_level < cfg["min_margin_level"]:
        status = "危险"
    elif current_vol >= cfg["max_total_volume"] * 0.8:
        status = "警告"
    elif daily_loss > balance * cfg["max_daily_loss_pct"] / 100 * 0.5:
        status = "警告"

    return {
        "max_positions": cfg["max_positions"],
        "current_positions": len(positions or []),
        "max_total_volume": cfg["max_total_volume"],
        "current_total_volume": round(current_vol, 2),
        "max_single_volume": cfg["max_single_volume"],
        "min_margin_level": cfg["min_margin_level"],
        "current_margin_level": round(margin_level, 1) if margin_level else None,
        "max_daily_loss_pct": cfg["max_daily_loss_pct"],
        "daily_loss": round(daily_loss, 2),
        "status": status,
    }


def _result(passed: bool, reason: str, warnings: list, checks: list) -> dict:
    """构造返回结果。"""
    return {
        "passed": passed,
        "rejected_reason": reason,
        "warnings": warnings,
        "checks": checks,
    }


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  风控保护模块 - 自测")
    print("=" * 55)

    # 测试 1：正常情况
    print("\n[1] 正常交易检查")
    print("-" * 40)
    result = check_trade_risk(
        direction="buy",
        volume=0.01,
        bid=4029.50,
        ask=4029.75,
        account_info={
            "balance": 100000, "equity": 100050, "margin": 500,
            "free_margin": 99550, "profit": 50, "leverage": 100,
        },
        positions=[],
        daily_loss=0,
        stop_loss=4000,
        take_profit=4100,
    )
    print(f"  通过: {result['passed']}")
    for c in result["checks"]:
        icon = "✅" if c["passed"] else "❌"
        print(f"  {icon} {c['name']}: {c['detail']}")
    if result["warnings"]:
        for w in result["warnings"]:
            print(f"  ⚠️  {w}")

    # 测试 2：止损方向错误
    print("\n[2] 止损方向错误（买入止损 > 入场价）")
    print("-" * 40)
    result2 = check_trade_risk(
        direction="buy",
        volume=0.01,
        bid=4029.50,
        ask=4029.75,
        account_info={
            "balance": 100000, "equity": 100050, "margin": 500,
            "free_margin": 99550, "profit": 50, "leverage": 100,
        },
        positions=[],
        stop_loss=4100,  # 买入止损应该在入场价下方
        take_profit=4000,
    )
    print(f"  通过: {result2['passed']}")
    print(f"  拒绝原因: {result2['rejected_reason']}")

    # 测试 3：持仓数超限
    print("\n[3] 持仓数超限")
    print("-" * 40)
    mock_positions = [{"volume": 0.01} for _ in range(5)]
    result3 = check_trade_risk(
        direction="buy",
        volume=0.01,
        bid=4029.50,
        ask=4029.75,
        account_info={
            "balance": 100000, "equity": 100050, "margin": 500,
            "free_margin": 99550, "profit": 50, "leverage": 100,
        },
        positions=mock_positions,
    )
    print(f"  通过: {result3['passed']}")
    print(f"  拒绝原因: {result3['rejected_reason']}")

    # 测试 4：手数超限
    print("\n[4] 单笔手数超限")
    print("-" * 40)
    result4 = check_trade_risk(
        direction="sell",
        volume=5.0,
        bid=4029.50,
        ask=4029.75,
        account_info={
            "balance": 100000, "equity": 100050, "margin": 500,
            "free_margin": 99550, "profit": 50, "leverage": 100,
        },
        positions=[],
    )
    print(f"  通过: {result4['passed']}")
    print(f"  拒绝原因: {result4['rejected_reason']}")

    print("\n" + "=" * 55)
    print("  自测完成")
    print("=" * 55)
