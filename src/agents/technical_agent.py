"""
技术分析 Agent
通过技术指标分析黄金走势，结合 LLM 给出买卖信号。
"""

import sys
from pathlib import Path

import pandas as pd
import pandas_ta as ta

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.data.mt5_data import (
    connect_mt5,
    get_gold_klines,
    get_current_price,
    disconnect_mt5,
)
from src.utils.llm import call_llm_json

# ── 指标计算 ─────────────────────────────────────────────


def _safe_round(val, ndigits: int = 2):
    """安全四舍五入，处理 None/NaN。"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return round(float(val), ndigits)


def calculate_indicators(df: pd.DataFrame) -> dict:
    """计算技术指标并返回当前值。

    Args:
        df: K 线 DataFrame（列：time, open, high, low, close, tick_volume）。

    Returns:
        dict: 当前各技术指标值。
    """
    result = {}

    if df.empty:
        print("[技术] K 线数据为空，无法计算指标")
        return result

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    current_price = close.iloc[-1]
    result["current_price"] = round(float(current_price), 2)

    # ── MA 均线 ──
    try:
        for p in (5, 10, 20, 60):
            ma_series = ta.sma(close, length=p)
            val = _safe_round(ma_series.iloc[-1])
            result.setdefault("ma", {})[f"ma{p}"] = val
        print(f"[技术] MA: MA5={result['ma']['ma5']}, MA10={result['ma']['ma10']}, "
              f"MA20={result['ma']['ma20']}, MA60={result['ma']['ma60']}")
    except Exception as e:
        print(f"[技术] MA 计算失败: {e}")
        result.setdefault("ma", {})
        for p in (5, 10, 20, 60):
            result["ma"][f"ma{p}"] = None

    # ── EMA 指数均线 ──
    try:
        for p in (12, 26):
            ema_series = ta.ema(close, length=p)
            val = _safe_round(ema_series.iloc[-1])
            result.setdefault("ema", {})[f"ema{p}"] = val
        print(f"[技术] EMA: EMA12={result['ema']['ema12']}, EMA26={result['ema']['ema26']}")
    except Exception as e:
        print(f"[技术] EMA 计算失败: {e}")
        result.setdefault("ema", {"ema12": None, "ema26": None})

    # ── RSI ──
    try:
        rsi_series = ta.rsi(close, length=14)
        result["rsi"] = _safe_round(rsi_series.iloc[-1])
        print(f"[技术] RSI: {result['rsi']}")
    except Exception as e:
        print(f"[技术] RSI 计算失败: {e}")
        result["rsi"] = None

    # ── MACD ──
    try:
        macd_df = ta.macd(close, fast=12, slow=26, signal=9)
        result["macd"] = {
            "macd": _safe_round(macd_df.iloc[-1].get("MACD_12_26_9")),
            "signal": _safe_round(macd_df.iloc[-1].get("MACDs_12_26_9")),
            "histogram": _safe_round(macd_df.iloc[-1].get("MACDh_12_26_9")),
        }
        print(f"[技术] MACD: {result['macd']}")
    except Exception as e:
        print(f"[技术] MACD 计算失败: {e}")
        result["macd"] = {"macd": None, "signal": None, "histogram": None}

    # ── KDJ ──
    try:
        stoch = ta.stoch(high, low, close, k=9, d=3, smooth_k=3)
        # pandas_ta stoch 返回列: STOCHk_9_3_3, STOCHd_9_3_3
        k_col = [c for c in stoch.columns if "STOCHk" in c][0]
        d_col = [c for c in stoch.columns if "STOCHd" in c][0]
        k_val = _safe_round(stoch.iloc[-1][k_col])
        d_val = _safe_round(stoch.iloc[-1][d_col])
        j_val = _safe_round(3 * k_val - 2 * d_val) if k_val is not None and d_val is not None else None
        result["kdj"] = {"k": k_val, "d": d_val, "j": j_val}
        print(f"[技术] KDJ: {result['kdj']}")
    except Exception as e:
        print(f"[技术] KDJ 计算失败: {e}")
        result["kdj"] = {"k": None, "d": None, "j": None}

    # ── 布林带 ──
    try:
        bb = ta.bbands(close, length=20, std=2)
        upper_col = [c for c in bb.columns if "BBU" in c][0]
        mid_col = [c for c in bb.columns if "BBM" in c][0]
        lower_col = [c for c in bb.columns if "BBL" in c][0]
        upper = _safe_round(bb.iloc[-1][upper_col])
        middle = _safe_round(bb.iloc[-1][mid_col])
        lower = _safe_round(bb.iloc[-1][lower_col])

        # 判断价格在布林带中的位置
        if upper and lower and upper != lower:
            pct = (current_price - lower) / (upper - lower)
            if pct > 0.9:
                position = "上轨附近"
            elif pct > 0.6:
                position = "中轨上方"
            elif pct > 0.4:
                position = "中轨附近"
            elif pct > 0.1:
                position = "中轨下方"
            else:
                position = "下轨附近"
        else:
            position = "未知"

        result["bollinger"] = {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "position": position,
        }
        print(f"[技术] Bollinger: 上={upper}, 中={middle}, 下={lower}, 位置={position}")
    except Exception as e:
        print(f"[技术] Bollinger 计算失败: {e}")
        result["bollinger"] = {"upper": None, "middle": None, "lower": None, "position": "未知"}

    # ── ATR ──
    try:
        atr_series = ta.atr(high, low, close, length=14)
        result["atr"] = _safe_round(atr_series.iloc[-1])
        print(f"[技术] ATR: {result['atr']}")
    except Exception as e:
        print(f"[技术] ATR 计算失败: {e}")
        result["atr"] = None

    # ── 价格 vs 均线 ──
    ma = result.get("ma", {})
    for key, label in [("ma5", "MA5"), ("ma20", "MA20"), ("ma60", "MA60")]:
        ma_val = ma.get(key)
        if ma_val is not None:
            result[f"price_vs_{key}"] = "上方" if current_price > ma_val else "下方"
        else:
            result[f"price_vs_{key}"] = "未知"

    return result


# ── 均线排列分析 ──
def _ma_arrangement(indicators: dict) -> str:
    """判断均线排列状态。"""
    ma = indicators.get("ma", {})
    vals = [ma.get(f"ma{p}") for p in (5, 10, 20, 60)]
    if any(v is None for v in vals):
        return "数据不足"
    # 多头排列：MA5 > MA10 > MA20 > MA60
    if vals[0] > vals[1] > vals[2] > vals[3]:  # type: ignore[operator]
        return "多头排列"
    # 空头排列：MA5 < MA10 < MA20 < MA60
    if vals[0] < vals[1] < vals[2] < vals[3]:  # type: ignore[operator]
        return "空头排列"
    return "均线纠缠"


# ── RSI 状态 ──
def _rsi_status(rsi) -> str:
    if rsi is None:
        return "未知"
    if rsi > 70:
        return "超买区（可能回调）"
    elif rsi < 30:
        return "超卖区（可能反弹）"
    elif rsi > 50:
        return "偏强"
    else:
        return "偏弱"


# ── MACD 状态 ──
def _macd_status(macd: dict) -> str:
    d = macd.get("macd")
    s = macd.get("signal")
    h = macd.get("histogram")
    if d is None or s is None:
        return "未知"
    if h is not None:
        if h > 0:
            return "金叉状态（MACD 在信号线上方）"
        else:
            return "死叉状态（MACD 在信号线下方）"
    return "未知"


# ── KDJ 状态 ──
def _kdj_status(kdj: dict) -> str:
    k, d, j = kdj.get("k"), kdj.get("d"), kdj.get("j")
    if k is None:
        return "未知"
    if k > 80:
        return "超买区"
    elif k < 20:
        return "超卖区"
    elif k > d:
        return "K 线上穿 D 线（偏多）"
    else:
        return "K 线下穿 D 线（偏空）"


# ── 构建 LLM Prompt ──
def _build_technical_prompt(indicators: dict, df: pd.DataFrame) -> str:
    """构建技术分析 prompt。"""
    ma_arr = _ma_arrangement(indicators)
    rsi_stat = _rsi_status(indicators.get("rsi"))
    macd_stat = _macd_status(indicators.get("macd", {}))
    kdj_stat = _kdj_status(indicators.get("kdj", {}))
    bb = indicators.get("bollinger", {})

    prompt = f"""请基于以下黄金技术指标数据进行专业分析：

