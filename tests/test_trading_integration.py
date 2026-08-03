"""
交易系统联调测试脚本
端到端验证完整交易流程：报价→风控→开仓→持仓→平仓→日志→统计

使用方法：
    cd D:\\gold-advisor
    venv\\Scripts\\activate
    python tests\\test_trading_integration.py

前置条件：
    1. MT5 终端已打开并登录 Demo 账户
    2. .env 中 MT5 配置正确
    3. DeepSeek API Key 有效（AI分析部分需要）
"""

import sys
import os
import time
import json
from datetime import datetime

# 确保项目根目录在 sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ── 导入模块 ──
from src.trading.executor import (
    open_position, close_position, close_all_positions,
    get_positions, get_account_info, calculate_volume,
)
from src.trading.realtime import (
    get_tick_price, get_positions_realtime, get_account_summary,
)
from src.trading.logger import log_trade, get_trade_history, get_trade_stats
from src.trading.risk_guard import check_trade_risk, get_risk_status


# ── 测试工具 ──
passed = 0
failed = 0
test_results = []


def test(name, condition, detail=""):
    """记录测试结果。"""
    global passed, failed
    if condition:
        passed += 1
        test_results.append(("✅", name, detail))
        print(f"  ✅ {name}")
    else:
        failed += 1
        test_results.append(("❌", name, detail))
        print(f"  ❌ {name} — {detail}")


def section(title):
    """打印分节标题。"""
    print(f"\n{'=' * 55}")
    print(f"  {title}")
    print(f"{'=' * 55}")


# ============================================================
# 测试主流程
# ============================================================

