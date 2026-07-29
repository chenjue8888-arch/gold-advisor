"""
黄金投资智能顾问 - 主程序入口
v2.0：完整 LangGraph 工作流 → 策略报告 → JSON 持久化
"""

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve()))

from src.graph.workflow import run_advisor

TZ_UTC8 = timezone(timedelta(hours=8))

# ── 启动横幅 ─────────────────────────────────────────────

BANNER = r"""
========================================================
  🏆  黄金投资智能顾问 - Gold Advisor AI

  Powered by LangGraph + DeepSeek + MetaTrader 5

  多维度分析 · AI 驱动决策 · 全自动工作流
========================================================
"""

# ── 打印报告 ─────────────────────────────────────────────


def print_final_report(report: dict):
    """格式化打印完整投资分析报告。

    Args:
        report: final_report dict。
    """
    if not report:
        print("\n⚠️ 无报告数据")
        return

    signal_icon = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "🟡 观望"}

    print("\n" + "=" * 60)
    print("  📋 黄金投资智能顾问 - 投资分析报告")
    print("=" * 60)

    # ── a) 综合信号 ──
    fs = report.get("final_signal", "hold")
    score = report.get("combined_score", 0)
    conf = report.get("confidence", 0)
    price = report.get("current_price", 0)

    print(f"\n  {'─' * 56}")
    print(f"  📊 综合决策")
    print(f"  {'─' * 56}")
    print(f"  最终信号: {signal_icon.get(fs, fs.upper())}")
    print(f"  综合得分: {score:+.1f} / 100")
    print(f"  置信度: {conf}%")
    print(f"  当前金价: ${price:.2f}" if price > 0 else "  当前金价: 数据暂不可用")

    # ── b) 风控 ──
    risk = report.get("risk_management", {})
    if risk:
        print(f"\n  {'─' * 56}")
        print(f"  ⚖️ 风控建议 ({risk.get('risk_level', 'moderate')})")
        print(f"  {'─' * 56}")
        print(f"  入场价: ${risk.get('entry_price', 0):.2f}")
        print(f"  止损价: ${risk.get('stop_loss', 0):.2f}  "
              f"(风险: ${risk.get('max_loss_per_unit', 0):.2f}/单位)")
        print(f"  止盈价: ${risk.get('take_profit', 0):.2f}  "
              f"(收益: ${risk.get('max_profit_per_unit', 0):.2f}/单位)")
        print(f"  风险收益比: 1:{risk.get('risk_reward_ratio', 0)}")
        print(f"  建议仓位: {risk.get('position_size', '?')}")
        if risk.get("rr_warning"):
            print(f"  ⚠️ 风险回报比 < 1，潜在亏损大于盈利，不建议入场！")

    summaries = report.get("agent_summaries", {})

    # ── c) 技术分析 ──
    tech = summaries.get("technical", {})
    if tech:
        print(f"\n  {'─' * 56}")
        print(f"  📈 技术分析")
        print(f"  {'─' * 56}")
        ts = tech.get("signal", "?")
        print(f"  信号: {signal_icon.get(ts, ts.upper())} "
              f"(置信度: {tech.get('confidence', 0)}%)")
        print(f"  趋势: {tech.get('trend', '未知')}")
        if tech.get("summary"):
            print(f"  研判: {tech['summary']}")

    # ── d) 情绪分析 ──
    sent = summaries.get("sentiment", {})
    if sent:
        print(f"\n  {'─' * 56}")
        print(f"  📰 情绪分析")
        print(f"  {'─' * 56}")
        print(f"  情绪: {sent.get('overall_sentiment', '?')}  "
              f"(得分: {sent.get('sentiment_score', 0)})")
        print(f"  对金影响: {sent.get('gold_impact', '?')}  "
              f"(强度: {sent.get('impact_strength', '?')})")
        print(f"  市场氛围: {sent.get('market_mood', '?')}")
        if sent.get("recommendation"):
            print(f"  建议: {sent['recommendation']}")

    # ── e) 基本面 ──
    fund = summaries.get("fundamental", {})
    if fund:
        print(f"\n  {'─' * 56}")
        print(f"  🏦 基本面分析")
        print(f"  {'─' * 56}")
        fs2 = fund.get("signal", "?")
        print(f"  信号: {signal_icon.get(fs2, fs2.upper())}  "
              f"(置信度: {fund.get('confidence', 0)}%)")
        if fund.get("outlook"):
            print(f"  展望: {fund['outlook']}")
        if fund.get("macro_environment"):
            print(f"  宏观环境: {fund['macro_environment']}")
        if fund.get("recommendation"):
            print(f"  建议: {fund['recommendation']}")

    # ── f) 权重与一致性 ──
    print(f"\n  {'─' * 56}")
    print(f"  ⚖️ 权重分配与信号一致性")
    print(f"  {'─' * 56}")
    weights = report.get("weights", {})
    print(f"  技术面: {weights.get('technical', 0) * 100:.0f}% | "
          f"情绪面: {weights.get('sentiment', 0) * 100:.0f}% | "
          f"基本面: {weights.get('fundamental', 0) * 100:.0f}%")
    scores = report.get("individual_scores", {})
    print(f"  各维度得分: "
          f"技术={scores.get('technical', 0):+.1f}, "
          f"情绪={scores.get('sentiment', 0):+.1f}, "
          f"基本面={scores.get('fundamental', 0):+.1f}")
    print(f"  信号一致性: {report.get('consensus', '无法判断')}")

    # ── g) 免责声明 ──
    print(f"\n  ⚠️ {report.get('disclaimer', '本报告由AI生成，仅供参考。')}")

    print(f"\n  🕐 {report.get('timestamp', '')}")
    print("=" * 60)


