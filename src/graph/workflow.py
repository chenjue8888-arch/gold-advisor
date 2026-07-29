"""
LangGraph 工作流编排模块
编排完整流程：数据采集 → 三 Agent 并行分析 → 策略引擎综合 → 最终报告。
"""

import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.mt5_data import connect_mt5, get_gold_klines, get_current_price, disconnect_mt5
from src.data.news_data import fetch_gold_news, fetch_gold_news_cn
from src.data.macro_data import get_macro_summary
from src.agents.technical_agent import analyze_technical
from src.agents.sentiment_agent import fetch_gold_news_safe, analyze_sentiment
from src.agents.fundamental_agent import analyze_fundamental
from src.strategy.engine import (
    combine_signals,
    calculate_risk_management,
    generate_final_report,
    print_strategy_report,
)

TZ_UTC8 = timezone(timedelta(hours=8))


# ============================================================
# 状态定义
# ============================================================

class AdvisorState(TypedDict, total=False):
    """黄金投资顾问工作流状态。"""
    # 数据层
    klines: Any              # MT5 K 线 DataFrame
    current_price: float     # 当前金价
    news_list: list          # 新闻列表
    macro_data: dict         # 宏观数据

    # Agent 结果
    technical_result: dict   # 技术分析结果
    sentiment_result: dict   # 情绪分析结果
    fundamental_result: dict # 基本面分析结果

    # 策略引擎结果
    combined_signal: dict    # 综合信号
    risk_management: dict    # 风控建议
    final_report: dict       # 最终报告

    # 元信息
    error: str               # 错误信息
    status: str              # 当前状态


# ============================================================
# 节点函数
# ============================================================

def collect_data(state: AdvisorState) -> dict:
    """数据采集节点：获取 MT5 行情、新闻、宏观数据。"""
    print("\n" + "─" * 50)
    print("[工作流] 📡 正在采集数据...")
    print("─" * 50)

    klines = None
    current_price = 0.0
    news_list = []
    macro_data = {}
    errors = []

    # ── MT5 行情 ──
    print("[工作流]   [1/3] MT5 行情...")
    try:
        if connect_mt5():
            current_price = get_current_price()
            klines = get_gold_klines(count=500, timeframe="H1")
            disconnect_mt5()
            if klines is not None and not klines.empty:
                print(f"[工作流]   ✅ 金价: ${current_price:.2f}, K线: {len(klines)} 根")
            else:
                print("[工作流]   ⚠️ K 线数据为空")
        else:
            print("[工作流]   ⚠️ MT5 连接失败")
            errors.append("MT5 连接失败")
    except Exception as e:
        print(f"[工作流]   ⚠️ MT5 异常: {e}")
        errors.append(f"MT5: {e}")
        try:
            disconnect_mt5()
        except Exception:
            pass

    # ── 新闻 ──
    print("[工作流]   [2/3] 财经新闻...")
    try:
        news_list = fetch_gold_news_safe(page_size=15)
        print(f"[工作流]   ✅ 新闻: {len(news_list)} 条")
    except Exception as e:
        print(f"[工作流]   ⚠️ 新闻异常: {e}")
        errors.append(f"新闻: {e}")

    # ── 宏观数据 ──
    print("[工作流]   [3/3] 宏观经济...")
    try:
        macro_data = get_macro_summary()
        print(f"[工作流]   ✅ 宏观数据已获取")
    except Exception as e:
        print(f"[工作流]   ⚠️ 宏观异常: {e}")
        errors.append(f"宏观: {e}")

    return {
        "klines": klines,
        "current_price": current_price,
        "news_list": news_list,
        "macro_data": macro_data,
        "status": "data_collected",
        "error": "; ".join(errors) if errors else "",
    }


def run_technical(state: AdvisorState) -> dict:
    """技术分析节点。"""
    print("\n[工作流] 📈 技术分析 Agent 运行中...")
    try:
        df = state.get("klines")
        result = analyze_technical(df)
        sig = result.get("signal", "?")
        conf = result.get("confidence", 0)
        print(f"[工作流]   ✅ 技术分析完成: {sig} (置信度={conf})")
        return {"technical_result": result}
    except Exception as e:
        print(f"[工作流]   ❌ 技术分析异常: {e}")
        return {"technical_result": {"signal": "hold", "confidence": 0, "error": str(e)}}


def run_sentiment(state: AdvisorState) -> dict:
    """情绪分析节点。"""
    print("\n[工作流] 📰 情绪分析 Agent 运行中...")
    try:
        news = state.get("news_list", [])
        result = analyze_sentiment(news)
        sent = result.get("overall_sentiment", "?")
        score = result.get("sentiment_score", 0)
        print(f"[工作流]   ✅ 情绪分析完成: {sent} (得分={score})")
        return {"sentiment_result": result}
    except Exception as e:
        print(f"[工作流]   ❌ 情绪分析异常: {e}")
        return {"sentiment_result": {"overall_sentiment": "中性", "sentiment_score": 0, "error": str(e)}}


