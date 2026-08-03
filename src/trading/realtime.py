"""
实时数据模块
实时报价获取、价格序列缓存、持仓实时监控、账户摘要、交易信号展示。
"""

import sys
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import CONFIG
from src.trading.executor import get_account_info, get_positions, calculate_volume

TZ_UTC8 = timezone(timedelta(hours=8))

# MT5 配置
MT5_LOGIN = int(CONFIG.get("MT5_LOGIN", 0))
MT5_PASSWORD = CONFIG["MT5_PASSWORD"]
MT5_SERVER = CONFIG["MT5_SERVER"]

# ── 模块级缓存 ──
_last_price: dict[str, float] = {}   # {symbol: last_bid}
_price_buffer: list[dict] = []         # [{time, symbol, bid, ask}]
_MAX_BUFFER = 3600  # 最多保留 3600 条


# ============================================================
# 连接管理
# ============================================================

def _connect() -> bool:
    """连接并登录 MT5。"""
    if not mt5.initialize():
        err = mt5.last_error()
        print(f"[实时] MT5 初始化失败: {err}")
        return False
    if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"[实时] MT5 登录失败: {mt5.last_error()}")
        mt5.shutdown()
        return False
    return True


def _disconnect():
    """断开 MT5。"""
    mt5.shutdown()


# ============================================================
# 实时报价
# ============================================================

def get_tick_price(symbol: str = "XAUUSD") -> dict:
    """获取实时报价（单次查询，自动缓存到价格序列）。

    Args:
        symbol: 交易品种，默认 "XAUUSD"。

    Returns:
        dict: {"symbol", "bid", "ask", "spread", "time", "change"}
    """
    global _last_price, _price_buffer

    if not _connect():
        return {
            "symbol": symbol, "bid": 0, "ask": 0, "spread": 0,
            "time": datetime.now(TZ_UTC8).isoformat(), "change": 0,
        }

    try:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"[实时] 无法获取 '{symbol}' 报价")
            return {
                "symbol": symbol, "bid": 0, "ask": 0, "spread": 0,
                "time": datetime.now(TZ_UTC8).isoformat(), "change": 0,
            }

        bid = tick.bid
        ask = tick.ask
        spread = round(ask - bid, 2)
        now = datetime.now(TZ_UTC8)

        # 计算涨跌幅
        last = _last_price.get(symbol)
        change = round((bid - last) / last * 100, 4) if last and last > 0 else 0
        _last_price[symbol] = bid

        # 追加到价格序列缓存
        _price_buffer.append({
            "time": now,
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
        })
        # 裁剪缓存
        if len(_price_buffer) > _MAX_BUFFER:
            _price_buffer = _price_buffer[-_MAX_BUFFER:]

        result = {
            "symbol": symbol,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "time": now.isoformat(),
            "change": change,
        }

        return result

    except Exception as e:
        print(f"[实时] ❌ 获取报价异常: {e}")
        return {
            "symbol": symbol, "bid": 0, "ask": 0, "spread": 0,
            "time": datetime.now(TZ_UTC8).isoformat(), "change": 0,
        }
    finally:
        _disconnect()


# ============================================================
# 价格序列
# ============================================================

def get_price_history(symbol: str = "XAUUSD", seconds: int = 60) -> list[dict]:
    """获取最近 N 秒的价格序列（用于实时价格曲线）。

    Args:
        symbol: 交易品种。
        seconds: 回看秒数。

    Returns:
        list[dict]: 价格序列。
    """
    now = datetime.now(TZ_UTC8)
    cutoff = now - timedelta(seconds=seconds)

    result = [
        p for p in _price_buffer
        if p["symbol"] == symbol and p["time"] >= cutoff
    ]

    if len(result) < 2:
        get_tick_price(symbol)
        result = [
            p for p in _price_buffer
            if p["symbol"] == symbol and p["time"] >= cutoff
        ]

    return result


# ============================================================
# 实时持仓监控
# ============================================================

def get_positions_realtime(symbol: str = "XAUUSD") -> list[dict]:
    """获取实时持仓状态（含实时盈亏、持仓时长、状态标签）。

    Args:
        symbol: 交易品种。

    Returns:
        list[dict]: 持仓列表（增强版）。
    """
    positions = get_positions(symbol=symbol)
    if not positions:
        return []

    now = datetime.now(TZ_UTC8)

    for p in positions:
        direction = 1 if p.get("type") == "buy" else -1
        price_diff = p.get("price_current", 0) - p.get("price_open", 0)
        p["profit_pips"] = round(price_diff * direction * 10, 1)

        try:
            open_time = datetime.strptime(p.get("time", ""), "%Y-%m-%d %H:%M:%S")
            open_time = open_time.replace(tzinfo=TZ_UTC8)
        except (ValueError, TypeError):
            open_time = now
        delta = now - open_time
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        p["duration"] = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        profit = p.get("profit", 0)
        if profit > 0:
            p["status"] = "盈利"
        elif profit < 0:
            p["status"] = "亏损"
        else:
            p["status"] = "持平"

    return positions


# ============================================================
# 账户实时摘要
# ============================================================