# ── 保存报告 ─────────────────────────────────────────────


def save_report(report: dict) -> str:
    """将报告保存为 JSON 文件到 data/ 目录。

    Args:
        report: final_report dict。

    Returns:
        str: 保存的文件路径（失败时返回空字符串）。
    """
    # 确保 data/ 目录存在
    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(TZ_UTC8).strftime("%Y%m%d_%H%M%S")
    filename = f"gold_report_{ts}.json"
    filepath = data_dir / filename

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n📁 报告已保存至: {filepath}")
        return str(filepath)
    except Exception as e:
        print(f"\n❌ 报告保存失败: {e}")
        return ""


# ── 验证报告 ─────────────────────────────────────────────


def validate_report(report: dict) -> tuple[bool, list[str]]:
    """验证 final_report 的必要字段是否完整。

    Args:
        report: final_report dict。

    Returns:
        (是否通过, 错误列表)。
    """
    errors = []

    if not report:
        errors.append("final_report 为空")
        return False, errors

    # 顶层字段
    for key in ("final_signal", "combined_score", "confidence", "current_price"):
        if key not in report:
            errors.append(f"缺失顶层字段: {key}")

    # signal 合法值
    fs = report.get("final_signal", "")
    if fs not in ("buy", "sell", "hold"):
        errors.append(f"final_signal 值异常: '{fs}' (应为 buy/sell/hold)")

    # confidence 范围
    conf = report.get("confidence", -1)
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 100:
        errors.append(f"confidence 范围异常: {conf} (应为 0-100)")

    # 风控
    risk = report.get("risk_management", {})
    for key in ("entry_price", "stop_loss", "take_profit"):
        if key not in risk:
            errors.append(f"risk_management 缺失: {key}")

    # Agent 摘要
    summaries = report.get("agent_summaries", {})
    for key in ("technical", "sentiment", "fundamental"):
        if key not in summaries:
            errors.append(f"agent_summaries 缺失: {key}")

    if errors:
        print(f"\n⚠️ 报告验证发现 {len(errors)} 个问题:")
        for e in errors:
            print(f"   - {e}")
    else:
        print("\n✅ 报告字段验证通过")

    return len(errors) == 0, errors


# ── 主函数 ────────────────────────────────────────────────


def main() -> dict:
    """主入口：运行完整工作流并输出报告。

    Returns:
        dict: final_report。
    """
    print(BANNER)
    print(f"  🕐 启动时间: {datetime.now(TZ_UTC8).strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 56}\n")

    final_report = {}

    try:
        state = run_advisor()
        final_report = state.get("final_report", {})
    except Exception as e:
        print(f"\n❌ 工作流执行失败: {e}")
        import traceback
        traceback.print_exc()
        return final_report

    if not final_report:
        print("\n⚠️ 未生成最终报告")
        return {}

    # 打印报告
    print_final_report(final_report)

    # 保存报告
    save_report(final_report)

    return final_report


# ── 入口 ──────────────────────────────────────────────────
if __name__ == "__main__":
    report = main()

    if report:
        passed, issues = validate_report(report)
        if passed:
            print("\n" + "=" * 56)
            print("  ✅ 端到端联调通过！系统运行正常。")
            print(f"  📁 报告已保存至 data/ 目录")
            print("  🚀 可进入 Day 4 Streamlit 界面开发")
            print("=" * 56)
        else:
            print(f"\n⚠️ 报告验证未通过 ({len(issues)} 个问题)，请检查上述错误。")
    else:
        print("\n❌ 系统运行失败，未获取到报告。")
        print("  请检查 MT5 是否已打开并登录、DeepSeek API Key 是否有效。")