def main():
    section("🏆 黄金交易系统 - 联调测试")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  模式: MT5 Demo（模拟盘）")

    # ──────────────────────────────────────
    # 第 1 阶段：基础模块验证
    # ──────────────────────────────────────
    section("[阶段1] 基础模块验证")

    # 1.1 账户信息
    print("\n[1.1] 账户信息获取")
    account = get_account_info()
    test("获取账户信息", "error" not in account, f"error={account.get('error', '')}")
    if "error" not in account:
        test("余额 > 0", account.get("balance", 0) > 0, f"余额=${account.get('balance', 0)}")
        print(f"    余额: ${account['balance']:,.2f}")
        print(f"    净值: ${account['equity']:,.2f}")
        print(f"    杠杆: 1:{account['leverage']}")

    # 1.2 实时报价
    print("\n[1.2] 实时报价获取")
    tick = get_tick_price("XAUUSD")
    test("获取实时报价", tick.get("bid", 0) > 0, f"bid={tick.get('bid')}")
    if tick.get("bid", 0) > 0:
        test("卖价 >= 买价", tick["ask"] >= tick["bid"], f"bid={tick['bid']}, ask={tick['ask']}")
        test("点差合理", 0 < tick["spread"] < 10, f"spread={tick['spread']}")
        print(f"    买价: ${tick['bid']:.2f}")
        print(f"    卖价: ${tick['ask']:.2f}")
        print(f"    点差: ${tick['spread']:.2f}")

    # 1.3 账户摘要
    print("\n[1.3] 账户摘要")
    summary = get_account_summary()
    test("获取账户摘要", "error" not in summary, f"error={summary.get('error', '')}")
    if "error" not in summary:
        test("持仓数字段存在", "total_positions" in summary)
        test("总手数字段存在", "total_volume" in summary)
        print(f"    持仓: {summary['total_positions']} 笔, 总手数: {summary['total_volume']:.2f}")

    # ──────────────────────────────────────
    # 第 2 阶段：风控模块验证
    # ──────────────────────────────────────
    section("[阶段2] 风控模块验证")

    # 2.1 正常交易应通过
    print("\n[2.1] 正常交易风控检查（应通过）")
    risk_ok = check_trade_risk(
        direction="buy",
        volume=0.01,
        bid=tick.get("bid", 4029),
        ask=tick.get("ask", 4030),
        account_info=account,
        positions=get_positions("XAUUSD"),
        stop_loss=tick.get("bid", 4029) - 30,
        take_profit=tick.get("ask", 4030) + 30,
    )
    test("正常交易通过风控", risk_ok["passed"], risk_ok.get("rejected_reason", ""))
    print(f"    检查项: {len(risk_ok['checks'])} 项")

    # 2.2 止损方向错误应拒绝
    print("\n[2.2] 止损方向错误（应拒绝）")
    risk_bad_sl = check_trade_risk(
        direction="buy",
        volume=0.01,
        bid=tick.get("bid", 4029),
        ask=tick.get("ask", 4030),
        account_info=account,
        positions=[],
        stop_loss=tick.get("ask", 4030) + 50,  # 买入止损在入场价上方 → 错误
        take_profit=tick.get("ask", 4030) + 100,
    )
    test("止损方向错误被拒绝", not risk_bad_sl["passed"])
    print(f"    拒绝原因: {risk_bad_sl['rejected_reason']}")

    # 2.3 手数超限应拒绝
    print("\n[2.3] 手数超限（应拒绝）")
    risk_big_vol = check_trade_risk(
        direction="buy",
        volume=999.0,
        bid=tick.get("bid", 4029),
        ask=tick.get("ask", 4030),
        account_info=account,
        positions=[],
    )
    test("手数超限被拒绝", not risk_big_vol["passed"])
    print(f"    拒绝原因: {risk_big_vol['rejected_reason']}")

    # 2.4 价格异常应拒绝
    print("\n[2.4] 价格异常（应拒绝）")
    risk_bad_price = check_trade_risk(
        direction="buy",
        volume=0.01,
        bid=0,
        ask=0,
        account_info=account,
        positions=[],
    )
    test("价格异常被拒绝", not risk_bad_price["passed"])
    print(f"    拒绝原因: {risk_bad_price['rejected_reason']}")

    # 2.5 风控状态
    print("\n[2.5] 风控状态获取")
    try:
        status = get_risk_status()
        test("风控状态获取", "status" in status, str(status))
        print(f"    状态: {status['status']}")
        print(f"    持仓: {status['current_positions']}/{status['max_positions']}")
        print(f"    总手数: {status['current_total_volume']}/{status['max_total_volume']}")
    except Exception as e:
        test("风控状态获取", False, str(e))

    # ──────────────────────────────────────
    # 第 3 阶段：交易执行验证（模拟盘）
    # ──────────────────────────────────────
    section("[阶段3] 交易执行验证（模拟盘）")

    # 记录测试前的持仓数
    initial_positions = get_positions("XAUUSD")
    initial_count = len(initial_positions)
    print(f"  测试前持仓数: {initial_count}")

    # 3.1 开仓
    print("\n[3.1] 开仓下单（0.01手买入）")
    open_result = open_position(
        symbol="XAUUSD",
        direction="buy",
        volume=0.01,
        comment="Integration Test BUY",
    )
    test("开仓成功", open_result.get("success", False), open_result.get("message", ""))
    ticket = open_result.get("order_ticket", 0)
    print(f"    订单号: #{ticket}")
    print(f"    消息: {open_result.get('message', '')}")

    if open_result.get("success"):
        # 记录开仓日志
        log_trade(
            action="open", symbol="XAUUSD", direction="buy",
            volume=0.01, price=tick.get("ask", 0), ticket=ticket,
            ai_signal="TEST", confidence=0,
            comment="Integration Test BUY",
            success=True, message="测试开仓",
        )
        print("    日志已记录")

        # 3.2 验证持仓
        print("\n[3.2] 验证持仓已创建")
        time.sleep(1)  # 等待MT5处理
        new_positions = get_positions("XAUUSD")
        test("持仓数增加", len(new_positions) > initial_count,
             f"之前={initial_count}, 之后={len(new_positions)}")

        # 验证持仓详情
        test_pos = None
        for p in new_positions:
            if p["ticket"] == ticket:
                test_pos = p
                break
        if test_pos:
            test("持仓方向正确", test_pos["type"] == "buy", f"type={test_pos['type']}")
            test("持仓手数正确", test_pos["volume"] == 0.01, f"volume={test_pos['volume']}")
            print(f"    方向: {test_pos['type']}, 手数: {test_pos['volume']}")
            print(f"    开仓价: ${test_pos['price_open']:.2f}")

        # 3.3 实时持仓监控
        print("\n[3.3] 实时持仓监控")
        rt_positions = get_positions_realtime("XAUUSD")
        test("实时持仓获取", len(rt_positions) > 0)
        if rt_positions:
            rt = rt_positions[0]
            test("持仓含盈亏字段", "profit" in rt)
            test("持仓含时长字段", "duration" in rt)
            test("持仓含状态字段", "status" in rt)
            print(f"    盈亏: ${rt.get('profit', 0):+.2f} ({rt.get('status', '?')})")
            print(f"    时长: {rt.get('duration', '?')}")

        # 3.4 平仓
        print("\n[3.4] 平仓测试")
        close_result = close_position(ticket)
        test("平仓成功", close_result.get("success", False), close_result.get("message", ""))
        print(f"    消息: {close_result.get('message', '')}")
        if close_result.get("success"):
            print(f"    盈亏: ${close_result.get('profit', 0):+.2f}")
            # 记录平仓日志
            log_trade(
                action="close", symbol="XAUUSD",
                direction=close_result.get("direction", "sell"),
                volume=close_result.get("volume", 0.01),
                price=close_result.get("price", 0),
                ticket=ticket,
                success=True,
                message=f"测试平仓 #{ticket}",
                profit=close_result.get("profit"),
            )
            print("    日志已记录")

        # 3.5 验证持仓已清除
        print("\n[3.5] 验证持仓已清除")
        time.sleep(1)
        final_positions = get_positions("XAUUSD")
        still_exists = any(p["ticket"] == ticket for p in final_positions)
        test("持仓已清除", not still_exists, f"ticket={ticket} 仍存在" if still_exists else "")
        print(f"    当前持仓数: {len(final_positions)}（测试前 {initial_count}）")

    # ──────────────────────────────────────
    # 第 4 阶段：日志与统计验证
    # ──────────────────────────────────────
    section("[阶段4] 日志与统计验证")

    # 4.1 交易历史
    print("\n[4.1] 交易历史读取")
    history = get_trade_history(limit=10)
    test("交易历史非空", len(history) > 0, "无记录")
    if history:
        latest = history[0]
        test("最新记录含时间戳", "timestamp" in latest)
        test("最新记录含操作类型", "action" in latest)
        test("最新记录含盈亏字段", "profit" in latest)
        print(f"    最近 {len(history)} 条记录")
        print(f"    最新: {latest.get('timestamp')} {latest.get('action')} "
              f"profit={latest.get('profit', '—')}")

    # 4.2 交易统计
    print("\n[4.2] 交易统计")
    stats = get_trade_stats()
    test("统计含总交易数", "total_trades" in stats)
    test("统计含开仓数", "total_opens" in stats)
    test("统计含平仓数", "total_closes" in stats)
    test("统计含胜率", "win_rate" in stats)
    test("统计含总盈亏", "total_profit" in stats)
    print(f"    总交易: {stats['total_trades']}")
    print(f"    开仓: {stats['total_opens']}, 平仓: {stats['total_closes']}")
    print(f"    胜率: {stats['win_rate']:.1f}% (盈{stats['win_count']}/亏{stats['loss_count']})")
    print(f"    总盈亏: ${stats['total_profit']:+.2f}")

    # ──────────────────────────────────────
    # 第 5 阶段：手数计算验证
    # ──────────────────────────────────────
    section("[阶段5] 手数计算验证")

    print("\n[5.1] 风险手数计算")
    vol = calculate_volume(risk_percent=2, entry_price=4030, stop_loss=4000, account_balance=100000)
    # 2% of 100000 = 2000, risk per lot = 30 * 100 = 3000, vol = 2000/3000 = 0.66
    test("手数计算合理", 0 < vol <= 1.0, f"vol={vol}")
    print(f"    2%风险, 入场4030, 止损4000, 余额100000 → {vol}手")

    vol2 = calculate_volume(risk_percent=5, entry_price=4030, stop_loss=4000, account_balance=100000)
    test("高风险手数更大", vol2 >= vol, f"2%={vol}, 5%={vol2}")
    print(f"    5%风险 → {vol2}手（应 >= 2%的 {vol}手）")

    # ──────────────────────────────────────
    # 汇总
    # ──────────────────────────────────────
    section("📊 测试汇总")
    total = passed + failed
    print(f"\n  总计: {total} 项")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")
    rate = passed / total * 100 if total > 0 else 0
    print(f"  通过率: {rate:.1f}%")

    if failed > 0:
        print("\n  失败项明细:")
        for icon, name, detail in test_results:
            if icon == "❌":
                print(f"    ❌ {name} — {detail}")

    print(f"\n{'=' * 55}")
    if failed == 0:
        print("  🎉 全部测试通过！交易系统联调成功！")
    else:
        print(f"  ⚠️  有 {failed} 项失败，请检查上方明细")
    print(f"{'=' * 55}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
