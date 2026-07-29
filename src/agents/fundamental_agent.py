"""
基本面分析 Agent
通过宏观经济数据分析黄金基本面，结合 LLM 评估宏观因素对金价的影响。
"""

import sys
from pathlib import Path

import pandas as pd

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.macro_data import get_macro_summary
from src.utils.llm import call_llm_json


def format_macro_for_llm(macro_data: dict) -> str:
    """将宏观数据格式化为 LLM 可读的文本。

    Args:
        macro_data: get_macro_summary() 返回的 dict。

    Returns:
        str: 格式化文本。
    """
    lines = ["===== 宏观经济指标 =====", ""]
    dxy = macro_data.get("dxy")
    vix = macro_data.get("vix", {})
    tsy = macro_data.get("treasury_10y", {})

    # ── 美元指数 ──
    lines.append("【美元指数 (USD/EUR 代理)】")
    if isinstance(dxy, pd.DataFrame) and not dxy.empty:
        current = dxy["usd_eur"].iloc[-1]
        lines.append(f"当前汇率: {current:.4f}")

        # 近 5 日趋势
        if len(dxy) >= 5:
            recent = dxy["usd_eur"].iloc[-5:]
            vals = recent.tolist()
            first, last = vals[0], vals[-1]
            if last > first * 1.001:
                trend = "美元走强（USD/EUR 升值）"
            elif last < first * 0.999:
                trend = "美元走弱（USD/EUR 贬值）"
            else:
                trend = "美元稳定"
            lines.append(f"近5日趋势: {trend}")
            lines.append(f"近5日数据: {[round(v, 4) for v in vals]}")
        else:
            lines.append("近5日趋势: 数据不足（少于5条）")
            lines.append(f"可用数据: {dxy['usd_eur'].tolist()}")
    else:
        lines.append("当前汇率: 数据暂不可用")
    lines.append("")

    # ── VIX ──
    lines.append("【VIX 恐慌指数】")
    if vix.get("value", 0) > 0:
        lines.append(f"当前值: {vix['value']}")
        change = vix.get("change", 0)
        sign = "+" if change >= 0 else ""
        lines.append(f"涨跌幅: {sign}{change}%")
        lines.append(f"状态: {vix.get('label', '未知')}")
        src = vix.get("source", "")
        if src and src != "默认值":
            lines.append(f"来源: {src}")
    else:
        lines.append("VIX 数据暂不可用")
    lines.append("")

    # ── 10Y 美债 ──
    lines.append("【10年期美债收益率】")
    y10 = tsy.get("yield_10y", 0)
    if y10 > 0:
        lines.append(f"当前收益率: {y10}%")
        lines.append(f"近期变化: {tsy.get('change', 0)}")
        lines.append(f"解读: {tsy.get('label', '未知')}")
    else:
        lines.append("10Y 美债数据暂不可用")
    lines.append("")
    lines.append("=" * 30)

    text = "\n".join(lines)
    print(f"[基本面] 已格式化宏观数据 ({len(lines)} 行)")
    return text


def _macro_snapshot(macro_data: dict) -> dict:
    """提取宏观数据的简要摘要。"""
    dxy = macro_data.get("dxy")
    vix = macro_data.get("vix", {})
    tsy = macro_data.get("treasury_10y", {})

    sn = {
        "timestamp": macro_data.get("timestamp", ""),
        "usd_eur": None,
        "vix_value": None,
        "treasury_10y": None,
    }

    if isinstance(dxy, pd.DataFrame) and not dxy.empty:
        sn["usd_eur"] = round(float(dxy["usd_eur"].iloc[-1]), 4)
    if vix.get("value", 0) > 0:
        sn["vix_value"] = vix["value"]
    if tsy.get("yield_10y", 0) > 0:
        sn["treasury_10y"] = tsy["yield_10y"]

    return sn


def _default_result(reason: str = "基本面分析失败") -> dict:
    """返回默认 hold 结果。"""
    return {
        "signal": "hold",
        "confidence": 0,
        "overall_fundamental": "中性",
        "dollar_analysis": reason,
        "rate_analysis": reason,
        "vix_analysis": reason,
        "macro_environment": "数据不可用",
        "key_factors": [],
        "outlook": "无法判断",
        "recommendation": "观望",
        "error": reason,
        "macro_snapshot": {},
    }