def run_fundamental(state: AdvisorState) -> dict:
    """基本面分析节点。"""
    print("\n[工作流] 🏦 基本面分析 Agent 运行中...")
    try:
        macro = state.get("macro_data", {})
        result = analyze_fundamental(macro)
        sig = result.get("signal", "?")
        conf = result.get("confidence", 0)
        print(f"[工作流]   ✅ 基本面分析完成: {sig} (置信度={conf})")
        return {"fundamental_result": result}
    except Exception as e:
        print(f"[工作流]   ❌ 基本面分析异常: {e}")
        return {"fundamental_result": {"signal": "hold", "confidence": 0, "error": str(e)}}


def run_strategy(state: AdvisorState) -> dict:
    """策略引擎节点：综合三个 Agent 结果，生成决策。"""
    print("\n" + "─" * 50)
    print("[工作流] ⚙️  策略引擎运行中...")
    print("─" * 50)

    tech = state.get("technical_result", {})
    sent = state.get("sentiment_result", {})
    fund = state.get("fundamental_result", {})
    price = state.get("current_price", 0.0)

    # 补齐缺失的 Agent 结果
    if not tech:
        tech = {"signal": "hold", "confidence": 0, "error": "未获取"}
    if not sent:
        sent = {"overall_sentiment": "中性", "sentiment_score": 0, "error": "未获取"}
    if not fund:
        fund = {"signal": "hold", "confidence": 0, "error": "未获取"}

    try:
        # 信号融合
        combined = combine_signals(tech, sent, fund)

        # 风控
        risk = calculate_risk_management(tech, price, "moderate")

        # 最终报告
        report = generate_final_report(tech, sent, fund, combined, risk, price)

        print(f"[工作流]   ✅ 策略引擎完成: {combined['final_signal'].upper()}")
        return {
            "combined_signal": combined,
            "risk_management": risk,
            "final_report": report,
        }
    except Exception as e:
        print(f"[工作流]   ❌ 策略引擎异常: {e}")
        return {
            "combined_signal": {
                "final_signal": "hold", "combined_score": 0, "confidence": 0,
                "error": str(e),
            },
            "risk_management": {
                "entry_price": price, "stop_loss": 0, "take_profit": 0,
                "risk_level": "moderate", "error": str(e),
            },
            "final_report": {
                "final_signal": "hold", "current_price": price,
                "error": str(e),
            },
        }


def generate_output(state: AdvisorState) -> dict:
    """输出节点：打印最终报告摘要。"""
    print("\n" + "=" * 55)
    print("  🎯 工作流完成")
    print("=" * 55)

    report = state.get("final_report", {})
    if report:
        print_strategy_report(report)
    else:
        print("  ⚠️ 未能生成最终报告")

    return {"status": "completed"}


# ============================================================
# 构建工作流图
# ============================================================

def build_workflow() -> StateGraph:
    """构建并编译 LangGraph StateGraph。

    Returns:
        编译后的 workflow（可 .invoke(initial_state) 运行）。
    """
    print("[工作流] 🏗️  构建工作流图...")

    workflow = StateGraph(AdvisorState)

    # 添加节点
    workflow.add_node("collect_data", collect_data)
    workflow.add_node("technical", run_technical)
    workflow.add_node("sentiment", run_sentiment)
    workflow.add_node("fundamental", run_fundamental)
    workflow.add_node("strategy", run_strategy)
    workflow.add_node("output", generate_output)

    # 设置入口
    workflow.set_entry_point("collect_data")

    # 数据采集 → 三个 Agent 并行
    workflow.add_edge("collect_data", "technical")
    workflow.add_edge("collect_data", "sentiment")
    workflow.add_edge("collect_data", "fundamental")

    # 三个 Agent → 策略引擎
    workflow.add_edge("technical", "strategy")
    workflow.add_edge("sentiment", "strategy")
    workflow.add_edge("fundamental", "strategy")

    # 策略引擎 → 输出
    workflow.add_edge("strategy", "output")
    workflow.add_edge("output", END)

    compiled = workflow.compile()
    print("[工作流] ✅ 工作流图构建完成")
    return compiled


# ============================================================
# 运行入口
# ============================================================