【价格数据】
- 当前金价: ${indicators.get('current_price', '?')}
- 价格相对 MA5: {indicators.get('price_vs_ma5', '?')}
- 价格相对 MA20: {indicators.get('price_vs_ma20', '?')}
- 价格相对 MA60: {indicators.get('price_vs_ma60', '?')}

【均线系统】
- MA5: {indicators.get('ma', {}).get('ma5', '?')}
- MA10: {indicators.get('ma', {}).get('ma10', '?')}
- MA20: {indicators.get('ma', {}).get('ma20', '?')}
- MA60: {indicators.get('ma', {}).get('ma60', '?')}
- 均线排列: {ma_arr}
- EMA12: {indicators.get('ema', {}).get('ema12', '?')}
- EMA26: {indicators.get('ema', {}).get('ema26', '?')}

【震荡指标】
- RSI(14): {indicators.get('rsi', '?')} — {rsi_stat}
- MACD: {indicators.get('macd', {})}
- MACD 状态: {macd_stat}
- KDJ: {indicators.get('kdj', {})}
- KDJ 状态: {kdj_stat}

【波动指标】
- 布林带上轨: {bb.get('upper', '?')}
- 布林带中轨: {bb.get('middle', '?')}
- 布林带下轨: {bb.get('lower', '?')}
- 价格位置: {bb.get('position', '?')}
- ATR(14): {indicators.get('atr', '?')}

