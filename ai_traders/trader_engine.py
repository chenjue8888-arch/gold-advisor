"""
AI 交易员引擎模块
负责加载交易员 Prompt、实时获取数据、调用 LLM 生成回答。
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 确保项目根目录在 sys.path 中
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.utils.llm import call_llm, get_llm
from src.data.mt5_data import get_gold_klines, connect_mt5, disconnect_mt5
from src.agents.technical_agent import calculate_indicators
from src.data.news_data import fetch_gold_news, fetch_gold_news_cn
from src.data.macro_data import get_macro_summary

TZ_UTC8 = timezone(timedelta(hours=8))

# ── 交易员定义 ──────────────────────────────────────────────
TRADERS = {
    "technical": {
        "name": "技术面交易员",
        "icon": "📊",
        "desc": "精通K线形态、技术指标（RSI/MACD/布林带/均线），专注技术面分析",
        "md_file": "technical_trader.md",
        "welcome": "您好！我是技术面交易员，专注于K线形态和技术指标分析。您可以问我任何关于黄金技术面的问题，例如「当前技术面怎么看？」「RSI和MACD信号矛盾怎么判断？」",
    },
    "sentiment": {
        "name": "情绪面交易员",
        "icon": "📰",
        "desc": "擅长新闻舆情分析、市场情绪判断，结合实时新闻给出情绪面分析",
        "md_file": "sentiment_trader.md",
        "welcome": "您好！我是情绪面交易员，专注于市场情绪与新闻舆情分析。您可以问我「现在市场情绪对黄金是利好还是利空？」「最近的新闻会对金价有什么影响？」",
    },
    "fundamental": {
        "name": "基本面交易员",
        "icon": "🌐",
        "desc": "精通宏观经济指标、央行政策、国际格局，专注基本面分析",
        "md_file": "fundamental_trader.md",
        "welcome": "您好！我是基本面交易员，专注于宏观经济与基本面分析。您可以问我「当前宏观经济环境对黄金有什么影响？」「美元指数和美债收益率变化怎么看？」",
    },
}


# ── Prompt 加载 ──────────────────────────────────────────────

def load_trader_prompt(trader_type: str) -> str:
    """从 MD 文件加载交易员的 System Prompt。

    Args:
        trader_type: 交易员类型 ("technical" / "sentiment" / "fundamental")

    Returns:
        str: System Prompt 文本。若文件不存在则返回默认 prompt。
    """
    trader = TRADERS.get(trader_type)
    if not trader:
        return "你是一名专业的黄金投资分析师。"

    md_path = Path(__file__).resolve().parent / trader["md_file"]
    if not md_path.exists():
        print(f"[Trader] ⚠️ MD 文件不存在: {md_path}")
        return f"你是{trader['name']}，专注于黄金投资分析。"

    try:
        content = md_path.read_text(encoding="utf-8")

        # 提取 ``` 代码块中的 System Prompt
        import re
        match = re.search(r"```\n(.*?)\n```", content, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 如果没有代码块，返回整个内容
        return content
    except Exception as e:
        print(f"[Trader] ⚠️ 加载 MD 文件失败: {e}")
        return f"你是{trader['name']}，专注于黄金投资分析。"


# ── 数据获取 ──────────────────────────────────────────────────

def _fetch_technical_data() -> str:
    """获取技术面数据并格式化为文本。"""
    parts = []
    parts.append(f"数据获取时间: {datetime.now(TZ_UTC8).strftime('%Y-%m-%d %H:%M:%S')}")

    # 获取K线数据
    kline_df = None
    try:
        if connect_mt5():
            kline_df = get_gold_klines(count=200, timeframe="H1")
            disconnect_mt5()
    except Exception as e:
        parts.append(f"[警告] MT5连接失败: {e}")
        try:
            disconnect_mt5()
        except Exception:
            pass

    if kline_df is not None and not kline_df.empty:
        parts.append("\n── K线数据（最近5根H1）──")
        recent = kline_df.tail(5)
        for _, row in recent.iterrows():
            t = row["time"]
            if hasattr(t, "strftime"):
                t = t.strftime("%m-%d %H:%M")
            parts.append(
                f"  {t} | O:{row['open']:.2f} H:{row['high']:.2f} "
                f"L:{row['low']:.2f} C:{row['close']:.2f}"
            )

        # 计算技术指标
        try:
            indicators = calculate_indicators(kline_df)
            if indicators:
                parts.append("\n── 技术指标（当前值）──")
                parts.append(f"  当前价格: ${indicators.get('current_price', 'N/A')}")

                ma = indicators.get("ma", {})
                parts.append(
                    f"  MA5: {ma.get('ma5', 'N/A')} | MA10: {ma.get('ma10', 'N/A')} | "
                    f"MA20: {ma.get('ma20', 'N/A')} | MA60: {ma.get('ma60', 'N/A')}"
                )

                ema = indicators.get("ema", {})
                parts.append(f"  EMA12: {ema.get('ema12', 'N/A')} | EMA26: {ema.get('ema26', 'N/A')}")

                parts.append(f"  RSI(14): {indicators.get('rsi', 'N/A')}")

                macd = indicators.get("macd", {})
                parts.append(
                    f"  MACD: {macd.get('macd', 'N/A')} | "
                    f"Signal: {macd.get('signal', 'N/A')} | "
                    f"Histogram: {macd.get('histogram', 'N/A')}"
                )

                kdj = indicators.get("kdj", {})
                parts.append(
                    f"  KDJ: K={kdj.get('k', 'N/A')} D={kdj.get('d', 'N/A')} J={kdj.get('j', 'N/A')}"
                )

                boll = indicators.get("boll", {})
                parts.append(
                    f"  BOLL: 上轨={boll.get('upper', 'N/A')} 中轨={boll.get('middle', 'N/A')} "
                    f"下轨={boll.get('lower', 'N/A')}"
                )
        except Exception as e:
            parts.append(f"[警告] 技术指标计算失败: {e}")
    else:
        parts.append("[警告] 无法获取K线数据，MT5可能未连接")

    return "\n".join(parts)


def _fetch_sentiment_data() -> str:
    """获取情绪面数据并格式化为文本。"""
    parts = []
    parts.append(f"数据获取时间: {datetime.now(TZ_UTC8).strftime('%Y-%m-%d %H:%M:%S')}")

    # 获取中文新闻
    try:
        cn_news = fetch_gold_news_cn(count=10)
        if cn_news:
            parts.append(f"\n── 中文黄金新闻（共{len(cn_news)}条）──")
            for i, news in enumerate(cn_news[:10], 1):
                title = news.get("title", "无标题")
                source = news.get("source", "未知来源")
                pub_time = news.get("published_at", "")
                desc = news.get("description", "")
                parts.append(f"  {i}. [{source}] {title}")
                if pub_time:
                    parts.append(f"     时间: {pub_time}")
                if desc:
                    parts.append(f"     摘要: {desc[:150]}")
        else:
            parts.append("[信息] 暂无中文新闻数据")
    except Exception as e:
        parts.append(f"[警告] 中文新闻获取失败: {e}")

    # 获取英文新闻
    try:
        en_news = fetch_gold_news(count=10)
        if en_news:
            parts.append(f"\n── 英文黄金新闻（共{len(en_news)}条）──")
            for i, news in enumerate(en_news[:10], 1):
                title = news.get("title", "No title")
                source = news.get("source", "Unknown")
                pub_time = news.get("published_at", "")
                desc = news.get("description", "")
                parts.append(f"  {i}. [{source}] {title}")
                if pub_time:
                    parts.append(f"     Time: {pub_time}")
                if desc:
                    parts.append(f"     Summary: {desc[:150]}")
        else:
            parts.append("[信息] 暂无英文新闻数据")
    except Exception as e:
        parts.append(f"[警告] 英文新闻获取失败: {e}")

    return "\n".join(parts)


def _fetch_fundamental_data() -> str:
    """获取基本面数据并格式化为文本。"""
    parts = []
    parts.append(f"数据获取时间: {datetime.now(TZ_UTC8).strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        macro = get_macro_summary()

        # DXY
        dxy = macro.get("dxy")
        if dxy is not None and not dxy.empty:
            latest = dxy.iloc[-1]
            parts.append("\n── 美元指数（DXY）──")
            parts.append(f"  最新值: {latest.get('Close', latest.get('close', 'N/A'))}")
            if len(dxy) >= 2:
                prev = dxy.iloc[-2]
                curr_val = float(latest.get("Close", latest.get("close", 0)) or 0)
                prev_val = float(prev.get("Close", prev.get("close", 0)) or 0)
                if prev_val > 0:
                    change = ((curr_val - prev_val) / prev_val) * 100
                    parts.append(f"  日变化: {change:+.2f}%")
            parts.append(f"  近{len(dxy)}日数据可用")
        else:
            parts.append("[警告] 美元指数数据获取失败")

        # VIX
        vix = macro.get("vix", {})
        if vix:
            parts.append("\n── VIX恐慌指数 ──")
            parts.append(f"  当前值: {vix.get('current', vix.get('value', 'N/A'))}")
            parts.append(f"  状态: {vix.get('status', vix.get('level', 'N/A'))}")
        else:
            parts.append("[警告] VIX数据获取失败")

        # 10Y Treasury
        treasury = macro.get("treasury_10y", {})
        if treasury:
            parts.append("\n── 10年期美债收益率 ──")
            parts.append(f"  当前值: {treasury.get('current', treasury.get('yield', 'N/A'))}%")
            parts.append(f"  趋势: {treasury.get('trend', 'N/A')}")
        else:
            parts.append("[警告] 美债收益率数据获取失败")

        parts.append(f"\n宏观数据更新时间: {macro.get('timestamp', 'N/A')}")

    except Exception as e:
        parts.append(f"[警告] 宏观数据获取失败: {e}")

    return "\n".join(parts)


# ── 数据获取调度 ──────────────────────────────────────────────

_FETCHERS = {
    "technical": _fetch_technical_data,
    "sentiment": _fetch_sentiment_data,
    "fundamental": _fetch_fundamental_data,
}


def fetch_trader_data(trader_type: str) -> str:
    """根据交易员类型获取对应的实时数据。

    Args:
        trader_type: 交易员类型

    Returns:
        str: 格式化的数据文本
    """
    fetcher = _FETCHERS.get(trader_type)
    if not fetcher:
        return "[错误] 未知交易员类型"
    return fetcher()


# ── LLM 对话 ──────────────────────────────────────────────────

def chat_with_trader(
    trader_type: str,
    user_message: str,
    chat_history: list[dict] | None = None,
) -> str:
    """与交易员对话，获取回复。

    Args:
        trader_type: 交易员类型 ("technical" / "sentiment" / "fundamental")
        user_message: 用户消息
        chat_history: 对话历史列表，每个元素 {"role": "user"/"assistant", "content": "..."}

    Returns:
        str: 交易员回复文本
    """
    # 1. 加载 System Prompt
    system_prompt = load_trader_prompt(trader_type)

    # 2. 获取实时数据
    print(f"[Trader] 正在获取{TRADERS[trader_type]['name']}数据...")
    data_text = fetch_trader_data(trader_type)

    # 3. 拼接完整 prompt
    full_prompt = f"""【实时市场数据】
{data_text}