def get_account_summary() -> dict:
    """获取账户实时摘要（含持仓汇总）。

    Returns:
        dict: 账户摘要。
    """
    info = get_account_info()
    if "error" in info:
        return {"error": info["error"]}

    positions = get_positions()
    total_positions = len(positions)
    total_volume = sum(p.get("volume", 0) for p in positions)

    equity = info.get("equity", 0)
    margin = info.get("margin", 0)
    margin_level = round(equity / margin * 100, 2) if margin > 0 else None

    result = {
        "balance": info.get("balance", 0),
        "equity": equity,
        "margin": margin,
        "free_margin": info.get("free_margin", 0),
        "margin_level": margin_level,
        "floating_profit": info.get("profit", 0),
        "leverage": info.get("leverage", 0),
        "total_positions": total_positions,
        "total_volume": round(total_volume, 2),
    }

    print(f"[实时] 账户摘要: 余额={result['balance']:.2f}, 净值={result['equity']:.2f}, "
          f"持仓={total_positions}笔, 总手数={total_volume}")

    return result


# ============================================================
# 交易信号展示
# ============================================================

def get_trading_signals_display(advisor_result: dict) -> dict:
    """将 AI 分析结果转换为交易确认面板的展示数据。

    中国股市惯例：涨/买/利好 → 红色，跌/卖/利空 → 绿色，中性 → 黄色。

    Args:
        advisor_result: run_advisor() 返回的 state dict。

    Returns:
        dict: 交易面板数据。
    """
    report = advisor_result.get("final_report", {})
    tech = report.get("agent_summaries", {}).get("technical", {})
    sent = report.get("agent_summaries", {}).get("sentiment", {})
    fund = report.get("agent_summaries", {}).get("fundamental", {})

    signal = report.get("final_signal", "hold")
    signal_color = {"buy": "red", "sell": "green", "hold": "yellow"}.get(signal, "yellow")

    risk = report.get("risk_management", {})
    entry_price = risk.get("entry_price", 0)
    stop_loss = risk.get("stop_loss", 0)
    take_profit = risk.get("take_profit", 0)
    rr_ratio = risk.get("risk_reward_ratio", 0)

    try:
        vol = calculate_volume(risk_percent=2, entry_price=entry_price, stop_loss=stop_loss)
    except Exception:
        vol = 0.01

    risk_warning = None
    if rr_ratio < 1:
        risk_warning = f"⚠️ 风险回报比 1:{rr_ratio:.2f} < 1，潜在亏损大于盈利，不建议入场！"

    reasoning_parts = []
    if tech.get("summary"):
        reasoning_parts.append(f"【技术面】{tech['summary']}")
    if sent.get("analysis"):
        reasoning_parts.append(f"【情绪面】{sent['analysis']}")
    if fund.get("outlook"):
        reasoning_parts.append(f"【基本面】{fund['outlook']}")
    reasoning = "\n\n".join(reasoning_parts) if reasoning_parts else "AI 分析摘要暂不可用"

    result = {
        "signal": signal.upper(),
        "signal_color": signal_color,
        "confidence": report.get("confidence", 0),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rr_ratio": rr_ratio,
        "suggested_volume": vol,
        "risk_warning": risk_warning,
        "reasoning": reasoning,
        "weights": report.get("weights", {}),
        "individual_scores": report.get("individual_scores", {}),
        "consensus": report.get("consensus", ""),
    }

    print(f"[实时] 交易信号: {result['signal']}, 置信度={result['confidence']}%, "
          f"入场={entry_price}, 止损={stop_loss}, 止盈={take_profit}")

    return result


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  实时数据模块 - 自测")
    print("=" * 55)

    print("\n[1] 实时报价")
    print("-" * 40)
    tick = get_tick_price("XAUUSD")
    print(f"  Bid={tick['bid']}, Ask={tick['ask']}, Spread={tick['spread']}, Change={tick['change']}%")

    print("\n[2] 价格序列 (最近 60 秒)")
    print("-" * 40)
    for _ in range(3):
        get_tick_price("XAUUSD")
    history = get_price_history("XAUUSD", seconds=60)
    print(f"  共 {len(history)} 条记录")

    print("\n[3] 实时持仓")
    print("-" * 40)
    positions = get_positions_realtime("XAUUSD")
    if positions:
        for p in positions:
            print(f"  #{p['ticket']} {p['type']} {p['volume']}手 "
                  f"盈亏=${p['profit']:.2f} ({p['profit_pips']}点) {p['status']} "
                  f"持仓{p['duration']}")
    else:
        print("  无持仓")

    print("\n[4] 账户摘要")
    print("-" * 40)
    summary = get_account_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")

    print("\n[5] 交易信号面板 (Mock)")
    print("-" * 40)
    mock_result = {
        "final_report": {
            "final_signal": "buy",
            "confidence": 65,
            "risk_management": {
                "entry_price": 4030, "stop_loss": 4000, "take_profit": 4100,
                "risk_reward_ratio": 2.33,
            },
            "agent_summaries": {
                "technical": {"summary": "KDJ金叉+RSI超卖反弹，短期偏多。"},
                "sentiment": {"analysis": "降息预期+避险情绪，利好黄金。"},
                "fundamental": {"outlook": "美元走弱支撑金价，偏多。"},
            },
            "weights": {"technical": 0.45, "sentiment": 0.25, "fundamental": 0.30},
            "individual_scores": {"technical": 65, "sentiment": 60, "fundamental": 55},
            "consensus": "一致看多",
        },
    }
    display = get_trading_signals_display(mock_result)
    for k, v in display.items():
        if k == "reasoning":
            print(f"  {k}:")
            for line in v.split("\n"):
                print(f"    {line}")
        else:
            print(f"  {k}: {v}")

    print("\n" + "=" * 55)
    print("  自测完成")
    print("=" * 55)
