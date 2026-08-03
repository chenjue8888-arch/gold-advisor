"""
交易日志模块
记录所有交易操作到 JSONL 文件，支持历史查询和统计。
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TZ_UTC8 = timezone(timedelta(hours=8))

# 日志文件路径
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "data"
LOG_FILE = LOG_DIR / "trading_log.jsonl"


def _ensure_dir():
    """确保日志目录存在。"""
    os.makedirs(LOG_DIR, exist_ok=True)


def log_trade(
    action: str,
    symbol: str = "",
    direction: str = "",
    volume: float = 0,
    price: float = 0,
    ticket: int | None = None,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    ai_signal: str | None = None,
    confidence: int | None = None,
    comment: str = "",
    success: bool = True,
    message: str = "",
    profit: float | None = None,
):
    """记录一笔交易操作到 JSONL 文件和终端。

    Args:
        action: "open" / "close" / "modify" / "close_all"
        symbol: 交易品种。
        direction: "buy" / "sell"。
        volume: 手数。
        price: 成交价。
        ticket: 订单号（开仓后返回的 ticket）。
        stop_loss: 止损价。
        take_profit: 止盈价。
        ai_signal: AI 信号（BUY/SELL/HOLD）。
        confidence: AI 置信度。
        comment: 备注。
        success: 是否成功。
        message: 详细信息。
        profit: 平仓盈亏（仅 close/close_all 时有值）。
    """
    _ensure_dir()

    entry = {
        "timestamp": datetime.now(TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "symbol": symbol,
        "direction": direction,
        "volume": volume,
        "price": price,
        "ticket": ticket,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "ai_signal": ai_signal,
        "confidence": confidence,
        "comment": comment,
        "success": success,
        "message": message,
        "profit": profit,
    }

    # 写入 JSONL
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        print(f"[日志] ❌ 写入文件失败: {e}")

    # 控制台打印
    status = "✅" if success else "❌"
    signal_str = f" AI={ai_signal}({confidence}%)" if ai_signal else ""
    profit_str = f" 盈亏=${profit:+.2f}" if profit is not None else ""
    print(f"[日志] {status} {action.upper()} {symbol} {direction} "
          f"{volume}手 @ {price}{signal_str}{profit_str} | {message}")


def get_trade_history(limit: int = 50) -> list[dict]:
    """读取交易历史记录（从最新开始）。

    Args:
        limit: 最多返回条数。

    Returns:
        list[dict]: 交易记录列表。
    """
    if not LOG_FILE.exists():
        print("[日志] 暂无交易记录")
        return []

    records = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
    except Exception as e:
        print(f"[日志] ❌ 读取历史失败: {e}")
        return []

    # 按时间倒序
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[:limit]


def get_trade_stats() -> dict:
    """获取交易统计。

    使用平仓记录中的 profit 字段统计盈亏和胜率。

    Returns:
        dict: 交易统计数据。
    """
    if not LOG_FILE.exists():
        return {
            "total_trades": 0,
            "total_opens": 0,
            "total_closes": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "total_profit": 0.0,
        }

    records = []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except (json.JSONDecodeError, ValueError, KeyError):
                        continue
    except Exception as e:
        print(f"[日志] ❌ 读取统计失败: {e}")
        return {
            "total_trades": 0,
            "total_opens": 0,
            "total_closes": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "total_profit": 0.0,
        }

    total_trades = len(records)
    total_opens = sum(1 for r in records if r.get("action") == "open")
    close_records = [r for r in records if r.get("action") in ("close", "close_all")]
    total_closes = len(close_records)

    # 用 profit 字段统计盈亏
    win_count = 0
    loss_count = 0
    total_profit = 0.0

    for r in close_records:
        if not r.get("success"):
            continue
        profit = r.get("profit")
        if profit is None:
            continue
        profit = float(profit)
        total_profit += profit
        if profit > 0:
            win_count += 1
        elif profit < 0:
            loss_count += 1

    total_decided = win_count + loss_count
    win_rate = round(win_count / total_decided * 100, 2) if total_decided > 0 else 0.0

    return {
        "total_trades": total_trades,
        "total_opens": total_opens,
        "total_closes": total_closes,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "total_profit": round(total_profit, 2),
    }


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  交易日志模块 - 自测")
    print("=" * 55)

    # 1. 记录开仓日志
    print("\n[1] 记录开仓")
    print("-" * 40)
    log_trade(
        action="open",
        symbol="XAUUSD",
        direction="buy",
        volume=0.02,
        price=4030.50,
        ticket=12345,
        stop_loss=4000.00,
        take_profit=4100.00,
        ai_signal="BUY",
        confidence=65,
        comment="AI Advisor BUY",
        success=True,
        message="开仓成功",
    )

    # 2. 记录平仓日志
    print("\n[2] 记录平仓")
    print("-" * 40)
    log_trade(
        action="close",
        symbol="XAUUSD",
        direction="sell",
        volume=0.02,
        price=4100.50,
        ticket=12345,
        ai_signal="SELL",
        confidence=60,
        success=True,
        message="平仓成功",
        profit=70.00,
    )

    # 3. 读取历史
    print("\n[3] 交易历史 (最近 5 条)")
    print("-" * 40)
    history = get_trade_history(limit=5)
    for h in history:
        print(f"  {h['timestamp']} {h['action']} {h['symbol']} {h['direction']} "
              f"{h['volume']}手 @ {h['price']} ticket={h.get('ticket')} "
              f"{'✅' if h['success'] else '❌'}")

    # 4. 交易统计
    print("\n[4] 交易统计")
    print("-" * 40)
    stats = get_trade_stats()
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 55)
    print("  自测完成")
    print("=" * 55)