def run_advisor() -> dict:
    """运行完整的黄金投资顾问工作流。

    Returns:
        dict: 最终 state。
    """
    print("\n" + "=" * 60)
    print("  黄金投资智能顾问 - 完整工作流")
    print(f"  🕐 {datetime.now(TZ_UTC8).strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    start = time.time()

    # 初始化状态
    initial_state: AdvisorState = {
        "klines": None,
        "current_price": 0.0,
        "news_list": [],
        "macro_data": {},
        "technical_result": {},
        "sentiment_result": {},
        "fundamental_result": {},
        "combined_signal": {},
        "risk_management": {},
        "final_report": {},
        "error": "",
        "status": "pending",
    }

    try:
        workflow = build_workflow()
        final_state = workflow.invoke(initial_state)  # type: ignore[arg-type]
    except Exception as e:
        print(f"[工作流] ❌ 工作流运行异常: {e}")
        final_state = {**initial_state, "error": str(e), "status": "failed"}

    elapsed = time.time() - start
    print(f"\n⏱️  工作流总耗时: {elapsed:.1f} 秒")

    if final_state.get("error"):
        print(f"[工作流] ⚠️ 部分环节异常: {final_state['error']}")

    return final_state


# ============================================================
# 测试入口
# ============================================================

def _print_full_report(report: dict):
    """打印完整投资分析报告。"""
    if not report:
        print("  ⚠️ 无报告数据")
        return

    signal_icon = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "🟡 观望"}
    fs = report.get("final_signal", "hold")

    print("\n" + "=" * 55)
    print("  黄金投资智能顾问 - 投资分析报告")
    print("=" * 55)

    print(f"\n  📊 综合信号: {signal_icon.get(fs, fs.upper())}")
    print(f"  📈 综合得分: {report.get('combined_score', 0):+.1f} / 100")
    print(f"  🎯 置信度: {report.get('confidence', 0)}%")
    print(f"  💰 当前金价: ${report.get('current_price', 0):.2f}")

    # ── 风控 ──
    risk = report.get("risk_management", {})
    if risk:
        print(f"\n  📐 风控建议 ({risk.get('risk_level', '?')}):")
        print(f"    入场价: ${risk.get('entry_price', 0):.2f}")
        print(f"    止损价: ${risk.get('stop_loss', 0):.2f}  "
              f"(风险: ${risk.get('max_loss_per_unit', 0):.2f}/单位)")
        print(f"    止盈价: ${risk.get('take_profit', 0):.2f}  "
              f"(收益: ${risk.get('max_profit_per_unit', 0):.2f}/单位)")
        print(f"    风险收益比: 1:{report.get('risk_management', {}).get('risk_reward_ratio', 0)}")
        print(f"    建议仓位: {risk.get('position_size', '?')}")
        if risk.get("rr_warning"):
            print(f"    ⚠️ 风险回报比 < 1，潜在亏损大于盈利，不建议入场！")

    # ── 三 Agent 摘要 ──
    summaries = report.get("agent_summaries", {})

    tech = summaries.get("technical", {})
    if tech:
        print(f"\n  📈 技术分析:")
        print(f"    信号: {tech.get('signal', '?').upper()} "
              f"(置信度: {tech.get('confidence', 0)}%)")
        print(f"    趋势: {tech.get('trend', '?')}")
        if tech.get("summary"):
            print(f"    研判: {tech['summary']}")

    sent = summaries.get("sentiment", {})
    if sent:
        print(f"\n  📰 情绪分析:")
        print(f"    情绪: {sent.get('overall_sentiment', '?')} "
              f"(得分: {sent.get('sentiment_score', 0)})")
        print(f"    影响: {sent.get('gold_impact', '?')}")
        print(f"    氛围: {sent.get('market_mood', '?')}")
        if sent.get("recommendation"):
            print(f"    建议: {sent['recommendation']}")

    fund = summaries.get("fundamental", {})
    if fund:
        print(f"\n  🏦 基本面分析:")
        print(f"    信号: {fund.get('signal', '?').upper()} "
              f"(置信度: {fund.get('confidence', 0)}%)")
        if fund.get("outlook"):
            print(f"    展望: {fund['outlook']}")
        if fund.get("recommendation"):
            print(f"    建议: {fund['recommendation']}")

    # ── 权重 ──
    weights = report.get("weights", {})
    print(f"\n  ⚖️ 权重分配:")
    print(f"    技术面: {weights.get('technical', 0) * 100:.0f}% | "
          f"情绪面: {weights.get('sentiment', 0) * 100:.0f}% | "
          f"基本面: {weights.get('fundamental', 0) * 100:.0f}%")
    print(f"    信号一致性: {report.get('consensus', '?')}")

    # ── 免责 ──
    print(f"\n  ⚠️ 免责声明: {report.get('disclaimer', '')}")
    print("=" * 55)


if __name__ == "__main__":
    final_state = run_advisor()

    report = final_state.get("final_report", {})
    if report:
        _print_full_report(report)
    else:
        print("\n⚠️ 未能生成最终报告")
        if final_state.get("error"):
            print(f"错误: {final_state['error']}")