【对话历史】
"""
    if chat_history:
        for msg in chat_history[-10:]:  # 保留最近10轮
            role = "用户" if msg.get("role") == "user" else "交易员"
            full_prompt += f"{role}: {msg.get('content', '')}\n"
    else:
        full_prompt += "（无历史对话）\n"

    full_prompt += f"""
【用户最新提问】
{user_message}

请根据以上实时市场数据，结合你的专业领域，回答用户的问题。"""

    # 4. 调用 LLM
    print(f"[Trader] 正在调用 LLM...")
    start = time.time()
    response = call_llm(
        prompt=full_prompt,
        system_prompt=system_prompt,
        temperature=0.4,
    )
    elapsed = time.time() - start
    print(f"[Trader] LLM 响应耗时: {elapsed:.2f}秒")

    return response if response else "抱歉，分析服务暂时不可用，请稍后重试。"


def chat_with_trader_stream(
    trader_type: str,
    user_message: str,
    chat_history: list[dict] | None = None,
):
    """与交易员对话，流式返回回复。

    使用 LangChain 的 stream 方法逐 token 返回。

    Args:
        trader_type: 交易员类型
        user_message: 用户消息
        chat_history: 对话历史

    Yields:
        str: 回复文本片段
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    # 1. 加载 System Prompt
    system_prompt = load_trader_prompt(trader_type)

    # 2. 获取实时数据
    print(f"[Trader] 正在获取{TRADERS[trader_type]['name']}数据...")
    data_text = fetch_trader_data(trader_type)

    # 3. 构建消息列表
    messages = [SystemMessage(content=system_prompt)]

    # 添加数据上下文作为系统消息
    data_context = f"【实时市场数据】\n{data_text}"
    messages.append(SystemMessage(content=data_context))

    # 添加对话历史
    if chat_history:
        for msg in chat_history[-10:]:
            if msg.get("role") == "user":
                messages.append(HumanMessage(content=msg.get("content", "")))
            else:
                from langchain_core.messages import AIMessage
                messages.append(AIMessage(content=msg.get("content", "")))

    # 添加当前用户消息
    messages.append(HumanMessage(content=user_message))

    # 4. 流式调用 LLM
    print(f"[Trader] 正在调用 LLM (stream)...")
    start = time.time()
    try:
        llm = get_llm(temperature=0.4)
        for chunk in llm.stream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content
        elapsed = time.time() - start
        print(f"[Trader] LLM 流式响应完成，耗时: {elapsed:.2f}秒")
    except Exception as e:
        elapsed = time.time() - start
        print(f"[Trader] ❌ LLM 调用失败 ({elapsed:.2f}秒): {e}")
        yield f"抱歉，分析服务暂时不可用: {e}"


# ── 自测 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  AI 交易员引擎 - 自测")
    print("=" * 55)

    # 测试 prompt 加载
    print("\n📝 测试 1: Prompt 加载")
    for t_type in TRADERS:
        prompt = load_trader_prompt(t_type)
        print(f"\n[{TRADERS[t_type]['name']}]")
        print(f"  Prompt 长度: {len(prompt)} 字符")
        print(f"  前100字: {prompt[:100]}...")

    # 测试数据获取
    print("\n\n📊 测试 2: 数据获取")
    for t_type in TRADERS:
        print(f"\n[{TRADERS[t_type]['name']}]")
        data = fetch_trader_data(t_type)
        print(data[:500])
        print("...")

    print("\n" + "=" * 55)
    print("  测试完成")
    print("=" * 55)
