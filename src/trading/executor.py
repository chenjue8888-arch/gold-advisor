"""
MT5 交易执行模块
封装下单、平仓、改单、查持仓、账户查询、风控手数计算。
"""

import sys
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

import MetaTrader5 as mt5

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import CONFIG

TZ_UTC8 = timezone(timedelta(hours=8))

# 默认交易品种
DEFAULT_SYMBOL = CONFIG.get("DEFAULT_SYMBOL", "XAUUSD")
# MT5 配置
MT5_LOGIN = int(CONFIG.get("MT5_LOGIN", 0))
MT5_PASSWORD = CONFIG["MT5_PASSWORD"]
MT5_SERVER = CONFIG["MT5_SERVER"]


# ============================================================
# 连接管理
# ============================================================

def _connect() -> bool:
    """连接并登录 MT5。"""
    if not mt5.initialize():
        err = mt5.last_error()
        print(f"[交易] MT5 初始化失败: {err}")
        return False
    if not mt5.login(MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print(f"[交易] MT5 登录失败: {mt5.last_error()}")
        mt5.shutdown()
        return False
    return True


def _disconnect():
    """断开 MT5。"""
    mt5.shutdown()


def _ensure_symbol(symbol: str) -> bool:
    """确保品种可选。"""
    info = mt5.symbol_info(symbol)
    if info is None:
        print(f"[交易] 品种 '{symbol}' 不存在")
        return False
    if not info.visible:
        mt5.symbol_select(symbol, True)
    return True


def _get_filling_mode(symbol: str) -> int:
    """从 symbol_info 自动检测支持的填充模式。

    MT5 填充模式 bitmask:
      bit 0 (1) = SYMBOL_FILLING_FOK → ORDER_FILLING_FOK
      bit 1 (2) = SYMBOL_FILLING_IOC → ORDER_FILLING_IOC

    Returns:
        mt5.ORDER_FILLING_FOK / mt5.ORDER_FILLING_IOC / mt5.ORDER_FILLING_RETURN
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        # 查询失败，默认用 IOC
        return mt5.ORDER_FILLING_IOC

    filling = info.filling_mode
    if filling & 1:  # FOK supported
        return mt5.ORDER_FILLING_FOK
    elif filling & 2:  # IOC supported
        return mt5.ORDER_FILLING_IOC
    else:
        # 都不支持，用 RETURN（部分经纪商兼容）
        return mt5.ORDER_FILLING_RETURN


def _send_order(request: dict) -> object:
    """发送订单，自动尝试多种填充模式。

    如果第一次 order_send 返回 None，依次尝试其他填充模式。
    """
    symbol = request.get("symbol", "")
    original_filling = request.get("type_filling", mt5.ORDER_FILLING_IOC)

    # 尝试的填充模式顺序
    filling_modes = [original_filling]
    for fm in [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]:
        if fm not in filling_modes:
            filling_modes.append(fm)

    result = None
    for fm in filling_modes:
        request["type_filling"] = fm
        result = mt5.order_send(request)
        if result is not None:
            return result
        # result 为 None，打印错误并尝试下一种模式
        err = mt5.last_error()
        print(f"[交易] ⚠️ order_send 返回 None (filling={fm}): {err}")

    return None


# ============================================================
# 开仓
# ============================================================

def open_position(
    symbol: str = DEFAULT_SYMBOL,
    direction: str = "buy",
    volume: float = 0.01,
    stop_loss: float | None = None,
    take_profit: float | None = None,
    comment: str = "AI Advisor",
) -> dict:
    """开仓下单。

    Args:
        symbol: 交易品种（默认 "XAUUSD"）。
        direction: "buy" 或 "sell"。
        volume: 手数。
        stop_loss: 止损价（可选）。
        take_profit: 止盈价（可选）。
        comment: 订单注释。

    Returns:
        {"success": bool, "order_ticket": int, "message": str}
    """
    if not _connect():
        return {"success": False, "order_ticket": 0, "message": "MT5 连接失败"}

    try:
        if not _ensure_symbol(symbol):
            return {"success": False, "order_ticket": 0, "message": f"品种 '{symbol}' 不可交易"}

        direction = direction.lower().strip()
        if direction not in ("buy", "sell"):
            return {"success": False, "order_ticket": 0, "message": f"无效方向: '{direction}'（应为 buy/sell）"}

        # 获取报价
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "order_ticket": 0, "message": f"无法获取 '{symbol}' 报价"}

        # ── 预取账户和持仓（避免嵌套 _connect/_disconnect 导致连接断开）──
        acct_raw = mt5.account_info()
        account_info = {
            "balance": acct_raw.balance if acct_raw else 0,
            "equity": acct_raw.equity if acct_raw else 0,
            "margin": acct_raw.margin if acct_raw else 0,
            "free_margin": acct_raw.margin_free if acct_raw else 0,
            "profit": acct_raw.profit if acct_raw else 0,
            "leverage": acct_raw.leverage if acct_raw else 0,
        } if acct_raw else {"error": "无法获取"}

        pos_raw = mt5.positions_get(symbol=symbol) or []
        type_map = {mt5.POSITION_TYPE_BUY: "buy", mt5.POSITION_TYPE_SELL: "sell"}
        positions = [{
            "ticket": p.ticket, "symbol": p.symbol,
            "type": type_map.get(p.type, str(p.type)),
            "volume": p.volume, "price_open": p.price_open,
            "price_current": p.price_current, "sl": p.sl, "tp": p.tp,
            "profit": p.profit, "swap": p.swap, "comment": p.comment,
        } for p in pos_raw]

        # ── 风控检查（传入预取的数据，避免嵌套连接断开）──
        from src.trading.risk_guard import check_trade_risk
        risk_result = check_trade_risk(
            direction=direction,
            volume=volume,
            bid=tick.bid,
            ask=tick.ask,
            account_info=account_info,
            positions=positions,
            stop_loss=stop_loss,
            take_profit=take_profit,
            symbol=symbol,
        )
        if not risk_result["passed"]:
            msg = f"风控拒绝: {risk_result['rejected_reason']}"
            print(f"[交易] ⛔ {msg}")
            return {"success": False, "order_ticket": 0, "message": msg}
        for w in risk_result.get("warnings", []):
            print(f"[交易] ⚠️ {w}")

        # 根据方向确定订单类型和价格
        if direction == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid

        # 自动检测填充模式
        filling_mode = _get_filling_mode(symbol)

        # 构建请求
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 20260728,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        if stop_loss is not None and stop_loss > 0:
            request["sl"] = stop_loss
        if take_profit is not None and take_profit > 0:
            request["tp"] = take_profit

        # 日志
        dir_cn = "买入" if direction == "buy" else "卖出"
        sl_str = f" SL={stop_loss}" if stop_loss else ""
        tp_str = f" TP={take_profit}" if take_profit else ""
        print(f"[交易] 开仓{dir_cn} {symbol} {volume}手 @ {price:.2f}{sl_str}{tp_str} 注释={comment}")

        # 发送订单（自动尝试多种填充模式）
        result = _send_order(request)

        if result is None:
            err = mt5.last_error()
            return {"success": False, "order_ticket": 0, "message": f"订单发送失败（返回 None）: {err}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            msg = f"下单失败: retcode={result.retcode}, comment={result.comment}"
            print(f"[交易] {msg}")
            return {"success": False, "order_ticket": 0, "message": msg}

        print(f"[交易] ✅ 开仓成功，订单号: {result.order}")
        return {
            "success": True,
            "order_ticket": result.order,
            "message": f"开仓成功，订单号 {result.order}",
        }

    except Exception as e:
        print(f"[交易] ❌ 开仓异常: {e}")
        return {"success": False, "order_ticket": 0, "message": str(e)}
    finally:
        _disconnect()


# ============================================================
# 平仓（按订单号）
# ============================================================

def close_position(ticket: int) -> dict:
    """按订单号平仓。

    Args:
        ticket: 持仓订单号。

    Returns:
        {"success": bool, "message": str}
    """
    if not _connect():
        return {"success": False, "message": "MT5 连接失败"}

    try:
        # 获取持仓
        pos = mt5.positions_get(ticket=ticket)
        if pos is None or len(pos) == 0:
            return {"success": False, "message": f"未找到订单 #{ticket}"}

        pos = pos[0]
        symbol = pos.symbol
        volume = pos.volume
        pos_type = pos.type  # 0=buy, 1=sell
        pos_profit = pos.profit  # 平仓前的浮动盈亏
        pos_open_price = pos.price_open

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"success": False, "message": f"无法获取 '{symbol}' 报价"}

        # 构造反向订单
        if pos_type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            direction = "sell"
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            direction = "buy"

        # 自动检测填充模式
        filling_mode = _get_filling_mode(symbol)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "deviation": 20,
            "magic": 20260728,
            "comment": "AI Advisor 平仓",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        print(f"[交易] 平仓 #{ticket} {symbol} {volume}手 @ {price:.2f} 盈亏=${pos_profit:.2f}")

        result = _send_order(request)

        if result is None:
            err = mt5.last_error()
            return {"success": False, "message": f"平仓发送失败: {err}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            msg = f"平仓失败: retcode={result.retcode}, comment={result.comment}"
            print(f"[交易] {msg}")
            return {"success": False, "message": msg}

        print(f"[交易] ✅ 平仓成功 #{ticket} 盈亏=${pos_profit:.2f}")
        return {
            "success": True,
            "message": f"平仓成功 #{ticket}",
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "volume": volume,
            "price": price,
            "open_price": pos_open_price,
            "profit": pos_profit,
        }

    except Exception as e:
        print(f"[交易] ❌ 平仓异常: {e}")
        return {"success": False, "message": str(e)}
    finally:
        _disconnect()


# ============================================================
# 全部平仓
# ============================================================

def close_all_positions(symbol: str | None = None) -> list[dict]:
    """全部平仓。

    Args:
        symbol: 指定品种（None=全部）。

    Returns:
        [{"ticket": int, "success": bool, "message": str}, ...]
    """
    if not _connect():
        return [{"ticket": 0, "success": False, "message": "MT5 连接失败"}]

    results = []
    try:
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None or len(positions) == 0:
            print("[交易] 没有需要平仓的持仓")
            return []

        print(f"[交易] 全部平仓，共 {len(positions)} 笔持仓")

        for pos in positions:
            r = close_position(pos.ticket)
            r["ticket"] = pos.ticket
            results.append(r)

        return results

    except Exception as e:
        print(f"[交易] ❌ 全部平仓异常: {e}")
        return [{"ticket": 0, "success": False, "message": str(e)}]
    finally:
        _disconnect()


# ============================================================
# 修改持仓
# ============================================================

def modify_position(
    ticket: int,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> dict:
    """修改持仓的止损止盈。

    Args:
        ticket: 订单号。
        stop_loss: 新止损价（None=不修改）。
        take_profit: 新止盈价（None=不修改）。

    Returns:
        {"success": bool, "message": str}
    """
    if stop_loss is None and take_profit is None:
        return {"success": False, "message": "未指定任何修改项"}

    if not _connect():
        return {"success": False, "message": "MT5 连接失败"}

    try:
        # 获取持仓信息
        pos = mt5.positions_get(ticket=ticket)
        if pos is None or len(pos) == 0:
            return {"success": False, "message": f"未找到订单 #{ticket}"}

        pos = pos[0]

        # 保持未修改的字段
        sl = stop_loss if stop_loss is not None else pos.sl
        tp = take_profit if take_profit is not None else pos.tp

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "symbol": pos.symbol,
            "sl": float(sl),
            "tp": float(tp),
        }

        sl_str = f" → {stop_loss}" if stop_loss is not None else ""
        tp_str = f" → {take_profit}" if take_profit is not None else ""
        print(f"[交易] 修改 #{ticket} SL{sl_str} TP{tp_str}")

        result = mt5.order_send(request)

        if result is None:
            return {"success": False, "message": "修改发送失败"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            msg = f"修改失败: retcode={result.retcode}, comment={result.comment}"
            print(f"[交易] {msg}")
            return {"success": False, "message": msg}

        print(f"[交易] ✅ 修改成功 #{ticket}")
        return {"success": True, "message": f"修改成功 #{ticket}"}

    except Exception as e:
        print(f"[交易] ❌ 修改异常: {e}")
        return {"success": False, "message": str(e)}
    finally:
        _disconnect()


# ============================================================
# 查询持仓
# ============================================================

def get_positions(symbol: str | None = None) -> list[dict]:
    """获取当前持仓列表。

    Args:
        symbol: 指定品种，None=全部。

    Returns:
        list[dict]: 持仓列表。
    """
    if not _connect():
        print("[交易] MT5 连接失败，无法获取持仓")
        return []

    try:
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None or len(positions) == 0:
            print("[交易] 当前无持仓")
            return []

        results = []
        for pos in positions:
            type_map = {mt5.POSITION_TYPE_BUY: "buy", mt5.POSITION_TYPE_SELL: "sell"}
            results.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": type_map.get(pos.type, str(pos.type)),
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "sl": pos.sl,
                "tp": pos.tp,
                "profit": pos.profit,
                "swap": pos.swap,
                "time": datetime.fromtimestamp(pos.time, tz=TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S"),
                "comment": pos.comment,
            })

        print(f"[交易] 当前持仓: {len(results)} 笔")
        return results

    except Exception as e:
        print(f"[交易] ❌ 获取持仓异常: {e}")
        return []
    finally:
        _disconnect()


# ============================================================
# 账户信息
# ============================================================

def get_account_info() -> dict:
    """获取账户信息。

    Returns:
        dict: 账户信息。
    """
    if not _connect():
        return {"error": "MT5 连接失败"}

    try:
        info = mt5.account_info()
        if info is None:
            return {"error": "无法获取账户信息"}

        result = {
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
            "server": info.server,
            "login": info.login,
        }

        print(f"[交易] 账户: #{result['login']}, 余额={result['balance']:.2f}, "
              f"净值={result['equity']:.2f}, 可用保证金={result['free_margin']:.2f}")
        return result

    except Exception as e:
        print(f"[交易] ❌ 获取账户异常: {e}")
        return {"error": str(e)}
    finally:
        _disconnect()


# ============================================================
# 风控手数计算
# ============================================================

def calculate_volume(
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    account_balance: float | None = None,
) -> float:
    """根据风险百分比计算建议手数。

    XAUUSD：1 手 = 100 盎司，每点 = $1（每变动 $1 = 100 点 = $100/手）。

    公式：手数 = (余额 × 风险比例) / (|入场 - 止损| × 100)

    Args:
        risk_percent: 风险比例（如 2 表示 2%）。
        entry_price: 入场价。
        stop_loss: 止损价。
        account_balance: 账户余额（None 则自动获取）。

    Returns:
        float: 建议手数（最小 0.01，向下取整到 0.01）。
    """
    # 获取余额
    if account_balance is None:
        info = get_account_info()
        account_balance = info.get("balance", 0)

    if account_balance is None or account_balance <= 0:
        print("[交易] 无法获取账户余额，返回最小手数 0.01")
        return 0.01

    # 风险金额
    risk_amount = account_balance * risk_percent / 100

    # 每手风险（XAUUSD：1 手 = 100 盎司，价格变动 $1 = $100）
    price_risk = abs(entry_price - stop_loss)
    if price_risk <= 0:
        print("[交易] 止损价与入场价相同，无法计算手数，返回 0.01")
        return 0.01

    lot_risk = price_risk * 100  # 每手风险金额

    # 手数
    volume = risk_amount / lot_risk
    volume = math.floor(volume * 100) / 100  # 向下取整到 0.01
    volume = max(volume, 0.01)  # 最小 0.01 手

    print(f"[交易] 风险计算: 余额=${account_balance:.2f} × {risk_percent}% = "
          f"${risk_amount:.2f}, 每手风险=${lot_risk:.2f}, 建议手数={volume:.2f}")

    return volume


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  交易执行模块 - 自测")
    print("=" * 55)

    # ── 账户信息 ──
    print("\n[1] 账户信息")
    print("-" * 40)
    info = get_account_info()
    for k, v in info.items():
        print(f"  {k}: {v}")

    # ── 持仓查询 ──
    print("\n[2] 当前持仓")
    print("-" * 40)
    positions = get_positions()
    if positions:
        for p in positions:
            print(f"  #{p['ticket']} {p['type']} {p['symbol']} "
                  f"{p['volume']}手 @ {p['price_open']:.2f} "
                  f"盈亏=${p['profit']:.2f}")
    else:
        print("  无持仓")

    # ── 手数计算 ──
    print("\n[3] 手数计算")
    print("-" * 40)
    vol = calculate_volume(risk_percent=2, entry_price=4030, stop_loss=4000, account_balance=100000)
    print(f"  2%风险, 入场4030, 止损4000, 余额100000 → {vol} 手")

    print("\n" + "=" * 55)
    print("  自测完成（未执行实际交易）")
    print("=" * 55)