请根据以上数据返回严格的 JSON 分析结果。
"""
    return prompt


SYSTEM_PROMPT_TECHNICAL = """你是一位专业的黄金技术分析师。基于以下技术指标数据，分析黄金的短期走势。

请严格按照 JSON 格式返回分析结果，不要包含 markdown 代码块标记。

返回格式：
{
  "signal": "buy" 或 "sell" 或 "hold",
  "confidence": 0-100 的整数,
  "entry_price": 建议入场价位（数字）,
  "stop_loss": 建议止损价位（数字）,
  "take_profit": 建议止盈价位（数字）,
  "trend": "上升趋势" 或 "下降趋势" 或 "震荡",
  "indicators_summary": "技术指标综合研判，2-3句话",
  "key_levels": {
    "support": [支撑位1, 支撑位2],
    "resistance": [阻力位1, 阻力位2]
  },
  "risks": ["风险点1", "风险点2"]
}"""


# ── 主分析函数 ────────────────────────────────────────────
def analyze_technical(df: pd.DataFrame = None) -> dict:
    """技术分析主函数：计算指标 + LLM 分析。

    Args:
        df: K 线 DataFrame，为 None 时自动连接 MT5 获取。

    Returns:
        dict: LLM 分析结果，包含 raw_indicators 字段。
    """
    # ── 获取数据 ──
    should_disconnect = False
    if df is None:
        print("[技术] 自动获取 MT5 数据...")
        try:
            if not connect_mt5():
                print("[技术] MT5 连接失败")
                return _default_result("MT5 连接失败")
            should_disconnect = True
            df = get_gold_klines(count=500, timeframe="H1")
        except Exception as e:
            print(f"[技术] MT5 异常: {e}")
            return _default_result(f"MT5 异常: {e}")
        finally:
            if should_disconnect:
                try:
                    disconnect_mt5()
                except Exception:
                    pass

    if df is None or df.empty:
        print("[技术] K 线数据为空")
        return _default_result("K 线数据为空")

    print(f"[技术] 数据规模: {len(df)} 根 K 线, "
          f"范围: {df['time'].iloc[0]} ~ {df['time'].iloc[-1]}")

    # ── 计算指标 ──
    print("\n" + "-" * 40)
    print("[技术] 计算技术指标...")
    print("-" * 40)
    indicators = calculate_indicators(df)

    # ── 调用 LLM ──
    print("\n" + "-" * 40)
    print("[技术] 调用 AI 分析...")
    print("-" * 40)

    prompt = _build_technical_prompt(indicators, df)
    result = call_llm_json(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT_TECHNICAL,
        temperature=0.1,
    )

    if not result:
        result = _default_result("LLM 调用失败")

    # ── 附加原始指标 ──
    result["raw_indicators"] = indicators
    return result


def _default_result(reason: str) -> dict:
    """返回默认的 hold 结果。"""
    return {
        "signal": "hold",
        "confidence": 0,
        "entry_price": 0,
        "stop_loss": 0,
        "take_profit": 0,
        "trend": "未知",
        "indicators_summary": f"技术分析不可用（{reason}）",
        "key_levels": {"support": [], "resistance": []},
        "risks": [],
        "error": reason,
        "raw_indicators": {},
    }


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  技术分析 Agent - 自测")
    print("=" * 55)

    try:
        if not connect_mt5():
            print("[测试] MT5 连接失败，测试终止")
            sys.exit(1)

        print("\n获取 K 线数据...")
        df = get_gold_klines(count=500, timeframe="H1")
        disconnect_mt5()

        if df.empty:
            print("[测试] 未获取到 K 线数据")
            sys.exit(1)

        print("\n开始技术分析...")
        result = analyze_technical(df)

        # ── 格式化打印 ──
        print("\n" + "=" * 55)
        print("  技术分析结果")
        print("=" * 55)

        signal_icon = {"buy": "🟢 BUY", "sell": "🔴 SELL", "hold": "🟡 HOLD"}
        print(f"\n  信号: {signal_icon.get(result.get('signal', 'hold'), 'HOLD')}")
        print(f"  置信度: {result.get('confidence', 0)}/100")
        print(f"  趋势: {result.get('trend', '未知')}")
        print(f"  入场: ${result.get('entry_price', 0):.2f}  "
              f"| 止损: ${result.get('stop_loss', 0):.2f}  "
              f"| 止盈: ${result.get('take_profit', 0):.2f}")
        print(f"  研判: {result.get('indicators_summary', '无')}")

        kl = result.get("key_levels", {})
        print(f"  支撑位: {kl.get('support', [])}")
        print(f"  阻力位: {kl.get('resistance', [])}")
        print(f"  风险: {result.get('risks', [])}")

        if result.get("error"):
            print(f"  ⚠️ 错误: {result['error']}")

        print("=" * 55)

    except Exception as e:
        print(f"[测试] 异常: {e}")
    finally:
        try:
            disconnect_mt5()
        except Exception:
            pass