SYSTEM_PROMPT_FUNDAMENTAL = """你是一位专业的黄金基本面分析师，擅长分析宏观经济数据对黄金价格的影响。

黄金价格的核心驱动因素：
- 美元指数：与黄金通常负相关，美元走强利空黄金
- 实际利率：高利率环境利空黄金（持有黄金无利息收益）
- VIX恐慌指数：VIX升高避险情绪升温，利好黄金
- 美债收益率：收益率上升利空黄金

请基于提供的宏观数据，分析基本面因素对黄金的影响。
请严格按照 JSON 格式返回，不要包含 markdown 代码块标记。

返回格式：
{
  "signal": "buy" 或 "sell" 或 "hold",
  "confidence": 0-100 的整数,
  "overall_fundamental": "利好" 或 "利空" 或 "中性",
  "dollar_analysis": "美元指数对黄金的影响分析，1-2句话",
  "rate_analysis": "利率环境对黄金的影响分析，1-2句话",
  "vix_analysis": "市场恐慌情绪对黄金的影响分析，1-2句话",
  "macro_environment": "当前宏观环境总结，1句话",
  "key_factors": [
    {"factor": "因素名称", "direction": "利好/利空/中性", "strength": "强/中/弱", "note": "简短说明"}
  ],
  "outlook": "短期基本面展望：偏多/偏空/中性，1-2句话",
  "recommendation": "基于基本面的建议：买入/卖出/观望"
}"""


def analyze_fundamental(macro_data: dict = None) -> dict:
    """基本面分析主函数。

    Args:
        macro_data: get_macro_summary() 返回的 dict，为 None 时自动获取。

    Returns:
        dict: LLM 基本面分析结果，包含 macro_snapshot 字段。
    """
    # ── 获取数据 ──
    if macro_data is None:
        print("[基本面] 自动获取宏观数据...")
        try:
            macro_data = get_macro_summary()
        except Exception as e:
            print(f"[基本面] 宏观数据获取失败: {e}")
            return _default_result(f"宏观数据获取失败: {e}")

    if not macro_data:
        print("[基本面] 宏观数据为空")
        return _default_result("宏观数据为空")

    # ── 格式化 ──
    print("\n" + "-" * 40)
    print("[基本面] 格式化宏观数据...")
    print("-" * 40)
    macro_text = format_macro_for_llm(macro_data)

    # ── 构建 prompt ──
    prompt = f"""请分析以下宏观经济数据对黄金价格的影响：

{macro_text}

请基于以上宏观数据，从美元、利率、市场恐慌三个维度分析基本面因素对黄金的影响，并返回 JSON 结果。
"""
    # ── 调用 LLM ──
    print("\n" + "-" * 40)
    print("[基本面] 调用 AI 分析...")
    print("-" * 40)
    result = call_llm_json(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_FUNDAMENTAL,
        temperature=0.2,
    )

    if not result:
        result = _default_result("LLM 调用失败")

    # ── 附加宏观摘要 ──
    result["macro_snapshot"] = _macro_snapshot(macro_data)
    return result


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  基本面分析 Agent - 自测")
    print("=" * 55)

    result = analyze_fundamental()

    # ── 格式化打印 ──
    print("\n" + "=" * 55)
    print("  基本面分析结果")
    print("=" * 55)

    signal_icon = {"buy": "🟢 BUY", "sell": "🔴 SELL", "hold": "🟡 HOLD"}
    bull_bear = {"利好": "🟢 利好", "利空": "🔴 利空", "中性": "🟡 中性"}

    print(f"\n  信号: {signal_icon.get(result.get('signal', 'hold'), 'HOLD')}")
    print(f"  置信度: {result.get('confidence', 0)}/100")
    print(f"  整体基本面: {bull_bear.get(result.get('overall_fundamental', '中性'), '中性')}")

    print(f"\n  美元分析: {result.get('dollar_analysis', '无')}")
    print(f"  利率分析: {result.get('rate_analysis', '无')}")
    print(f"  VIX分析: {result.get('vix_analysis', '无')}")
    print(f"  宏观环境: {result.get('macro_environment', '无')}")

    factors = result.get("key_factors", [])
    if factors:
        print(f"\n  关键因素 ({len(factors)} 项):")
        for i, f in enumerate(factors):
            direc = bull_bear.get(f.get("direction", ""), f.get("direction", ""))
            print(f"    [{i + 1}] {f.get('factor', '?')} → {direc} "
                  f"(强度: {f.get('strength', '?')})")
            if f.get("note"):
                print(f"        说明: {f.get('note')}")
    else:
        print(f"\n  关键因素: 无")

    print(f"\n  展望: {result.get('outlook', '无')}")
    print(f"  建议: {result.get('recommendation', '观望')}")

    sn = result.get("macro_snapshot", {})
    if sn:
        print(f"\n  📊 宏观快照: USD/EUR={sn.get('usd_eur', '?')}, "
              f"VIX={sn.get('vix_value', '?')}, "
              f"10Y={sn.get('treasury_10y', '?')}%")

    if result.get("error"):
        print(f"\n  ⚠️ 错误: {result['error']}")

    print("=" * 55)
