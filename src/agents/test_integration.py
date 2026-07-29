"""
三 Agent 联调测试脚本
依次运行技术分析、情绪分析、基本面分析三个 Agent，验证返回结果并生成汇总报告。
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.mt5_data import connect_mt5, get_gold_klines, get_current_price, disconnect_mt5
from src.agents.technical_agent import analyze_technical
from src.agents.sentiment_agent import analyze_sentiment
from src.agents.fundamental_agent import analyze_fundamental

TZ_UTC8 = timezone(timedelta(hours=8))

# ── 字段验证 ──────────────────────────────────────────────


def _validate_technical(result: dict) -> tuple[bool, list[str]]:
    """验证技术分析结果字段完整性。"""
    required = [
        ("signal", str, ["buy", "sell", "hold"]),
        ("confidence", (int, float), None),
        ("entry_price", (int, float), None),
        ("stop_loss", (int, float), None),
        ("take_profit", (int, float), None),
        ("trend", str, None),
        ("indicators_summary", str, None),
    ]
    missing = []
    for field, expected_type, allowed in required:
        val = result.get(field)
        if val is None:
            if field == "indicators_summary":
                # 兜底结果可能为空字符串而不是缺失
                continue
            missing.append(f"缺失: {field}")
            continue
        if not isinstance(val, expected_type):
            missing.append(f"类型错误: {field} (期望 {expected_type}, 实际 {type(val).__name__})")
            continue
        if allowed and val not in allowed:
            missing.append(f"值异常: {field}={val} (允许: {allowed})")
    return len(missing) == 0, missing


def _validate_sentiment(result: dict) -> tuple[bool, list[str]]:
    """验证情绪分析结果字段完整性。"""
    required = [
        ("overall_sentiment", str, ["看多", "看空", "中性"]),
        ("sentiment_score", (int, float), None),
        ("gold_impact", str, ["利好", "利空", "中性"]),
        ("market_mood", str, None),
        ("analysis", str, None),
        ("recommendation", str, None),
    ]
    missing = []
    for field, expected_type, allowed in required:
        val = result.get(field)
        if val is None:
            missing.append(f"缺失: {field}")
            continue
        if not isinstance(val, expected_type):
            missing.append(f"类型错误: {field} (期望 {expected_type}, 实际 {type(val).__name__})")
            continue
        if allowed and val not in allowed:
            missing.append(f"值异常: {field}={val} (允许: {allowed})")
    # sentiment_score 范围检查
    score = result.get("sentiment_score", 0)
    if isinstance(score, (int, float)) and (score < -100 or score > 100):
        missing.append(f"范围错误: sentiment_score={score} (应为 -100~100)")
    return len(missing) == 0, missing


def _validate_fundamental(result: dict) -> tuple[bool, list[str]]:
    """验证基本面分析结果字段完整性。"""
    required = [
        ("signal", str, ["buy", "sell", "hold"]),
        ("confidence", (int, float), None),
        ("overall_fundamental", str, ["利好", "利空", "中性"]),
        ("dollar_analysis", str, None),
        ("rate_analysis", str, None),
        ("vix_analysis", str, None),
        ("outlook", str, None),
        ("recommendation", str, None),
    ]
    missing = []
    for field, expected_type, allowed in required:
        val = result.get(field)
        if val is None:
            missing.append(f"缺失: {field}")
            continue
        if not isinstance(val, expected_type):
            missing.append(f"类型错误: {field} (期望 {expected_type}, 实际 {type(val).__name__})")
            continue
        if allowed and val not in allowed:
            missing.append(f"值异常: {field}={val} (允许: {allowed})")
    return len(missing) == 0, missing


# ── 信号一致性 ──
def _check_consensus(results: dict) -> str:
    """检查三个 Agent 的信号一致性。"""
    signals = []
    tech = results.get("technical", {})
    fund = results.get("fundamental", {})

    # 技术分析
    t_sig = tech.get("signal", "hold")
    signals.append(("技术分析", t_sig))

    # 情绪分析：看多→buy, 看空→sell, 中性→hold
    sent = results.get("sentiment", {})
    s = sent.get("overall_sentiment", "中性")
    if s == "看多":
        s_sig = "buy"
    elif s == "看空":
        s_sig = "sell"
    else:
        s_sig = "hold"
    signals.append(("情绪分析", s_sig))

    # 基本面
    f_sig = fund.get("signal", "hold")
    signals.append(("基本面", f_sig))

    buy_count = sum(1 for _, s in signals if s == "buy")
    sell_count = sum(1 for _, s in signals if s == "sell")
    hold_count = sum(1 for _, s in signals if s == "hold")

    if buy_count == 3:
        return "🟢 一致看多（3/3 buy）"
    elif sell_count == 3:
        return "🔴 一致看空（3/3 sell）"
    elif hold_count == 3:
        return "🟡 一致观望（3/3 hold）"
    elif hold_count >= 2:
        return f"🟡 偏向观望（{hold_count} hold, {buy_count} buy, {sell_count} sell）"
    elif buy_count > sell_count:
        return f"🟢 偏向看多（{buy_count} buy, {sell_count} sell, {hold_count} hold）"
    else:
        return f"🔴 偏向看空（{sell_count} sell, {buy_count} buy, {hold_count} hold）"


# ── 主测试 ────────────────────────────────────────────────


def run_integration_test() -> dict:
    """依次运行三个 Agent 并返回汇总结果。

    Returns:
        dict: {
            "technical": dict,
            "sentiment": dict,
            "fundamental": dict,
            "gold_price": float,
            "validation": dict,
            "all_passed": bool,
            "consensus": str,
            "timestamp": str,
            "elapsed": float,
        }
    """
    results = {
        "technical": {},
        "sentiment": {},
        "fundamental": {},
        "gold_price": 0.0,
        "validation": {},
        "all_passed": False,
        "consensus": "",
        "timestamp": "",
        "elapsed": 0.0,
    }
    all_valid = True

    start = time.time()

    # ── 0. 获取 MT5 数据 ──
    print("=" * 55)
    print("  三 Agent 联调测试")
    print("=" * 55)

    print("\n[0/4] 获取 MT5 数据...")
    df = None
    try:
        if connect_mt5():
            price = get_current_price()
            results["gold_price"] = price
            df = get_gold_klines(count=500, timeframe="H1")
            disconnect_mt5()
            if df is not None and not df.empty:
                print(f"  ✅ MT5 数据: {len(df)} 根 K 线, 金价 ${price:.2f}")
            else:
                print("  ⚠️ K 线数据为空，技术分析将跳过")
        else:
            print("  ⚠️ MT5 连接失败，部分 Agent 将跳过")
    except Exception as e:
        print(f"  ⚠️ MT5 异常: {e}")
        try:
            disconnect_mt5()
        except Exception:
            pass

    # ── 1. 技术分析 ──
    print("\n" + "-" * 55)
    print("[1/4] 技术分析 Agent")
    print("-" * 55)
    try:
        tech_result = analyze_technical(df if df is not None and not df.empty else None)
        results["technical"] = tech_result
        ok, issues = _validate_technical(tech_result)
        results["validation"]["technical"] = {"passed": ok, "issues": issues}
        if not ok:
            all_valid = False
        print(f"  信号: {tech_result.get('signal', '?')}, "
              f"置信度: {tech_result.get('confidence', '?')}/100, "
              f"验证: {'✅ 通过' if ok else '❌ 失败'}")
        if issues:
            for issue in issues:
                print(f"    → {issue}")
    except Exception as e:
        print(f"  ❌ 技术分析异常: {e}")
        results["technical"] = {"signal": "hold", "confidence": 0, "error": str(e)}
        results["validation"]["technical"] = {"passed": False, "issues": [str(e)]}
        all_valid = False

    # ── 2. 情绪分析 ──
    print("\n" + "-" * 55)
    print("[2/4] 情绪分析 Agent")
    print("-" * 55)
    try:
        sent_result = analyze_sentiment()
        results["sentiment"] = sent_result
        ok, issues = _validate_sentiment(sent_result)
        results["validation"]["sentiment"] = {"passed": ok, "issues": issues}
        if not ok:
            all_valid = False
        print(f"  情绪: {sent_result.get('overall_sentiment', '?')}, "
              f"得分: {sent_result.get('sentiment_score', '?')}/100, "
              f"验证: {'✅ 通过' if ok else '❌ 失败'}")
        if issues:
            for issue in issues:
                print(f"    → {issue}")
    except Exception as e:
        print(f"  ❌ 情绪分析异常: {e}")
        results["sentiment"] = {"overall_sentiment": "中性", "sentiment_score": 0, "error": str(e)}
        results["validation"]["sentiment"] = {"passed": False, "issues": [str(e)]}
        all_valid = False

    # ── 3. 基本面分析 ──
    print("\n" + "-" * 55)
    print("[3/4] 基本面分析 Agent")
    print("-" * 55)
    try:
        fund_result = analyze_fundamental()
        results["fundamental"] = fund_result
        ok, issues = _validate_fundamental(fund_result)
        results["validation"]["fundamental"] = {"passed": ok, "issues": issues}
        if not ok:
            all_valid = False
        print(f"  信号: {fund_result.get('signal', '?')}, "
              f"置信度: {fund_result.get('confidence', '?')}/100, "
              f"验证: {'✅ 通过' if ok else '❌ 失败'}")
        if issues:
            for issue in issues:
                print(f"    → {issue}")
    except Exception as e:
        print(f"  ❌ 基本面分析异常: {e}")
        results["fundamental"] = {"signal": "hold", "confidence": 0, "error": str(e)}
        results["validation"]["fundamental"] = {"passed": False, "issues": [str(e)]}
        all_valid = False

    # ── 4. 汇总 ──
    elapsed = time.time() - start
    results["all_passed"] = all_valid
    results["consensus"] = _check_consensus(results)
    results["timestamp"] = datetime.now(TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S")
    results["elapsed"] = elapsed

    print(f"\n⏱️  联调总耗时: {elapsed:.1f} 秒")
    return results


# ── 打印报告 ──────────────────────────────────────────────


def print_integration_report(results: dict):
    """格式化打印联调汇总报告。

    Args:
        results: run_integration_test() 返回的 dict。
    """
    print("\n" + "=" * 60)
    print("  三 Agent 联调测试 - 汇总报告")
    print("=" * 60)

    signal_icon = {"buy": "🟢 BUY", "sell": "🔴 SELL", "hold": "🟡 HOLD"}

    # ── 技术分析 ──
    tech = results.get("technical", {})
    t_ok = results.get("validation", {}).get("technical", {}).get("passed", False)
    print(f"\n📈 技术分析 Agent — {'✅ 通过' if t_ok else '❌ 失败'}")
    print(f"   信号: {signal_icon.get(tech.get('signal', 'hold'), tech.get('signal', '?'))}")
    print(f"   置信度: {tech.get('confidence', 0)}/100")
    print(f"   趋势: {tech.get('trend', '?')}")
    print(f"   入场: ${tech.get('entry_price', 0):.2f}  |  "
          f"止损: ${tech.get('stop_loss', 0):.2f}  |  "
          f"止盈: ${tech.get('take_profit', 0):.2f}")
    if tech.get("indicators_summary"):
        print(f"   研判: {tech['indicators_summary']}")
    if tech.get("error"):
        print(f"   ⚠️ {tech['error']}")

    # ── 情绪分析 ──
    sent = results.get("sentiment", {})
    s_ok = results.get("validation", {}).get("sentiment", {}).get("passed", False)
    print(f"\n📰 情绪分析 Agent — {'✅ 通过' if s_ok else '❌ 失败'}")
    print(f"   情绪: {sent.get('overall_sentiment', '?')}")
    print(f"   得分: {sent.get('sentiment_score', 0)}/100")
    print(f"   对金影响: {sent.get('gold_impact', '?')} ({sent.get('impact_strength', '?')})")
    print(f"   市场氛围: {sent.get('market_mood', '?')}")
    if sent.get("analysis"):
        print(f"   分析: {sent['analysis']}")
    if sent.get("recommendation"):
        print(f"   建议: {sent['recommendation']}")
    if sent.get("error"):
        print(f"   ⚠️ {sent['error']}")

    # ── 基本面 ──
    fund = results.get("fundamental", {})
    f_ok = results.get("validation", {}).get("fundamental", {}).get("passed", False)
    print(f"\n🏦 基本面分析 Agent — {'✅ 通过' if f_ok else '❌ 失败'}")
    print(f"   信号: {signal_icon.get(fund.get('signal', 'hold'), fund.get('signal', '?'))}")
    print(f"   置信度: {fund.get('confidence', 0)}/100")
    print(f"   整体: {fund.get('overall_fundamental', '?')}")
    print(f"   宏观: {fund.get('macro_environment', '?')}")
    if fund.get("outlook"):
        print(f"   展望: {fund['outlook']}")
    if fund.get("recommendation"):
        print(f"   建议: {fund['recommendation']}")
    if fund.get("error"):
        print(f"   ⚠️ {fund['error']}")

    # ── 信号一致性 ──
    print(f"\n{'─' * 60}")
    print(f"📊 信号一致性: {results.get('consensus', '无法判断')}")
    print(f"💰 当前金价: ${results.get('gold_price', 0):.2f}")

    # ── 总结 ──
    all_passed = results.get("all_passed", False)
    print(f"\n{'=' * 60}")
    if all_passed:
        print("  ✅ 三 Agent 联调全部通过")
    else:
        print("  ⚠️  部分 Agent 验证失败，详情见上方")
    print(f"  🕐 {results.get('timestamp', '')}")
    print(f"  ⏱️  总耗时: {results.get('elapsed', 0):.1f} 秒")
    print("=" * 60)


# ── 入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    results = run_integration_test()
    print_integration_report(results)
