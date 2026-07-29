"""
策略引擎模块
融合三个 Agent 的信号，加权计算最终交易决策，并生成风控方案和完整报告。
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TZ_UTC8 = timezone(timedelta(hours=8))

# ── 权重配置 ──
DEFAULT_WEIGHTS = {
    "technical": 0.45,
    "sentiment": 0.25,
    "fundamental": 0.30,
}

# ── 风控参数 ──
RISK_PARAMS = {
    "conservative": {"stop_loss_pct": 0.02, "take_profit_pct": 0.03, "position_pct": 0.10},
    "moderate":     {"stop_loss_pct": 0.03, "take_profit_pct": 0.05, "position_pct": 0.20},
    "aggressive":   {"stop_loss_pct": 0.05, "take_profit_pct": 0.08, "position_pct": 0.30},
}


# ============================================================
# 信号转换
# ============================================================

def signal_to_score(signal: str, confidence: int) -> float:
    """将 buy/sell/hold 信号转为数值分数。

    Args:
        signal: "buy" / "sell" / "hold"。
        confidence: 0-100 置信度。

    Returns:
        float: -100 ~ +100 的分数。
    """
    if not signal:
        return 0.0
    s = signal.lower().strip()
    if s == "buy":
        return float(confidence)
    elif s == "sell":
        return -float(confidence)
    else:
        return 0.0


def sentiment_to_score(sentiment_score: int) -> float:
    """情绪分数直接返回（已经 -100 ~ +100）。

    Args:
        sentiment_score: 情绪得分，-100 ~ 100。

    Returns:
        float: 情绪分数。
    """
    if sentiment_score is None:
        return 0.0
    return float(sentiment_score)


# ============================================================
# 综合信号
# ============================================================

def combine_signals(
    technical: dict | None,
    sentiment: dict | None,
    fundamental: dict | None,
    weights: dict | None = None,
) -> dict:
    """加权融合三个 Agent 的信号。

    Args:
        technical: 技术分析 Agent 返回。
        sentiment: 情绪分析 Agent 返回。
        fundamental: 基本面 Agent 返回。
        weights: 可选自定义权重，默认 DEFAULT_WEIGHTS。

    Returns:
        dict: 包含 final_signal / combined_score / confidence 等字段。
    """
    w = weights or DEFAULT_WEIGHTS

    # ── 技术分析分数 ──
    tech_score = 0.0
    tech_conf = 0
    if technical and isinstance(technical, dict):
        tech_sig = technical.get("signal", "hold")
        tech_conf = technical.get("confidence", 0)
        if isinstance(tech_conf, (int, float)):
            tech_score = signal_to_score(tech_sig, int(tech_conf))
        else:
            tech_conf = 0
    else:
        print("[策略] ⚠️ 技术分析数据缺失，按 0 分处理")

    # ── 情绪分析分数 ──
    sent_score = 0.0
    sent_conf = 0
    if sentiment and isinstance(sentiment, dict):
        sent_score = sentiment_to_score(sentiment.get("sentiment_score", 0))
        # 情绪 Agent 不直接返回 confidence，根据分数绝对值估计
        sent_conf = min(int(abs(sent_score)), 100)
    else:
        print("[策略] ⚠️ 情绪分析数据缺失，按 0 分处理")

    # ── 基本面分数 ──
    fund_score = 0.0
    fund_conf = 0
    if fundamental and isinstance(fundamental, dict):
        fund_sig = fundamental.get("signal", "hold")
        fund_conf = fundamental.get("confidence", 0)
        if isinstance(fund_conf, (int, float)):
            fund_score = signal_to_score(fund_sig, int(fund_conf))
        else:
            fund_conf = 0
    else:
        print("[策略] ⚠️ 基本面数据缺失，按 0 分处理")

    # ── 加权计算 ──
    combined = (
        w["technical"] * tech_score
        + w["sentiment"] * sent_score
        + w["fundamental"] * fund_score
    )

    # ── 综合置信度（三 Agent 置信度加权平均）──
    total_w = (w["technical"] + w["sentiment"] + w["fundamental"])
    weighted_conf = (
        w["technical"] * tech_conf
        + w["sentiment"] * sent_conf
        + w["fundamental"] * fund_conf
    ) / total_w if total_w > 0 else 0

    # ── 最终信号 ──
    if combined > 30:
        final_signal = "buy"
    elif combined < -30:
        final_signal = "sell"
    else:
        final_signal = "hold"

    # ── 一致性判断 ──
    signals = []
    if technical:
        signals.append(technical.get("signal", "hold"))
    if sentiment:
        s = sentiment.get("overall_sentiment", "中性")
        signals.append("buy" if s == "看多" else ("sell" if s == "看空" else "hold"))
    if fundamental:
        signals.append(fundamental.get("signal", "hold"))
    agreement = len(set(signals)) == 1 if len(signals) >= 2 else False

    consensus_text = (
        f"{'✅ 一致' if agreement else '⚠️ 存在分歧'} "
        f"（技术={signals[0] if len(signals) > 0 else '?'}, "
        f"情绪={signals[1] if len(signals) > 1 else '?'}, "
        f"基本面={signals[2] if len(signals) > 2 else '?'}）"
    )

    result = {
        "final_signal": final_signal,
        "combined_score": round(combined, 2),
        "confidence": round(weighted_conf),
        "weights": w,
        "individual_scores": {
            "technical": round(tech_score, 2),
            "sentiment": round(sent_score, 2),
            "fundamental": round(fund_score, 2),
        },
        "signal_consensus": consensus_text,
        "agreement": agreement,
    }

    print(f"[策略] 技术={tech_score:.1f} 情绪={sent_score:.1f} 基本面={fund_score:.1f}")
    print(f"[策略] 综合={combined:.1f} → {final_signal.upper()} (置信度={round(weighted_conf)})")
    print(f"[策略] {consensus_text}")

    return result


# ============================================================
# 风控计算
# ============================================================

def calculate_risk_management(
    technical: dict | None,
    current_price: float,
    risk_level: str = "moderate",
) -> dict:
    """基于技术分析或风控参数计算止损/止盈/仓位。

    Args:
        technical: 技术分析结果（优先使用其 stop_loss / take_profit）。
        current_price: 当前金价。
        risk_level: 风险偏好，"conservative" / "moderate" / "aggressive"。

    Returns:
        dict: 风控方案。
    """
    params = RISK_PARAMS.get(risk_level, RISK_PARAMS["moderate"])
    entry_price = current_price
    stop_loss = 0.0
    take_profit = 0.0

    # 优先从技术分析取
    if technical and isinstance(technical, dict):
        tech_sl = technical.get("stop_loss", 0)
        tech_tp = technical.get("take_profit", 0)
        tech_entry = technical.get("entry_price", 0)
        tech_signal = technical.get("signal", "hold")

        if tech_entry and tech_entry > 0:
            entry_price = tech_entry

        # 看空时 LLM 给出的止损可能在入场价上方（做空逻辑），
        # 检查并修正：止损应该在亏损方向，止盈在盈利方向
        if tech_signal == "sell":
            # 做空：止损在上方（高价），止盈在下方（低价）
            if tech_sl and tech_sl > 0:
                stop_loss = tech_sl if tech_sl > entry_price else entry_price
            if tech_tp and tech_tp > 0:
                take_profit = tech_tp if tech_tp < entry_price else entry_price
        else:
            # 做多/观望：止损在下方，止盈在上方
            if tech_sl and tech_sl > 0:
                stop_loss = tech_sl if tech_sl < entry_price else entry_price
            if tech_tp and tech_tp > 0:
                take_profit = tech_tp if tech_tp > entry_price else entry_price

    # 如果未提供，按百分比计算
    if stop_loss == 0:
        stop_loss = round(entry_price * (1 - params["stop_loss_pct"]), 2)
    if take_profit == 0:
        take_profit = round(entry_price * (1 + params["take_profit_pct"]), 2)

    # 风险回报比（做多：止盈在上，止损在下；做空：止盈在下，止损在上）
    tech_signal = technical.get("signal", "hold") if technical and isinstance(technical, dict) else "hold"
    if tech_signal == "sell":
        risk_per_unit = stop_loss - entry_price   # 做空：止损在上方（亏损空间）
        reward_per_unit = entry_price - take_profit  # 做空：止盈在下方（盈利空间）
    else:
        risk_per_unit = entry_price - stop_loss   # 做多：止损在下方
        reward_per_unit = take_profit - entry_price  # 做多：止盈在上方
    rr_ratio = round(reward_per_unit / risk_per_unit, 2) if risk_per_unit > 0 else 0

    result = {
        "entry_price": round(entry_price, 2),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "position_size": f"{params['position_pct'] * 100:.0f}%",
        "risk_reward_ratio": rr_ratio,
        "max_loss_per_unit": round(abs(risk_per_unit), 2),
        "max_profit_per_unit": round(abs(reward_per_unit), 2),
        "risk_level": risk_level,
        "rr_warning": rr_ratio < 1.0,  # RR < 1 触发预警
    }

    # 风控日志（做空时金额逻辑颠倒，用绝对值展示）
    print(f"[策略] 风控({risk_level}): 入场={entry_price}, 止损={stop_loss}, "
          f"止盈={take_profit}, RR={rr_ratio}, 仓位={result['position_size']}"
          + (" ⚠️" if rr_ratio < 1.0 else ""))

    return result


# ============================================================
# 最终报告
# ============================================================

def generate_final_report(
    technical: dict | None,
    sentiment: dict | None,
    fundamental: dict | None,
    combined: dict,
    risk: dict,
    current_price: float,
) -> dict:
    """整合所有结果，生成最终分析报告。

    Args:
        technical: 技术分析结果。
        sentiment: 情绪分析结果。
        fundamental: 基本面结果。
        combined: combine_signals() 返回。
        risk: calculate_risk_management() 返回。
        current_price: 当前金价。

    Returns:
        dict: 完整报告。
    """
    ts = datetime.now(TZ_UTC8).strftime("%Y-%m-%d %H:%M:%S")

    # ── 技术摘要 ──
    tech_summary = {}
    if technical and isinstance(technical, dict):
        tech_summary = {
            "signal": technical.get("signal", "hold"),
            "confidence": technical.get("confidence", 0),
            "trend": technical.get("trend", "未知"),
            "summary": technical.get("indicators_summary", ""),
        }

    # ── 情绪摘要 ──
    sent_summary = {}
    if sentiment and isinstance(sentiment, dict):
        sent_summary = {
            "overall_sentiment": sentiment.get("overall_sentiment", "中性"),
            "sentiment_score": sentiment.get("sentiment_score", 0),
            "gold_impact": sentiment.get("gold_impact", "中性"),
            "market_mood": sentiment.get("market_mood", "未知"),
            "recommendation": sentiment.get("recommendation", "观望"),
        }

    # ── 基本面摘要 ──
    fund_summary = {}
    if fundamental and isinstance(fundamental, dict):
        fund_summary = {
            "signal": fundamental.get("signal", "hold"),
            "confidence": fundamental.get("confidence", 0),
            "overall": fundamental.get("overall_fundamental", "中性"),
            "macro_environment": fundamental.get("macro_environment", "未知"),
            "outlook": fundamental.get("outlook", "未知"),
            "recommendation": fundamental.get("recommendation", "观望"),
        }

    report = {
        "timestamp": ts,
        "current_price": current_price,
        "final_signal": combined.get("final_signal", "hold"),
        "combined_score": combined.get("combined_score", 0),
        "confidence": combined.get("confidence", 0),
        "risk_management": risk,
        "agent_summaries": {
            "technical": tech_summary,
            "sentiment": sent_summary,
            "fundamental": fund_summary,
        },
        "weights": combined.get("weights", DEFAULT_WEIGHTS),
        "individual_scores": combined.get("individual_scores", {}),
        "consensus": combined.get("signal_consensus", ""),
        "agreement": combined.get("agreement", False),
        "disclaimer": "本报告由 AI 生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。",
    }

    return report


# ── 格式化打印 ────────────────────────────────────────────

def print_strategy_report(report: dict):
    """格式化打印策略报告。"""
    print("\n" + "=" * 60)
    print("  黄金投资智能顾问 - 策略报告")
    print("=" * 60)

    signal_icon = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "🟡 观望"}
    fs = report.get("final_signal", "hold")

    print(f"\n{'─' * 60}")
    print(f"  📊 最终决策: {signal_icon.get(fs, fs.upper())}")
    print(f"  综合分数: {report.get('combined_score', 0):.1f} / 100")
    print(f"  置信度: {report.get('confidence', 0)}/100")
    print(f"  当前金价: ${report.get('current_price', 0):.2f}")

    # ── 各 Agent 分数 ──
    scores = report.get("individual_scores", {})
    print(f"\n  各维度得分:")
    print(f"    技术分析: {scores.get('technical', 0):+.1f}  (权重 {report.get('weights', {}).get('technical', 0)})")
    print(f"    情绪分析: {scores.get('sentiment', 0):+.1f}  (权重 {report.get('weights', {}).get('sentiment', 0)})")
    print(f"    基本面:   {scores.get('fundamental', 0):+.1f}  (权重 {report.get('weights', {}).get('fundamental', 0)})")

    # ── 一致性 ──
    print(f"\n  🔗 信号一致性: {report.get('consensus', '?')}")

    # ── 三 Agent 摘要 ──
    summaries = report.get("agent_summaries", {})

    tech = summaries.get("technical", {})
    if tech:
        print(f"\n  📈 技术: {tech.get('signal', '?').upper()}, "
              f"趋势={tech.get('trend', '?')}, "
              f"置信度={tech.get('confidence', '?')}")
        if tech.get("summary"):
            print(f"     {tech['summary'][:100]}...")

    sent = summaries.get("sentiment", {})
    if sent:
        print(f"\n  📰 情绪: {sent.get('overall_sentiment', '?')}, "
              f"得分={sent.get('sentiment_score', '?')}, "
              f"氛围={sent.get('market_mood', '?')}")
        if sent.get("recommendation"):
            print(f"     建议: {sent['recommendation']}")

    fund = summaries.get("fundamental", {})
    if fund:
        print(f"\n  🏦 基本面: {fund.get('signal', '?').upper()}, "
              f"整体={fund.get('overall', '?')}, "
              f"置信度={fund.get('confidence', '?')}")
        if fund.get("macro_environment"):
            print(f"     {fund['macro_environment']}")

    # ── 风控 ──
    risk = report.get("risk_management", {})
    if risk:
        print(f"\n  ⚖️ 风控方案 ({risk.get('risk_level', '?')}):")
        print(f"    入场: ${risk.get('entry_price', 0):.2f}")
        print(f"    止损: ${risk.get('stop_loss', 0):.2f}  "
              f"| 风险: ${risk.get('max_loss_per_unit', 0):.2f}/单位")
        print(f"    止盈: ${risk.get('take_profit', 0):.2f}  "
              f"| 收益: ${risk.get('max_profit_per_unit', 0):.2f}/单位")
        print(f"    风险回报比: 1:{risk.get('risk_reward_ratio', 0)}")
        if risk.get("rr_warning"):
            print(f"    ⚠️ 风险回报比 < 1，潜在亏损大于盈利，不建议入场！")
        print(f"    建议仓位: {risk.get('position_size', '?')}")

    # ── 时间 & 免责 ──
    print(f"\n  🕐 报告时间: {report.get('timestamp', '')}")
    print(f"\n  ⚠️  {report.get('disclaimer', '')}")
    print("=" * 60)


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  策略引擎 - 自测 (Mock 数据)")
    print("=" * 55)

    # ── Mock 数据 ──
    mock_technical = {
        "signal": "hold",
        "confidence": 60,
        "entry_price": 4049,
        "stop_loss": 4030,
        "take_profit": 4065,
        "trend": "震荡",
        "indicators_summary": "均线纠缠，MACD死叉但KDJ金叉，方向不明。",
        "key_levels": {"support": [4030, 4046], "resistance": [4065, 4099]},
        "risks": ["MACD死叉延续", "价格在布林中轨下方"],
    }

    mock_sentiment = {
        "overall_sentiment": "看多",
        "sentiment_score": 60,
        "gold_impact": "利好",
        "impact_strength": "中",
        "key_events": [
            {"event": "降息预期升温", "impact": "利好", "reason": "削弱美元"},
            {"event": "地缘风险", "impact": "利好", "reason": "避险需求"},
        ],
        "market_mood": "谨慎乐观",
        "analysis": "降息+避险双重利好黄金。",
        "recommendation": "观望",
    }

    mock_fundamental = {
        "signal": "sell",
        "confidence": 55,
        "overall_fundamental": "利空",
        "dollar_analysis": "美元走强施压黄金。",
        "rate_analysis": "高利率环境不利黄金。",
        "vix_analysis": "VIX正常，避险需求有限。",
        "macro_environment": "美元走强+高利率，利空黄金。",
        "key_factors": [
            {"factor": "美元走强", "direction": "利空", "strength": "中"},
            {"factor": "高利率", "direction": "利空", "strength": "强"},
        ],
        "outlook": "偏空，美元强势格局下黄金承压。",
        "recommendation": "观望",
    }

    current_price = 4049

    # ── 测试 1：信号融合 ──
    print("\n[测试 1] 信号加权融合")
    print("-" * 40)
    combined = combine_signals(mock_technical, mock_sentiment, mock_fundamental)
    print(f"  最终信号: {combined['final_signal']}")
    print(f"  综合分数: {combined['combined_score']}")
    print(f"  置信度: {combined['confidence']}")
    print(f"  一致性: {combined['agreement']}")

    # ── 测试 2：风控 ──
    print(f"\n[测试 2] 风控计算 (moderate)")
    print("-" * 40)
    risk = calculate_risk_management(mock_technical, current_price, "moderate")
    print(f"  入场: {risk['entry_price']} | 止损: {risk['stop_loss']} | 止盈: {risk['take_profit']}")
    print(f"  RR比: {risk['risk_reward_ratio']} | 仓位: {risk['position_size']}")

    # ── 测试 3：完整报告 ──
    print(f"\n[测试 3] 结果")
    print("-" * 40)
    report = generate_final_report(
        mock_technical, mock_sentiment, mock_fundamental,
        combined, risk, current_price,
    )

    print_strategy_report(report)
