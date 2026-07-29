"""
市场情绪分析 Agent
通过分析财经新闻判断市场情绪，评估对黄金价格的影响。
"""

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.news_data import fetch_gold_news, fetch_gold_news_cn
from src.utils.llm import call_llm_json


def fetch_gold_news_safe(page_size: int = 15) -> list[dict]:
    """安全获取黄金新闻，合并英文和中文来源。

    Args:
        page_size: 每种语言大致获取条数。

    Returns:
        list[dict]: 新闻列表。
    """
    all_news = []
    try:
        en = fetch_gold_news(count=page_size)
        if en:
            all_news.extend(en)
    except Exception as e:
        print(f"[情绪] 英文新闻获取失败: {e}")
    try:
        cn = fetch_gold_news_cn(count=page_size)
        all_news.extend(cn)
    except Exception as e:
        print(f"[情绪] 中文新闻获取失败: {e}")

    if not all_news:
        print("[情绪] 未获取到任何新闻")
    else:
        en_count = sum(1 for n in all_news if '新浪' not in n.get('source', ''))
        cn_count = sum(1 for n in all_news if '新浪' in n.get('source', ''))
        print(f"[情绪] 获取新闻: 英文 {en_count} / 中文 {cn_count}，合计 {len(all_news)} 条")

    return all_news


def format_news_for_llm(news_list: list[dict], max_items: int = 15) -> str:
    """将新闻列表格式化为 LLM 可读的文本。

    Args:
        news_list: 新闻条目列表。
        max_items: 最多包含的新闻条数。

    Returns:
        str: 格式化后的文本。
    """
    if not news_list:
        return "（暂无新闻数据）"

    lines = []
    for i, n in enumerate(news_list[:max_items]):
        source = n.get("source", "未知")
        pub_time = n.get("published_at", "未知时间")
        title = n.get("title", "无标题")
        desc = n.get("description", "").strip()

        lines.append(f"【新闻{i + 1}】来源: {source} | 时间: {pub_time}")
        lines.append(f"标题: {title}")
        if desc:
            lines.append(f"摘要: {desc}")
        lines.append("")  # 空行分隔

    print(f"[情绪] 已格式化 {min(len(news_list), max_items)} 条新闻")
    return "\n".join(lines)


def _get_gold_price_safe() -> float | None:
    """安全获取当前金价（不保持 MT5 长连接）。"""
    try:
        from src.data.mt5_data import connect_mt5, get_current_price, disconnect_mt5
        if connect_mt5():
            price = get_current_price()
            disconnect_mt5()
            return price if price > 0 else None
        return None
    except Exception as e:
        print(f"[情绪] 获取金价失败: {e}")
        return None


def _default_result(reason: str = "无新闻数据可供分析", news_count: int = 0) -> dict:
    """返回默认中性结果。"""
    return {
        "overall_sentiment": "中性",
        "sentiment_score": 0,
        "gold_impact": "中性",
        "impact_strength": "弱",
        "key_events": [],
        "market_mood": "观望",
        "analysis": reason,
        "recommendation": "观望",
        "news_count": news_count,
    }


SYSTEM_PROMPT_SENTIMENT = """你是一位专业的金融市场情绪分析师，专注于分析新闻对黄金价格的影响。
请基于提供的新闻内容，分析市场情绪并评估对黄金的影响。
请严格按照 JSON 格式返回，不要包含 markdown 代码块标记。

返回格式：
{
  "overall_sentiment": "看多" 或 "看空" 或 "中性",
  "sentiment_score": -100 到 100 的整数（负数看空，正数看多，0中性）,
  "gold_impact": "利好" 或 "利空" 或 "中性",
  "impact_strength": "强" 或 "中" 或 "弱",
  "key_events": [
    {"event": "事件描述", "impact": "利好/利空/中性", "reason": "简短原因"}
  ],
  "market_mood": "恐慌/贪婪/谨慎/乐观/观望 等市场情绪状态",
  "analysis": "综合情绪分析，2-3句话",
  "recommendation": "基于情绪面的建议：加仓/减仓/观望/规避"
}"""


def analyze_sentiment(news_list: list[dict] = None) -> dict:
    """市场情绪分析主函数。

    Args:
        news_list: 新闻列表，为 None 时自动获取。

    Returns:
        dict: LLM 情绪分析结果，包含 news_count 字段。
    """
    # ── 获取新闻 ──
    if news_list is None:
        print("[情绪] 自动获取新闻...")
        news_list = fetch_gold_news_safe(page_size=15)

    if not news_list:
        print("[情绪] 无新闻数据")
        return _default_result(news_count=0)

    # ── 获取当前金价（可选）──
    gold_price = _get_gold_price_safe()

    # ── 格式化新闻 ──
    news_text = format_news_for_llm(news_list, max_items=15)

    # ── 构建 prompt ──
    price_line = f"\n【当前金价】${gold_price:.2f}\n" if gold_price else "\n【当前金价】未获取\n"
    prompt = f"""请分析以下财经新闻对黄金的市场情绪影响：

{price_line}
【新闻列表】
{news_text}

请基于以上新闻内容，分析当前市场情绪状况并返回 JSON 结果。
如果新闻大多与黄金、金融、地缘政治、经济政策相关，要重点分析；如果多数新闻与黄金不直接相关，根据宏观经济面做一般性判断。
"""
    # ── 调用 LLM ──
    print("[情绪] 调用 AI 情绪分析...")
    result = call_llm_json(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_SENTIMENT,
        temperature=0.2,
    )

    if not result:
        result = _default_result(reason="LLM 调用失败", news_count=len(news_list))

    # ── 附加新闻数量 ──
    result["news_count"] = len(news_list)
    if gold_price:
        result["gold_price"] = gold_price

    return result


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  市场情绪分析 Agent - 自测")
    print("=" * 55)

    result = analyze_sentiment()

    # ── 格式化打印 ──
    print("\n" + "=" * 55)
    print("  市场情绪分析结果")
    print("=" * 55)

    sent_map = {"看多": "🟢 看多", "看空": "🔴 看空", "中性": "🟡 中性"}
    impact_map = {"利好": "✅ 利好", "利空": "❌ 利空", "中性": "🟡 中性"}

    print(f"\n  整体情绪: {sent_map.get(result.get('overall_sentiment', '中性'), '中性')}")
    print(f"  情绪得分: {result.get('sentiment_score', 0)}/100")
    print(f"  对黄金影响: {impact_map.get(result.get('gold_impact', '中性'), '中性')}  "
          f"(强度: {result.get('impact_strength', '弱')})")
    print(f"  市场氛围: {result.get('market_mood', '观望')}")

    events = result.get("key_events", [])
    if events:
        print(f"\n  关键事件 ({len(events)} 件):")
        for i, ev in enumerate(events):
            ev_impact = impact_map.get(ev.get("impact", ""), ev.get("impact", ""))
            print(f"    [{i + 1}] {ev.get('event', '?')} → {ev_impact}")
            if ev.get("reason"):
                print(f"        原因: {ev.get('reason')}")
    else:
        print(f"\n  关键事件: 无")

    print(f"\n  分析: {result.get('analysis', '无')}")
    print(f"  建议: {result.get('recommendation', '观望')}")
    print(f"\n  分析新闻: {result.get('news_count', 0)} 条")
    if result.get("gold_price"):
        print(f"  参考金价: ${result['gold_price']:.2f}")
    if result.get("error"):
        print(f"  ⚠️ 错误: {result['error']}")

    print("=" * 55)
