"""
黄金投资智能顾问 - Streamlit Web 界面
多维度分析看板：综合建议、技术图表、情绪分析、基本面、完整报告
"""

import json
import sys
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import streamlit as st

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(__file__))

from src.graph.workflow import run_advisor
from src.data.mt5_data import get_gold_klines, get_current_price, connect_mt5, disconnect_mt5
from src.agents.technical_agent import calculate_indicators
import pandas_ta as ta
from src.trading.executor import (
    open_position, close_position, close_all_positions,
    modify_position, get_positions, get_account_info, calculate_volume,
)
from src.trading.realtime import (
    get_tick_price, get_positions_realtime, get_account_summary,
)
from src.trading.logger import log_trade, get_trade_history, get_trade_stats
from src.trading.risk_guard import check_trade_risk, get_risk_status
from ai_traders.trader_engine import TRADERS, chat_with_trader_stream

TZ_UTC8 = timezone(timedelta(hours=8))

# ── 样式颜色 ──
RED = "#FF4B4B"      # 涨/买入/利好（中国惯例）
GREEN = "#00C853"    # 跌/卖出/利空
YELLOW = "#FFB300"   # 中性/观望
DARK_BG = "#1a1a2e"

# ============================================================
# 页面配置
# ============================================================
st.set_page_config(
    page_title="黄金投资智能顾问",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 自定义 CSS ──
st.markdown("""
<style>
    .big-signal-buy {
        font-size: 42px; font-weight: 900; color: #FF4B4B;
        text-align: center; padding: 12px;
        border: 3px solid #FF4B4B; border-radius: 16px;
        background: rgba(255,75,75,0.08);
    }
    .big-signal-sell {
        font-size: 42px; font-weight: 900; color: #00C853;
        text-align: center; padding: 12px;
        border: 3px solid #00C853; border-radius: 16px;
        background: rgba(0,200,83,0.08);
    }
    .big-signal-hold {
        font-size: 42px; font-weight: 900; color: #FFB300;
        text-align: center; padding: 12px;
        border: 3px solid #FFB300; border-radius: 16px;
        background: rgba(255,179,0,0.08);
    }
    .stButton > button {
        width: 100%; font-size: 18px; padding: 12px;
        background: linear-gradient(135deg, #FF4B4B, #FF8F00);
        color: white; border: none; border-radius: 10px;
        font-weight: 700;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #FF6B6B, #FFA040);
    }

    /* ── 侧边栏字体（缩小到上一版70%，≈默认大小）── */
    [data-testid="stSidebar"] {
        font-size: 1.18rem;
    }
    [data-testid="stSidebar"] h1 { font-size: 2.0rem !important; }
    [data-testid="stSidebar"] h2 { font-size: 1.63rem !important; }
    [data-testid="stSidebar"] h3 { font-size: 1.42rem !important; }
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-baseweb="radio"] label,
    [data-testid="stSidebar"] .stSelectbox label,
    [data-testid="stSidebar"] .stSlider label {
        font-size: 1.24rem !important;
        font-weight: 600;
    }
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {
        font-size: 1.11rem;
    }
    [data-testid="stSidebar"] .stButton > button {
        font-size: 1.21rem;
    }
    /* radio行间距缩小，子分项更紧凑 */
    [data-testid="stSidebar"] [data-baseweb="radio"] {
        row-gap: 0.15rem;
        margin-bottom: 0.15rem;
    }

    /* ── 交易主区域字体放大1.5倍 ── */
    section[data-testid="stMain"] p,
    section[data-testid="stMain"] li,
    section[data-testid="stMain"] label {
        font-size: 1.35rem;
    }
    section[data-testid="stMain"] h1 { font-size: 2.85rem !important; }
    section[data-testid="stMain"] h2 { font-size: 2.33rem !important; }
    section[data-testid="stMain"] h3 { font-size: 2.03rem !important; }

    /* ── 维度得分 hover tooltip ── */
    .score-tip {
        position: relative;
        display: inline-block;
        cursor: help;
        margin-right: 28px;
        font-size: 15px;
    }
    .score-tip .tip-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 20px; height: 20px;
        border-radius: 50%;
        background: rgba(108, 180, 255, 0.2);
        color: #6CB4FF;
        font-size: 13px;
        font-weight: bold;
        margin-left: 6px;
        vertical-align: middle;
    }
    .score-tip .tip-box {
        visibility: hidden;
        opacity: 0;
        transition: opacity 0.2s;
        position: absolute;
        top: 50%;
        left: calc(100% + 12px);
        transform: translateY(-50%);
        background: #232342;
        color: #e8e8e8;
        border: 1px solid #4a4a6a;
        border-radius: 10px;
        padding: 12px 16px;
        font-size: 13px;
        line-height: 1.7;
        max-width: 340px;
        width: max-content;
        z-index: 99999;
        box-shadow: 0 4px 16px rgba(0,0,0,0.5);
        pointer-events: none;
        white-space: normal;
    }
    .score-tip:hover .tip-box {
        visibility: visible;
        opacity: 1;
    }
    .score-tip .tip-box::after {
        content: "";
        position: absolute;
        top: 50%;
        right: 100%;
        transform: translateY(-50%);
        border: 6px solid transparent;
        border-right-color: #232342;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 侧边栏（功能切换 + 专属参数）
# ============================================================
with st.sidebar:
    # 参数默认值（避免 NameError）
    timeframe = "H1"
    kline_count = 500
    risk_profile = "moderate"
    start_btn = False

    # ── 分区1：交易 ──
    st.subheader("交易")
    st.radio(
        "交易子项",
        options=["overview", "market", "manual", "realtime", "positions", "trades"],
        index=0,
        format_func=lambda x: {
            "overview": "综合建议",
            "market": "行情分析",
            "manual": "手动交易",
            "realtime": "实时行情",
            "positions": "持仓管理",
            "trades": "交易历史",
        }[x],
        key="trade_sub_view",
        label_visibility="collapsed",
    )

    # ── 分区2：AI交易员 ──
    st.divider()
    st.subheader("AI交易员")
    ai_trader_view = st.toggle(
        "进入AI交易员",
        value=False,
        key="ai_trader_view",
        help="开启后切换到AI交易员对话界面",
    )
    if ai_trader_view:
        trader_type = st.radio(
            "选择交易员",
            options=["technical", "sentiment", "fundamental"],
            index=0,
            format_func=lambda x: {
                "technical": "📊 技术面交易员",
                "sentiment": "📰 情绪面交易员",
                "fundamental": "🌐 基本面交易员",
            }[x],
            key="ai_trader_type",
        )
        st.caption("💡 可直接向交易员提问，交易员会实时获取数据分析回答。")

    # ── 分区3：设置及主要参数 ──
    st.divider()
    st.subheader("设置及主要参数")
    timeframe = st.selectbox(
        "K线周期",
        options=["M1", "M30", "H1", "H4", "D1"],
        index=2,
        format_func=lambda x: {"M1": "1分钟", "M30": "30分钟", "H1": "1小时", "H4": "4小时", "D1": "日线"}[x],
        help="M1=1分钟, M30=30分钟, H1=1小时, H4=4小时, D1=日线"
    )
    kline_count = st.slider(
        "K线数量",
        min_value=100, max_value=1000, value=500, step=100,
    )
    risk_profile = st.radio(
        "风险偏好",
        options=["conservative", "moderate", "aggressive"],
        index=1,
        format_func=lambda x: {"conservative": "保守", "moderate": "平衡", "aggressive": "激进"}[x],
    )
    st.divider()
    start_btn = st.button("开始分析", width="stretch", type="primary")
    st.caption("本报告由AI生成，仅供参考\n不构成投资建议。投资有风险，入市需谨慎。")

# ============================================================
# 标题
# ============================================================
st.title("黄金投资智能顾问 (XAU/USD)")
st.caption("Powered by LangGraph + DeepSeek + MetaTrader 5  |  多维度分析 · AI 驱动决策")


# ============================================================
# 辅助函数
# ============================================================


def _signal_class(signal: str) -> str:
    return {"buy": "buy", "sell": "sell", "hold": "hold"}.get(signal, "hold")


def _signal_html(signal: str) -> str:
    icon = {"buy": "买入", "sell": "卖出", "hold": "观望"}
    cls = _signal_class(signal)
    return f'<div class="big-signal-{cls}">{icon.get(signal, signal.upper())}</div>'


def _score_gauge(score: float) -> go.Figure:
    """综合得分半圆仪表盘。"""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": " / 100", "font": {"size": 28, "color": "#fff"}},
        gauge={
            "axis": {"range": [-100, 100], "tickcolor": "#aaa"},
            "bar": {"color": YELLOW if abs(score) <= 30 else (RED if score > 0 else GREEN)},
            "steps": [
                {"range": [-100, -30], "color": "rgba(0,200,83,0.15)"},
                {"range": [-30, 30], "color": "rgba(255,179,0,0.15)"},
                {"range": [30, 100], "color": "rgba(255,75,75,0.15)"},
            ],
            "threshold": {
                "line": {"color": "#fff", "width": 3},
                "thickness": 0.8, "value": score,
            },
        },
        domain={"x": [0, 1], "y": [0, 1]},
    ))
    fig.update_layout(
        height=250, margin=dict(l=20, r=20, t=10, b=10),
        paper_bgcolor="rgba(0,0,0,0)", font_color="#fff",
    )
    return fig


# ============================================================
# Tab 1：综合建议
# ============================================================
def render_tab_overview(report: dict, indicators: dict | None):
    """渲染综合建议 Tab。"""
    fs = report.get("final_signal", "hold")
    score = report.get("combined_score", 0)
    conf = report.get("confidence", 0)
    price = report.get("current_price", 0)
    risk = report.get("risk_management", {})
    scores = report.get("individual_scores", {})

    # ── 大信号 ──
    st.markdown(_signal_html(fs), unsafe_allow_html=True)

    # ── 三指标卡片 ──
    c1, c2, c3 = st.columns(3)
    _tip_total = ("<b>综合得分</b><br>"
                  "由技术分析、情绪分析、基本面三维度加权计算，代表AI对金价的整体判断方向与强度<br>"
                  "<span style='color:#FF6B6B'>正值</span>：综合看多金价，利多因素占优<br>"
                  "<span style='color:#4CAF50'>负值</span>：综合看空金价，利空因素占优<br>"
                  "<b>判断标准</b>：&gt;30偏多看涨 | &lt;-30偏空看跌 | -30~30中性观望")
    _tip_conf = ("<b>置信度</b><br>"
                 "AI对当前分析结论的信心程度，基于各维度信号一致性、数据质量与模型收敛度综合评估<br>"
                 "<span style='color:#6CB4FF'>高置信(&gt;70%)</span>：各维度信号方向一致，数据充分，结论可靠<br>"
                 "<span style='color:#FFB300'>中等(40~70%)</span>：部分维度存在分歧，结论具一定参考价值<br>"
                 "<span style='color:#FF6B6B'>低置信(&lt;40%)</span>：各维度信号矛盾较大，建议谨慎参考")

    # 国内金价换算
    _oz_to_gram = 31.1035
    _usd_per_gram = price / _oz_to_gram if price else 0
    _approx_rate = 7.25  # 美元兑人民币近似汇率
    _cny_per_gram = _usd_per_gram * _approx_rate if _usd_per_gram else 0
    _tip_price = (f"<b>当前金价（国际现货 XAU/USD）</b><br>"
                  f"单位：美元/盎司(troy oz)，即1盎司黄金的美元报价<br><br>"
                  f"<b>与国内金价换算</b><br>"
                  f"1盎司 ≈ 31.1035克<br>"
                  f"每克美元价 = ${price:.2f} ÷ 31.1035 ≈ <b>${_usd_per_gram:.2f}/克</b><br>"
                  f"国内金价(元/克) ≈ ${_usd_per_gram:.2f} × {_approx_rate} ≈ <b>¥{_cny_per_gram:.2f}/克</b><br>"
                  f"<span style='color:#aaa;font-size:12px;'>* 汇率为近似值，实际以银行/金店挂牌价为准</span>")

    c1.markdown(
        "<div style='margin-bottom:2px;font-size:14px;color:#aaa;'>"
        "<span class='score-tip'>综合得分<span class='tip-icon'>?</span>"
        "<span class='tip-box'>" + _tip_total + "</span></span>"
        "</div>",
        unsafe_allow_html=True,
    )
    c1.metric("", f"{score:+.1f}", delta=None, label_visibility="collapsed")
    c2.markdown(
        "<div style='margin-bottom:2px;font-size:14px;color:#aaa;'>"
        "<span class='score-tip'>置信度<span class='tip-icon'>?</span>"
        "<span class='tip-box'>" + _tip_conf + "</span></span>"
        "</div>",
        unsafe_allow_html=True,
    )
    c2.metric("", f"{conf}%", delta=None, label_visibility="collapsed")
    c3.markdown(
        "<div style='margin-bottom:2px;font-size:14px;color:#aaa;'>"
        "<span class='score-tip'>当前金价<span class='tip-icon'>?</span>"
        "<span class='tip-box'>" + _tip_price + "</span></span>"
        "</div>",
        unsafe_allow_html=True,
    )
    c3.metric("", f"${price:.2f}" if price else "—", delta=None, label_visibility="collapsed")

    # ── 得分仪表盘 + 柱状图 ──
    col_g, col_b = st.columns([1, 1])
    with col_g:
        st.plotly_chart(_score_gauge(score), width="stretch", key="overview_gauge")
    with col_b:
        # 柱状图数据顺序：技术/情绪/基本面（Plotly水平柱状图首元素在底部，显示从上到下为基本面→情绪分析→技术分析）
        dims = ["技术分析", "情绪分析", "基本面"]
        vals = [scores.get("technical", 0), scores.get("sentiment", 0), scores.get("fundamental", 0)]
        colors_bar = [RED if v > 0 else (GREEN if v < 0 else YELLOW) for v in vals]

        # 维度名 + ? hover tooltip（从左到右：基本面 → 情绪分析 → 技术分析）
        _tip_fund = ("<b>基本面得分</b><br>"
                     "<span style='color:#FF6B6B'>正值(红柱)</span>：基本面利好，美元走弱、地缘风险上升、降息预期升温，利多金价<br>"
                     "<span style='color:#4CAF50'>负值(绿柱)</span>：基本面利空，美元走强、加息预期、经济数据强劲，利空金价<br>"
                     "<b>判断标准</b>：&gt;30基本面偏多 | &lt;-30基本面偏空 | -30~30多空平衡")
        _tip_sent = ("<b>情绪分析得分</b><br>"
                     "<span style='color:#FF6B6B'>正值(红柱)</span>：市场情绪乐观，避险需求上升、利好消息增多，利多金价<br>"
                     "<span style='color:#4CAF50'>负值(绿柱)</span>：市场情绪悲观，风险偏好上升、利空消息增多，利空金价<br>"
                     "<b>判断标准</b>：&gt;30乐观利多 | &lt;-30悲观利空 | -30~30中性")
        _tip_tech = ("<b>技术分析得分</b><br>"
                     "<span style='color:#FF6B6B'>正值(红柱)</span>：看涨信号占优，均线多头排列、RSI偏强、MACD金叉，利多金价<br>"
                     "<span style='color:#4CAF50'>负值(绿柱)</span>：看跌信号占优，均线空头排列、RSI偏弱、MACD死叉，利空金价<br>"
                     "<b>判断标准</b>：&gt;30偏多看涨 | &lt;-30偏空看跌 | -30~30中性观望")
        st.markdown(
            "<div style='margin-bottom:8px;'>"
            "<span class='score-tip'>基本面<span class='tip-icon'>?</span>"
            "<span class='tip-box'>" + _tip_fund + "</span></span>"
            "<span class='score-tip'>情绪分析<span class='tip-icon'>?</span>"
            "<span class='tip-box'>" + _tip_sent + "</span></span>"
            "<span class='score-tip'>技术分析<span class='tip-icon'>?</span>"
            "<span class='tip-box'>" + _tip_tech + "</span></span>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Plotly 柱状图（hovertext 加正负值含义，顺序与 dims 一致：技术/情绪/基本面，显示从上到下为基本面→情绪→技术）
        _hover_texts = [
            f"技术分析 {vals[0]:+.1f}\n正值=利多金价(看涨信号占优)\n负值=利空金价(看跌信号占优)\n>30偏多 | <-30偏空 | -30~30中性",
            f"情绪分析 {vals[1]:+.1f}\n正值=利多金价(市场情绪乐观)\n负值=利空金价(市场情绪悲观)\n>30乐观 | <-30悲观 | -30~30中性",
            f"基本面 {vals[2]:+.1f}\n正值=利多金价(基本面利好)\n负值=利空金价(基本面利空)\n>30偏多 | <-30偏空 | -30~30平衡",
        ]
        bar_fig = go.Figure(go.Bar(
            x=vals, y=dims, orientation="h",
            marker_color=colors_bar,
            text=[f"{v:+.1f}" for v in vals], textposition="outside",
            hovertext=_hover_texts, hoverinfo="text",
        ))
        bar_fig.update_layout(
            title="各维度得分", height=250,
            paper_bgcolor="rgba(0,0,0,0)", font_color="#fff",
            xaxis_range=[-100, 100], xaxis=dict(zeroline=True, zerolinecolor="#555"),
        )
        st.plotly_chart(bar_fig, width="stretch")

        # 颜色图例
        st.markdown(
            "<div style='font-size:13px;color:#aaa;margin-top:4px;'>"
            "<span style='color:#FF4B4B'>红色</span> = 正值(利多/看涨)　"
            "<span style='color:#00C853'>绿色</span> = 负值(利空/看跌)　"
            "<span style='color:#FFB300'>黄色</span> = 接近0(中性)"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── 风控 ──
    st.subheader("风控方案")
    if risk:
        rr = risk.get("risk_reward_ratio", 0)
        rdata = {
            "项目": ["入场价", "止损价", "止盈价", "风险收益比", "建议仓位"],
            "数值": [
                f"${risk.get('entry_price', 0):.2f}",
                f"${risk.get('stop_loss', 0):.2f}",
                f"${risk.get('take_profit', 0):.2f}",
                f"1:{rr:.2f}",
                risk.get("position_size", "—"),
            ],
        }
        st.table(pd.DataFrame(rdata))
        if risk.get("rr_warning") or rr < 1:
            st.warning("风险回报比 < 1，潜在亏损大于盈利，不建议入场！")

    # ── 信号一致性 ──
    st.info(f"信号一致性：{report.get('consensus', '无法判断')}")

    # ── 权重 ──
    w = report.get("weights", {})
    st.caption(
        f"权重分配：技术面 {w.get('technical', 0) * 100:.0f}% | "
        f"情绪面 {w.get('sentiment', 0) * 100:.0f}% | "
        f"基本面 {w.get('fundamental', 0) * 100:.0f}%"
    )


# ============================================================
# Tab 2：技术分析
# ============================================================
def render_tab_technical(kline_df: pd.DataFrame | None, indicators: dict | None, report: dict):
    """渲染技术分析 Tab：技术指标表格 + AI研判（K线图已移至手动交易页面）。"""
    summaries = report.get("agent_summaries", {})
    tech = summaries.get("technical", {})

    st.info("K线图与均线已移至「手动交易」页面，可在此页面边看K线边进行交易。")

    # ── 技术指标表格 ──
    if indicators:
        st.subheader("技术指标")
        ind_data = {
            "指标": [],
            "当前值": [],
            "信号": [],
        }
        ma = indicators.get("ma", {})
        for k, v in ma.items():
            ind_data["指标"].append(k.upper())
            ind_data["当前值"].append(f"{v:.2f}" if v else "—")
            price_val = indicators.get("current_price", 0)
            ind_data["信号"].append(
                "上方" if v and price_val > v else ("下方" if v else "—")
            )
        for ik in ["rsi", "atr"]:
            v = indicators.get(ik)
            ind_data["指标"].append(ik.upper())
            ind_data["当前值"].append(f"{v:.2f}" if v else "—")
            ind_data["信号"].append("—")
        boll = indicators.get("bollinger", {})
        for bk in [("upper", "BOLL上"), ("middle", "BOLL中"), ("lower", "BOLL下")]:
            ind_data["指标"].append(bk[1])
            ind_data["当前值"].append(f"{boll.get(bk[0]):.2f}" if boll.get(bk[0]) else "—")
            ind_data["信号"].append(boll.get("position", "—"))
        kdj = indicators.get("kdj", {})
        for kk in ["k", "d", "j"]:
            ind_data["指标"].append(f"KDJ-{kk.upper()}")
            ind_data["当前值"].append(f"{kdj.get(kk):.2f}" if kdj.get(kk) else "—")
            ind_data["信号"].append("—")

        st.dataframe(pd.DataFrame(ind_data), width="stretch", hide_index=True)

    # ── AI 研判 ──
    if tech.get("summary"):
        st.info(f"AI 研判：{tech['summary']}")


# ============================================================
# Tab 3：情绪分析
# ============================================================
def render_tab_sentiment(report: dict, news: list | None):
    """渲染情绪分析 Tab。"""
    summaries = report.get("agent_summaries", {})
    sent = summaries.get("sentiment", {})

    if not sent:
        st.info("情绪数据暂不可用")
        return

    s_score = sent.get("sentiment_score", 0)

    # ── 情绪仪表盘 ──
    col_g, col_m = st.columns([1, 1])
    with col_g:
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=s_score,
            number={"suffix": " / 100", "font": {"size": 28, "color": "#fff"}},
            gauge={
                "axis": {"range": [-100, 100], "tickcolor": "#aaa"},
                "bar": {"color": YELLOW if abs(s_score) <= 30 else (RED if s_score > 0 else GREEN)},
                "steps": [
                    {"range": [-100, -30], "color": "rgba(0,200,83,0.15)"},
                    {"range": [-30, 30], "color": "rgba(255,179,0,0.15)"},
                    {"range": [30, 100], "color": "rgba(255,75,75,0.15)"},
                ],
            },
            domain={"x": [0, 1], "y": [0, 1]},
        ))
        fig.update_layout(
            height=250, margin=dict(l=20, r=20, t=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)", font_color="#fff",
        )
        st.plotly_chart(fig, width="stretch")

    # ── 情绪摘要 ──
    with col_m:
        st.metric("情绪方向", sent.get("overall_sentiment", "—"))
        st.metric("市场氛围", sent.get("market_mood", "—"))
        st.metric("对金影响", f"{sent.get('gold_impact', '—')} ({sent.get('impact_strength', '—')})")
        st.metric("建议", sent.get("recommendation", "—"))

    # ── 新闻列表 ──
    if news and isinstance(news, list) and len(news) > 0:
        st.subheader("新闻列表")
        # 可展开式新闻列表：点击标题展开查看摘要+原文链接
        for i, item in enumerate(news):
            title = item.get("title", "无标题")
            source = item.get("source", "未知")
            pub = item.get("published_at", "")
            desc = item.get("description", "")
            url = item.get("url", "")
            # 格式化时间：published_at 可能是 Unix 时间戳或字符串
            if pub:
                try:
                    if isinstance(pub, (int, float)) or (isinstance(pub, str) and pub.isdigit()):
                        pub = datetime.fromtimestamp(int(pub), tz=TZ_UTC8).strftime("%Y-%m-%d %H:%M")
                    else:
                        pub = str(pub)
                except Exception:
                    pub = str(pub)
            label = f"[{i+1}] {title}"
            with st.expander(label, expanded=False):
                if desc:
                    st.markdown(f"**摘要**：{desc}")
                else:
                    st.markdown("*暂无摘要*")
                col_a, col_b = st.columns([3, 2])
                with col_a:
                    st.caption(f"来源：{source}")
                with col_b:
                    st.caption(f"时间：{pub}")
                if url:
                    st.markdown(f"[查看原文 →]({url})")

    # ── AI 分析 ──
    if sent.get("analysis"):
        st.info(f"AI 分析：{sent.get('analysis', '暂无')}")


# ============================================================
# Tab 4：基本面分析
# ============================================================
def render_tab_fundamental(report: dict, macro_snapshot: dict | None):
    """渲染基本面分析 Tab。"""
    summaries = report.get("agent_summaries", {})
    fund = summaries.get("fundamental", {})

    if not fund:
        st.info("基本面数据暂不可用")
        return

    # ── 宏观快照 ──
    if macro_snapshot:
        st.subheader("宏观指标快照")
        c1, c2, c3 = st.columns(3)
        ueur = macro_snapshot.get("usd_eur")
        c1.metric("美元指数 (USD/EUR)", f"{ueur:.4f}" if ueur else "—")
        vv = macro_snapshot.get("vix_value")
        c2.metric("VIX 恐慌指数", f"{vv}" if vv else "—")
        ty = macro_snapshot.get("treasury_10y")
        c3.metric("10Y 美债收益率", f"{ty}%" if ty else "获取超时")

    # ── 信号 ──
    c1, c2 = st.columns(2)
    c1.metric("基本面信号", fund.get("signal", "—").upper())
    c2.metric("置信度", f"{fund.get('confidence', 0)}%")

    # ── 分析内容 ──
    if fund.get("macro_environment"):
        st.info(f"宏观环境：{fund['macro_environment']}")
    if fund.get("outlook"):
        st.info(f"AI 展望：{fund['outlook']}")
    if fund.get("recommendation"):
        st.metric("建议", fund["recommendation"])


# ============================================================
# Tab 5：完整报告
# ============================================================
def render_tab_report(report: dict):
    """渲染完整报告 Tab。"""
    st.subheader("完整分析报告")

    # 报告文本
    fs = report.get("final_signal", "hold")
    icon = {"buy": "买入", "sell": "卖出", "hold": "观望"}
    price = report.get("current_price", 0)
    score = report.get("combined_score", 0)
    conf = report.get("confidence", 0)
    risk = report.get("risk_management", {})
    summaries = report.get("agent_summaries", {})

    md = f"""### 黄金投资智能顾问 - 分析报告

---

#### 综合决策
| 项目 | 数值 |
|------|------|
| 最终信号 | {icon.get(fs, fs)} |
| 综合得分 | {score:+.1f} / 100 |
| 置信度 | {conf}% |
| 当前金价 | ${price:.2f} |

---

#### 风控方案
| 项目 | 数值 |
|------|------|
| 入场价 | ${risk.get('entry_price', 0):.2f} |
| 止损价 | ${risk.get('stop_loss', 0):.2f} |
| 止盈价 | ${risk.get('take_profit', 0):.2f} |
| 风险收益比 | 1:{risk.get('risk_reward_ratio', 0):.2f} |
| 建议仓位 | {risk.get('position_size', '—')} |

---

#### 技术分析
- 信号：{summaries.get('technical', {}).get('signal', '—').upper()}
- 趋势：{summaries.get('technical', {}).get('trend', '—')}
- 置信度：{summaries.get('technical', {}).get('confidence', 0)}%

> {summaries.get('technical', {}).get('summary', '暂无')}

#### 情绪分析
- 情绪：{summaries.get('sentiment', {}).get('overall_sentiment', '—')}
- 得分：{summaries.get('sentiment', {}).get('sentiment_score', 0)}
- 氛围：{summaries.get('sentiment', {}).get('market_mood', '—')}

#### 基本面分析
- 信号：{summaries.get('fundamental', {}).get('signal', '—').upper()}
- 展望：{summaries.get('fundamental', {}).get('outlook', '—')}

---

#### 权重
- 技术面 45% | 情绪面 25% | 基本面 30%
- 一致性：{report.get('consensus', '—')}

---

> 免责声明：{report.get('disclaimer', '本报告由AI生成，仅供参考。')}

报告时间：{report.get('timestamp', '—')}
"""
    st.markdown(md)

    # ── 下载按钮 ──
    report_json = json.dumps(_sanitize_report(report), ensure_ascii=False, indent=2, default=str)
    st.download_button(
        label="下载报告 (JSON)",
        data=report_json,
        file_name=f"gold_report_{datetime.now(TZ_UTC8).strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json",
    )


def _sanitize_report(report: dict) -> dict:
    """清洗报告，移除不可序列化的字段。"""
    clean = {}
    for k, v in report.items():
        if v is None:
            clean[k] = None
        elif isinstance(v, (str, int, float, bool, list, dict)):
            if isinstance(v, dict):
                clean[k] = _sanitize_report(v)
            else:
                clean[k] = v
        else:
            clean[k] = str(v)
    return clean


# ============================================================
# 交易确认面板（嵌入综合建议 Tab）
# ============================================================

def render_trade_confirmation(report: dict):
    """AI 信号确认下单面板（半自动模式）。"""
    st.subheader("AI 信号交易确认")

    fs = report.get("final_signal", "hold")
    risk = report.get("risk_management", {})
    conf = report.get("confidence", 0)
    entry = risk.get("entry_price", 0)
    sl = risk.get("stop_loss", 0)
    tp = risk.get("take_profit", 0)
    rr = risk.get("risk_reward_ratio", 0)

    # 只在 buy/sell 时显示交易面板
    if fs not in ("buy", "sell"):
        st.info(f"当前信号为 **观望**，暂不适合交易，请等待明确的买卖信号。")
        return

    # 信号摘要
    dir_cn = "买入" if fs == "buy" else "卖出"
    dir_color = RED if fs == "buy" else GREEN
    st.markdown(
        f'<div style="background:rgba({255 if fs=="buy" else 0},{75 if fs=="buy" else 200},{75 if fs=="buy" else 83},0.1);'
        f'border:2px solid {dir_color};border-radius:12px;padding:16px;text-align:center;">'
        f'<span style="font-size:28px;font-weight:900;color:{dir_color};">AI 建议：{dir_cn}</span><br>'
        f'<span style="font-size:14px;color:#aaa;">置信度 {conf}%  |  入场 ${entry:.2f}  |  止损 ${sl:.2f}  |  止盈 ${tp:.2f}  |  RR 1:{rr:.2f}</span>'
        f'</div>', unsafe_allow_html=True
    )

    # 风险回报比警告
    if rr < 1:
        st.warning(f"风险回报比 1:{rr:.2f} < 1，潜在亏损大于盈利，不建议入场！")

    # 下单参数
    col1, col2, col3 = st.columns(3)
    with col1:
        volume = st.number_input("手数", min_value=0.01, max_value=1.0, value=0.01, step=0.01)
    with col2:
        use_ai_sl = st.checkbox("使用 AI 止损价", value=True)
        sl_input = sl if use_ai_sl else st.number_input("自定义止损", min_value=0.0, value=sl, step=1.0)
    with col3:
        use_ai_tp = st.checkbox("使用 AI 止盈价", value=True)
        tp_input = tp if use_ai_tp else st.number_input("自定义止盈", min_value=0.0, value=tp, step=1.0)

    # 确认下单按钮
    st.markdown(f"**即将执行：{dir_cn} XAUUSD {volume}手 @ 市价  SL={sl_input:.2f}  TP={tp_input:.2f}**")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button(f"确认{dir_cn}", type="primary", key="confirm_trade"):
            with st.spinner("正在执行交易..."):
                result = open_position(
                    symbol="XAUUSD",
                    direction=fs,
                    volume=volume,
                    stop_loss=sl_input if sl_input > 0 else None,
                    take_profit=tp_input if tp_input > 0 else None,
                    comment=f"AI Advisor {fs.upper()} {conf}%",
                )
                # 记录日志
                log_trade(
                    action="open", symbol="XAUUSD", direction=fs,
                    volume=volume, price=entry, ticket=result.get("order_ticket", 0),
                    stop_loss=sl_input, take_profit=tp_input,
                    ai_signal=fs.upper(), confidence=conf,
                    comment=f"AI Advisor {fs.upper()}",
                    success=result.get("success", False),
                    message=result.get("message", ""),
                )
                if result.get("success"):
                    st.success(f"{result['message']}")
                    st.balloons()
                else:
                    st.error(f"下单失败：{result.get('message', '未知错误')}")
                st.rerun()

    with col_btn2:
        if st.button("取消", key="cancel_trade"):
            st.info("已取消交易")


# ============================================================
# Tab 6：实时行情
# ============================================================

def render_tab_realtime():
    """渲染实时行情 Tab。"""
    st.subheader("实时行情")

    # 自动刷新开关
    col_sw, col_info = st.columns([1, 3])
    with col_sw:
        if st.toggle("自动刷新 (3秒)", key="auto_refresh_toggle"):
            st.session_state.auto_refresh = True
            st_autorefresh()
        else:
            st.session_state.auto_refresh = False
    with col_info:
        st.caption("开启后页面每3秒自动刷新报价")

    # 获取实时报价
    tick = get_tick_price("XAUUSD")

    # 报价卡片
    c1, c2, c3, c4 = st.columns(4)
    bid_color = RED if tick.get("change", 0) > 0 else GREEN
    c1.metric("买价 (Bid)", f"${tick['bid']:.2f}")
    c2.metric("卖价 (Ask)", f"${tick['ask']:.2f}")
    c3.metric("点差", f"${tick['spread']:.2f}")
    c4.metric("涨跌幅", f"{tick['change']:+.4f}%", delta_color="normal")

    # 账户信息
    st.divider()
    st.subheader("账户信息")
    summary = get_account_summary()
    if "error" not in summary:
        a1, a2, a3, a4, a5 = st.columns(5)
        a1.metric("余额", f"${summary['balance']:,.2f}")
        a2.metric("净值", f"${summary['equity']:,.2f}")
        a3.metric("浮动盈亏", f"${summary['floating_profit']:+,.2f}")
        a4.metric("持仓数", f"{summary['total_positions']}")
        a5.metric("总手数", f"{summary['total_volume']:.2f}")

        if summary.get("margin_level"):
            st.metric("保证金比例", f"{summary['margin_level']:.1f}%")
    else:
        st.error(f"获取账户信息失败：{summary['error']}")


# ============================================================
# Tab 7：持仓管理
# ============================================================

def render_tab_positions():
    """渲染持仓管理 Tab。"""
    st.subheader("持仓管理")

    # 获取实时持仓
    positions = get_positions_realtime("XAUUSD")

    if not positions:
        st.info("当前无持仓")
        # 一键平仓按钮（即使无持仓也显示，方便操作）
        if st.button("全部平仓", key="close_all_empty"):
            close_all_positions("XAUUSD")
            st.rerun()
        return

    # 持仓表格
    pos_data = []
    for p in positions:
        pos_data.append({
            "订单号": p["ticket"],
            "方向": "买入" if p["type"] == "buy" else "卖出",
            "手数": p["volume"],
            "开仓价": f"${p['price_open']:.2f}",
            "当前价": f"${p['price_current']:.2f}",
            "盈亏($)": f"${p['profit']:+.2f}",
            "盈亏(点)": f"{p['profit_pips']:+.1f}",
            "止损": f"${p['sl']:.2f}" if p['sl'] else "—",
            "止盈": f"${p['tp']:.2f}" if p['tp'] else "—",
            "持仓时长": p["duration"],
            "状态": "盈利" if p["status"] == "盈利" else "亏损" if p["status"] == "亏损" else "持平",
        })

    st.dataframe(pd.DataFrame(pos_data), use_container_width=True, hide_index=True)

    # 总盈亏
    total_profit = sum(p["profit"] for p in positions)
    profit_color = RED if total_profit > 0 else GREEN
    st.markdown(
        f'<div style="text-align:center;padding:12px;border-radius:10px;'
        f'background:rgba({255 if total_profit>0 else 0},{75 if total_profit>0 else 200},{75 if total_profit>0 else 83},0.1);">'
        f'<span style="font-size:24px;font-weight:900;color:{profit_color};">'
        f'总浮动盈亏：${total_profit:+,.2f}</span></div>', unsafe_allow_html=True
    )

    # 操作按钮
    st.divider()
    st.subheader("快速操作")
    col1, col2 = st.columns(2)

    with col1:
        # 单笔平仓
        tickets = [p["ticket"] for p in positions]
        sel_ticket = st.selectbox("选择订单平仓", options=tickets, format_func=lambda t: f"#{t}")
        if st.button("平仓选中", key="close_one"):
            result = close_position(sel_ticket)
            log_trade(
                action="close",
                symbol=result.get("symbol", "XAUUSD"),
                direction=result.get("direction", ""),
                volume=result.get("volume", 0),
                price=result.get("price", 0),
                ticket=sel_ticket,
                success=result.get("success", False),
                message=result.get("message", ""),
                profit=result.get("profit"),
            )
            if result.get("success"):
                st.success(f"{result['message']}")
            else:
                st.error(f"{result.get('message', '平仓失败')}")
            st.rerun()

    with col2:
        # 全部平仓
        if st.button("全部平仓", key="close_all"):
            results = close_all_positions("XAUUSD")
            for r in results:
                log_trade(
                    action="close_all",
                    symbol=r.get("symbol", "XAUUSD"),
                    direction=r.get("direction", ""),
                    volume=r.get("volume", 0),
                    price=r.get("price", 0),
                    ticket=r.get("ticket", 0),
                    success=r.get("success", False),
                    message=r.get("message", ""),
                    profit=r.get("profit"),
                )
            st.success(f"全部平仓完成，共 {len(results)} 笔")
            st.rerun()


# ============================================================
# Tab 8：交易历史
# ============================================================

def render_tab_trades():
    """渲染交易历史 Tab。"""
    st.subheader("交易历史")

    # 交易统计
    stats = get_trade_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总交易次数", stats["total_trades"])
    c2.metric("开仓次数", stats["total_opens"])
    c3.metric("平仓次数", stats["total_closes"])
    c4.metric("胜率", f"{stats['win_rate']:.1f}%")
    profit_val = stats["total_profit"]
    c5.metric("总盈亏", f"${profit_val:+.2f}",
              delta=f"盈{stats['win_count']}/亏{stats['loss_count']}" if stats["win_count"] + stats["loss_count"] > 0 else None)

    st.divider()

    # 交易记录列表
    history = get_trade_history(limit=50)
    if not history:
        st.info("暂无交易记录")
        return

    hist_data = []
    for h in history:
        profit = h.get("profit")
        row = {
            "时间": h.get("timestamp", ""),
            "操作": h.get("action", "").upper(),
            "品种": h.get("symbol", ""),
            "方向": h.get("direction", ""),
            "手数": h.get("volume", 0),
            "价格": f"${h.get('price', 0):.2f}" if h.get("price") else "—",
            "盈亏": f"${profit:+.2f}" if profit is not None else "—",
            "AI信号": h.get("ai_signal", "—"),
            "置信度": f"{h.get('confidence', 0)}%" if h.get("confidence") else "—",
            "状态": "成功" if h.get("success") else "失败",
            "备注": h.get("message", ""),
        }
        hist_data.append(row)

    st.dataframe(pd.DataFrame(hist_data), use_container_width=True, hide_index=True)


# ============================================================
# Tab 9：手动交易
# ============================================================

def _calc_sl_tp_for_dir(direction: str, sl_tp_mode: str,
                        sl_points: int, tp_points: int,
                        sl_price_val, tp_price_val,
                        bid: float, ask: float):
    """根据方向和止损止盈模式，计算实际SL/TP价格和参考价。"""
    ref = ask if direction == "buy" else bid
    if sl_tp_mode == "按价格":
        return sl_price_val, tp_price_val, ref
    elif sl_tp_mode == "按点数":
        if direction == "buy":
            sl = (ask - sl_points * 0.1) if sl_points > 0 else None
            tp = (ask + tp_points * 0.1) if tp_points > 0 else None
        else:
            sl = (bid + sl_points * 0.1) if sl_points > 0 else None
            tp = (bid - tp_points * 0.1) if tp_points > 0 else None
        return sl, tp, ref
    return None, None, ref


def render_tab_manual_trade(kline_df: pd.DataFrame | None = None,
                            indicators: dict | None = None,
                            report: dict | None = None):
    """渲染手动交易 Tab — MT5桌面端风格：左交易面板 + 右K线图 + 底部持仓管理。"""
    summaries = report.get("agent_summaries", {}) if report else {}
    tech = summaries.get("technical", {})

    # ── 获取实时报价 ──
    try:
        tick = get_tick_price("XAUUSD")
        bid = tick.get("bid", 0)
        ask = tick.get("ask", 0)
        spread = tick.get("spread", 0)
    except Exception:
        bid = ask = spread = 0

    if bid == 0 and ask == 0:
        st.error("无法获取实时报价，请确保 MT5 终端已启动并登录")
        return

    # ── 1. 顶部工具栏：品种 + 周期 + 报价 + 刷新 ──
    col_sym, col_tf, col_price, col_rf = st.columns([1, 1, 2, 1])

    with col_sym:
        st.markdown("##### XAUUSD")

    with col_tf:
        chart_tf = st.selectbox(
            "图表周期",
            options=["M1", "M30", "H1", "H4", "D1"],
            format_func=lambda x: {"M1": "1分钟", "M30": "30分钟", "H1": "1小时", "H4": "4小时", "D1": "日线"}[x],
            key="manual_chart_tf",
            label_visibility="collapsed",
        )

    with col_price:
        col_b, col_a, col_s = st.columns(3)
        col_b.metric("Bid", f"${bid:.2f}")
        col_a.metric("Ask", f"${ask:.2f}")
        col_s.metric("点差", f"${spread:.2f}")

    with col_rf:
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            refresh_btn = st.button("刷新", key="manual_refresh_btn", use_container_width=True)
        with col_r2:
            auto_refresh_on = st.toggle("自动刷新", key="manual_auto_toggle")
            if auto_refresh_on:
                st_autorefresh(5000)

    # ── 风控状态条 ──
    try:
        risk_status = get_risk_status()
        status_color = {"正常": "#00C853", "警告": "#FFB300", "危险": "#FF4B4B"}.get(risk_status["status"], "#FFB300")
        ml_str = f'{risk_status["current_margin_level"]:.0f}%' if risk_status["current_margin_level"] else "—"
        st.markdown(
            f'<div style="padding:8px 16px;border-radius:8px;'
            f'background:rgba(255,255,255,0.05);border-left:4px solid {status_color};margin-bottom:8px;">'
            f'<span style="font-size:14px;font-weight:700;color:{status_color};">'
            f'风控: {risk_status["status"]}</span>'
            f' &nbsp;|&nbsp; 持仓 {risk_status["current_positions"]}/{risk_status["max_positions"]} 笔'
            f' &nbsp;|&nbsp; 总手数 {risk_status["current_total_volume"]}/{risk_status["max_total_volume"]}'
            f' &nbsp;|&nbsp; 保证金比例 {ml_str}'
            f' &nbsp;|&nbsp; 今日亏损 ${risk_status["daily_loss"]:.2f}'
            f'</div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass

    # ── 2. 主区域：左交易面板(30%) + 右K线图(70%) ──
    col_panel, col_chart = st.columns([3, 7])

    # ─── 左侧：交易面板 ───
    with col_panel:
        st.markdown("### 下单")

        # 手数
        volume = st.number_input("手数", min_value=0.01, max_value=10.0, value=0.01, step=0.01, key="manual_volume")

        # 止损止盈
        st.markdown("#### 止损 / 止盈")
        sl_tp_mode = st.selectbox(
            "设置方式",
            options=["不设置", "按点数", "按价格"],
            index=0,
            key="manual_sl_tp_mode",
            label_visibility="collapsed",
        )

        sl_price_input = None
        tp_price_input = None
        sl_points_input = 0
        tp_points_input = 0

        if sl_tp_mode == "按价格":
            col_sl, col_tp = st.columns(2)
            with col_sl:
                sl_price_input = st.number_input("止损 ($)", min_value=0.0, value=float(bid), step=1.0, format="%.2f", key="manual_sl_price")
            with col_tp:
                tp_price_input = st.number_input("止盈 ($)", min_value=0.0, value=float(bid), step=1.0, format="%.2f", key="manual_tp_price")

        elif sl_tp_mode == "按点数":
            col_sl, col_tp = st.columns(2)
            with col_sl:
                sl_points_input = st.number_input("止损点数", min_value=0, value=100, step=10, key="manual_sl_points",
                                                   help="1点=$0.1，100点=$10")
            with col_tp:
                tp_points_input = st.number_input("止盈点数", min_value=0, value=200, step=10, key="manual_tp_points",
                                                  help="1点=$0.1，200点=$20")

        # 买入/卖出按钮 — MT5一键面板风格，显示实时价格
        st.markdown("---")
        col_buy, col_sell = st.columns(2)
        with col_buy:
            if st.button(f"买入 Buy\n${ask:.2f}", key="manual_buy_btn",
                         use_container_width=True,
                         help=f"市价买入 {volume}手，参考价 ${ask:.2f}"):
                sl_val, tp_val, ref = _calc_sl_tp_for_dir(
                    "buy", sl_tp_mode, sl_points_input, tp_points_input,
                    sl_price_input, tp_price_input, bid, ask)
                _execute_manual_trade("buy", volume, sl_val, tp_val, ref)

        with col_sell:
            if st.button(f"卖出 Sell\n${bid:.2f}", key="manual_sell_btn",
                         use_container_width=True,
                         help=f"市价卖出 {volume}手，参考价 ${bid:.2f}"):
                sl_val, tp_val, ref = _calc_sl_tp_for_dir(
                    "sell", sl_tp_mode, sl_points_input, tp_points_input,
                    sl_price_input, tp_price_input, bid, ask)
                _execute_manual_trade("sell", volume, sl_val, tp_val, ref)

        # 账户摘要
        st.divider()
        try:
            summary = get_account_summary()
            if "error" not in summary:
                st.markdown("##### 账户")
                col_a1, col_a2 = st.columns(2)
                col_a1.metric("余额", f"${summary['balance']:,.2f}")
                col_a2.metric("净值", f"${summary['equity']:,.2f}")
                col_a3, col_a4 = st.columns(2)
                col_a3.metric("可用保证金", f"${summary['free_margin']:,.2f}")
                col_a4.metric("浮动盈亏", f"${summary['floating_profit']:+,.2f}")
                if summary.get("margin_level"):
                    st.metric("保证金比例", f"{summary['margin_level']:.1f}%")
        except Exception:
            pass

    # ─── 右侧：K线图 ───
    with col_chart:
        st.subheader("K线图与均线")

        # 判断是否需要从MT5重新获取数据
        cached_tf = st.session_state.get("manual_chart_cached_tf")
        cached_df = st.session_state.get("manual_chart_cached_df")
        need_fetch = refresh_btn or (chart_tf != cached_tf) or (cached_df is None)

        if need_fetch:
            if (cached_df is None and not refresh_btn and
                    kline_df is not None and not kline_df.empty and
                    chart_tf == "H1"):
                chart_df = kline_df.copy()
                st.session_state.manual_chart_cached_df = chart_df
                st.session_state.manual_chart_cached_tf = "H1"
            else:
                with st.spinner("正在从MT5获取行情数据..."):
                    try:
                        if connect_mt5():
                            chart_df = get_gold_klines(count=500, timeframe=chart_tf)
                            disconnect_mt5()
                        else:
                            chart_df = cached_df if cached_df is not None else (kline_df if kline_df is not None else pd.DataFrame())
                    except Exception as e:
                        st.error(f"获取行情失败: {e}")
                        chart_df = cached_df if cached_df is not None else (kline_df if kline_df is not None else pd.DataFrame())
                        try:
                            disconnect_mt5()
                        except Exception:
                            pass
                if chart_df is not None and not chart_df.empty:
                    st.session_state.manual_chart_cached_df = chart_df
                    st.session_state.manual_chart_cached_tf = chart_tf
        else:
            chart_df = cached_df

        if chart_df is not None and not chart_df.empty:
            if not pd.api.types.is_datetime64_any_dtype(chart_df["time"]):
                chart_df = chart_df.copy()
                chart_df["time"] = pd.to_datetime(chart_df["time"])

            close = chart_df["close"].astype(float)

            # 布林带
            try:
                bb = ta.bbands(close, length=20, std=2)
                bb_upper = bb.filter(regex="BBU").iloc[:, 0]
                bb_middle = bb.filter(regex="BBM").iloc[:, 0]
                bb_lower = bb.filter(regex="BBL").iloc[:, 0]
            except Exception:
                bb_upper = bb_middle = bb_lower = None

            # MA5 / MA10
            try:
                ma5_series = ta.sma(close, length=5)
                ma10_series = ta.sma(close, length=10)
            except Exception:
                ma5_series = ma10_series = None

            fig = go.Figure()

            # K线 (红涨绿跌 — 中国惯例)
            fig.add_trace(go.Candlestick(
                x=chart_df["time"],
                open=chart_df["open"], high=chart_df["high"],
                low=chart_df["low"], close=chart_df["close"],
                name="XAUUSD",
                increasing_line_color=RED,
                increasing_fillcolor="rgba(255,75,75,0.7)",
                decreasing_line_color=GREEN,
                decreasing_fillcolor="rgba(0,200,83,0.7)",
            ))

            # 布林带
            if bb_upper is not None:
                fig.add_trace(go.Scatter(
                    x=chart_df["time"], y=bb_upper,
                    mode="lines", name="BOLL上轨",
                    line=dict(color="rgba(150,200,255,0.5)", width=1, dash="dot"),
                    hoverinfo="skip",
                ))
                fig.add_trace(go.Scatter(
                    x=chart_df["time"], y=bb_lower,
                    mode="lines", name="BOLL下轨",
                    line=dict(color="rgba(150,200,255,0.5)", width=1, dash="dot"),
                    fill="tonexty", fillcolor="rgba(100,149,237,0.06)",
                    hoverinfo="skip",
                ))
                fig.add_trace(go.Scatter(
                    x=chart_df["time"], y=bb_middle,
                    mode="lines", name="BOLL中轨",
                    line=dict(color="rgba(200,200,200,0.5)", width=1, dash="dash"),
                ))

            # MA5
            if ma5_series is not None:
                fig.add_trace(go.Scatter(
                    x=chart_df["time"], y=ma5_series,
                    mode="lines", name="MA5",
                    line=dict(color="#FFD700", width=1.5),
                ))

            # MA10
            if ma10_series is not None:
                fig.add_trace(go.Scatter(
                    x=chart_df["time"], y=ma10_series,
                    mode="lines", name="MA10",
                    line=dict(color="#FF8C00", width=1.5),
                ))

            # 支撑阻力 (来自AI分析)
            kl = tech.get("key_levels", {}) if isinstance(tech.get("key_levels"), dict) else {}
            for lvl in kl.get("support", []):
                fig.add_hline(y=lvl, line_dash="dash", line_color="rgba(0,200,83,0.6)",
                              annotation_text=f"S:{lvl}")
            for lvl in kl.get("resistance", []):
                fig.add_hline(y=lvl, line_dash="dash", line_color="rgba(255,75,75,0.6)",
                              annotation_text=f"R:{lvl}")

            fig.update_layout(
                template="plotly_dark", height=500,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.1)",
                xaxis_rangeslider_visible=False,
                hovermode="x unified",
                margin=dict(l=20, r=20, t=20, b=20),
                yaxis_title="价格",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )

            st.plotly_chart(fig, width="stretch", key="manual_kline_chart")

            last_close = chart_df["close"].iloc[-1]
            last_time = chart_df["time"].iloc[-1]
            st.caption(f"最后更新: {last_time.strftime('%Y-%m-%d %H:%M')} | 最新收盘: ${last_close:.2f} | 周期: {chart_tf}")
        else:
            st.info("K线数据暂不可用，请确保MT5已连接后点击「刷新」")

    # ── 3. 技术指标表格 ──
    if indicators:
        st.divider()
        st.subheader("技术指标")
        ind_data = {"指标": [], "当前值": [], "信号": []}
        ma = indicators.get("ma", {})
        for k, v in ma.items():
            ind_data["指标"].append(k.upper())
            ind_data["当前值"].append(f"{v:.2f}" if v else "—")
            price_val = indicators.get("current_price", 0)
            ind_data["信号"].append("上方" if v and price_val > v else ("下方" if v else "—"))
        for ik in ["rsi", "atr"]:
            v = indicators.get(ik)
            ind_data["指标"].append(ik.upper())
            ind_data["当前值"].append(f"{v:.2f}" if v else "—")
            ind_data["信号"].append("—")
        boll = indicators.get("bollinger", {})
        for bk in [("upper", "BOLL上"), ("middle", "BOLL中"), ("lower", "BOLL下")]:
            ind_data["指标"].append(bk[1])
            ind_data["当前值"].append(f"{boll.get(bk[0]):.2f}" if boll.get(bk[0]) else "—")
            ind_data["信号"].append(boll.get("position", "—"))
        kdj = indicators.get("kdj", {})
        for kk in ["k", "d", "j"]:
            ind_data["指标"].append(f"KDJ-{kk.upper()}")
            ind_data["当前值"].append(f"{kdj.get(kk):.2f}" if kdj.get(kk) else "—")
            ind_data["信号"].append("—")
        st.dataframe(pd.DataFrame(ind_data), width="stretch", hide_index=True)

    # ── AI 研判 ──
    if tech.get("summary"):
        st.info(f"AI 研判：{tech['summary']}")

    # ── 4. 底部持仓面板 (类似 MT5 Trade 标签页) ──
    st.divider()
    st.subheader("持仓管理")

    positions = get_positions_realtime("XAUUSD")

    if not positions:
        st.info("当前无持仓")
    else:
        pos_data = []
        for p in positions:
            pos_data.append({
                "订单号": p["ticket"],
                "方向": "买入" if p["type"] == "buy" else "卖出",
                "手数": p["volume"],
                "开仓价": f"${p['price_open']:.2f}",
                "当前价": f"${p['price_current']:.2f}",
                "盈亏($)": f"${p['profit']:+.2f}",
                "盈亏(点)": f"{p['profit_pips']:+.1f}",
                "止损": f"${p['sl']:.2f}" if p['sl'] else "—",
                "止盈": f"${p['tp']:.2f}" if p['tp'] else "—",
                "持仓时长": p["duration"],
            })
        st.dataframe(pd.DataFrame(pos_data), use_container_width=True, hide_index=True)

        total_profit = sum(p["profit"] for p in positions)
        profit_color = RED if total_profit > 0 else GREEN
        st.markdown(
            f'<div style="text-align:center;padding:10px;border-radius:8px;'
            f'background:rgba({255 if total_profit>0 else 0},{75 if total_profit>0 else 200},{75 if total_profit>0 else 83},0.1);">'
            f'<span style="font-size:20px;font-weight:700;color:{profit_color};">'
            f'总浮动盈亏：${total_profit:+,.2f}</span></div>',
            unsafe_allow_html=True,
        )

    # 底部操作按钮
    col_op1, col_op2, col_op3 = st.columns(3)
    with col_op1:
        if positions:
            tickets = [p["ticket"] for p in positions]
            sel_ticket = st.selectbox("选择订单平仓", options=tickets,
                                       format_func=lambda t: f"#{t}", key="manual_close_sel")
            if st.button("平仓选中", key="manual_close_one_btn", use_container_width=True):
                result = close_position(sel_ticket)
                log_trade(
                    action="close", symbol=result.get("symbol", "XAUUSD"),
                    direction=result.get("direction", ""), volume=result.get("volume", 0),
                    price=result.get("price", 0), ticket=sel_ticket,
                    success=result.get("success", False), message=result.get("message", ""),
                    profit=result.get("profit"),
                )
                if result.get("success"):
                    st.success(result['message'])
                else:
                    st.error(result.get('message', '平仓失败'))
                st.rerun()

    with col_op2:
        if st.button("全部平仓", key="manual_close_all_btn", use_container_width=True):
            with st.spinner("正在平仓..."):
                results = close_all_positions("XAUUSD")
                success_count = sum(1 for r in results if r.get("success"))
                for r in results:
                    log_trade(
                        action="close_all", symbol=r.get("symbol", "XAUUSD"),
                        direction=r.get("direction", ""), volume=r.get("volume", 0),
                        price=r.get("price", 0), ticket=r.get("ticket", 0),
                        success=r.get("success", False), message=r.get("message", ""),
                        profit=r.get("profit"),
                    )
                if results:
                    st.success(f"平仓完成：{success_count}/{len(results)} 笔成功")
                else:
                    st.info("当前无持仓可平仓")
                st.rerun()

    with col_op3:
        if positions:
            mod_ticket = st.selectbox("选择订单修改", options=[p["ticket"] for p in positions],
                                        format_func=lambda t: f"#{t}", key="manual_mod_sel")
            col_sl2, col_tp2 = st.columns(2)
            with col_sl2:
                new_sl = st.number_input("新止损", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="manual_mod_sl")
            with col_tp2:
                new_tp = st.number_input("新止盈", min_value=0.0, value=0.0, step=1.0, format="%.2f", key="manual_mod_tp")
            if st.button("修改止盈止损", key="manual_modify_btn", use_container_width=True):
                result = modify_position(mod_ticket,
                                         stop_loss=new_sl if new_sl > 0 else None,
                                         take_profit=new_tp if new_tp > 0 else None)
                if result.get("success"):
                    st.success(result['message'])
                else:
                    st.error(result.get('message', '修改失败'))
                st.rerun()


def _execute_manual_trade(direction: str, volume: float, sl_price, tp_price, ref_price: float):
    """执行手动交易并记录日志。下单前自动进行风控检查。"""
    # ── 风控预检 ──
    try:
        from src.trading.realtime import get_tick_price as _gtp
        tick = _gtp("XAUUSD")
        risk = check_trade_risk(
            direction=direction,
            volume=volume,
            bid=tick.get("bid", 0),
            ask=tick.get("ask", 0),
            stop_loss=sl_price,
            take_profit=tp_price,
        )
        if not risk["passed"]:
            st.error(f"风控拒绝：{risk['rejected_reason']}")
            st.caption("以下检查未通过：")
            for c in risk["checks"]:
                if not c["passed"]:
                    st.caption(f"  {c['name']}: {c['detail']}")
            return
        for w in risk.get("warnings", []):
            st.warning(f"{w}")
    except Exception as e:
        st.warning(f"风控预检异常（继续执行）：{e}")

    with st.spinner(f"正在执行{'买入' if direction == 'buy' else '卖出'}订单..."):
        try:
            result = open_position(
                symbol="XAUUSD",
                direction=direction,
                volume=volume,
                stop_loss=sl_price,
                take_profit=tp_price,
                comment=f"Manual {direction.upper()}",
            )
            log_trade(
                action="open", symbol="XAUUSD", direction=direction,
                volume=volume, price=ref_price,
                ticket=result.get("order_ticket", 0),
                stop_loss=sl_price, take_profit=tp_price,
                ai_signal="MANUAL", confidence=0,
                comment="Manual trade",
                success=result.get("success", False),
                message=result.get("message", ""),
            )
            if result.get("success"):
                st.success(f"{'买入' if direction == 'buy' else '卖出'}成功！"
                           f" 订单号: #{result.get('order_ticket', '?')}")
                st.balloons()
            else:
                st.error(f"下单失败：{result.get('message', '未知错误')}")
        except Exception as e:
            st.error(f"交易异常：{e}")
            import traceback
            st.code(traceback.format_exc())


def st_autorefresh(interval: int = 3000):
    """通过 HTML meta refresh 或 st.fragment 实现自动刷新。"""
    try:
        import streamlit.components.v1 as components
        components.html(
            f'<script>setTimeout(function(){{window.location.reload()}},{interval});</script>',
            height=0,
        )
    except Exception:
        pass


# ============================================================
# AI 交易员聊天界面
# ============================================================

def render_ai_trader(trader_type: str):
    """渲染 AI 交易员聊天界面。

    Args:
        trader_type: 交易员类型 ("technical" / "sentiment" / "fundamental")
    """
    trader = TRADERS.get(trader_type)
    if not trader:
        st.error("未知交易员类型")
        return

    # ── 初始化对话历史 ──
    history_key = f"ai_trader_chat_{trader_type}"
    if history_key not in st.session_state:
        st.session_state[history_key] = [
            {"role": "assistant", "content": trader["welcome"]}
        ]

    chat_history = st.session_state[history_key]

    # ── 顶部信息栏 ──
    col_name, col_status, col_clear = st.columns([5, 2, 2])
    with col_name:
        st.markdown(f"### {trader['icon']} {trader['name']}")
        st.caption(trader["desc"])
    with col_status:
        st.markdown("🟢 在线")
    with col_clear:
        if st.button("🗑️ 清空对话", key=f"clear_chat_{trader_type}"):
            st.session_state[history_key] = [
                {"role": "assistant", "content": trader["welcome"]}
            ]
            st.rerun()

    st.divider()

    # ── 对话区域（直接渲染，不使用 container 包裹）──
    for msg in chat_history:
        if msg["role"] == "user":
            with st.chat_message("user", avatar="🧑"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar=trader["icon"]):
                st.markdown(msg["content"])

    # ── 输入框 ──
    user_input = st.chat_input(
        f"向{trader['name']}提问...",
        key=f"chat_input_{trader_type}",
    )

    if user_input:
        # 显示用户消息
        with st.chat_message("user", avatar="🧑"):
            st.markdown(user_input)

        # 流式显示交易员回复
        with st.chat_message("assistant", avatar=trader["icon"]):
            response_placeholder = st.empty()
            full_response = ""
            try:
                for chunk in chat_with_trader_stream(
                    trader_type, user_input, chat_history
                ):
                    full_response += chunk
                    response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)
            except Exception as e:
                full_response = f"抱歉，分析服务出现异常: {e}"
                response_placeholder.markdown(full_response)

        # 添加对话到历史
        chat_history.append({"role": "user", "content": user_input})
        chat_history.append({"role": "assistant", "content": full_response})
        st.session_state[history_key] = chat_history
        st.rerun()


# ============================================================
# 主界面
# ============================================================

def main_ui():
    """主界面入口。"""
    global timeframe, kline_count, risk_profile, start_btn, ai_trader_view

    # ── 初始化 session_state ──
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "kline_data" not in st.session_state:
        st.session_state.kline_data = None
    if "news_data" not in st.session_state:
        st.session_state.news_data = None
    if "macro_snapshot" not in st.session_state:
        st.session_state.macro_snapshot = None
    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = False

    # ── 处理开始分析按钮 ──
    if start_btn:
        with st.spinner("正在采集市场数据（约 1 分钟）..."):
            try:
                # 运行完整工作流
                state = run_advisor()
                report = state.get("final_report", {})
                st.session_state.analysis_result = report

                # 从 state 中提取数据
                st.session_state.news_data = state.get("news_list", [])
                fund_res = state.get("fundamental_result", {})
                st.session_state.macro_snapshot = fund_res.get("macro_snapshot", {})

                # 交易执行结果
                exec_result = state.get("execution_result", {})
                st.session_state.execution_result = exec_result

                # K 线从 state 获取（工作流内部已获取过）
                kdf = state.get("klines")
                if kdf is not None and not kdf.empty:
                    st.session_state.kline_data = kdf

                st.success("分析完成！下方可查看交易子分项结果与下单。")
            except Exception as e:
                st.error(f"分析失败: {e}")
                import traceback
                st.code(traceback.format_exc())

    # ── 根据选中的子分项渲染对应内容 ──

    # ── 结果展示 ──
    report = st.session_state.analysis_result
    kline_df = st.session_state.kline_data
    news = st.session_state.news_data
    macro_sn = st.session_state.macro_snapshot

    # ── 计算指标（用于绘图）──
    indicators = None
    if kline_df is not None and not kline_df.empty:
        try:
            indicators = calculate_indicators(kline_df)
        except Exception:
            pass

    # ── 根据选中的子分项渲染对应内容 ──
    sub_view = st.session_state.get("trade_sub_view", "overview")

    # ── AI 交易员模式：优先渲染聊天界面 ──
    if ai_trader_view:
        trader_type = st.session_state.get("ai_trader_type", "technical")
        render_ai_trader(trader_type)

    elif sub_view == "overview":
        # 综合建议
        if report is None:
            st.info("请先到设置及主要参数点击开始分析启动AI分析")
        else:
            render_tab_overview(report, indicators)
            st.divider()
            render_trade_confirmation(report)

    elif sub_view == "market":
        # 行情分析：技术/情绪/基本面/报告 四块上下平铺
        if report is None:
            st.info("请先到设置及主要参数点击开始分析启动AI分析")
        else:
            st.subheader("技术分析")
            render_tab_technical(kline_df, indicators, report)
            st.divider()
            st.subheader("情绪分析")
            render_tab_sentiment(report, news)
            st.divider()
            st.subheader("基本面分析")
            render_tab_fundamental(report, macro_sn)
            st.divider()
            # render_tab_report 内部已自带「完整分析报告」标题
            render_tab_report(report)

    elif sub_view == "manual":
        # 手动交易（K线图 + 技术指标 + 交易面板 + 持仓管理）
        render_tab_manual_trade(kline_df, indicators, report)

    elif sub_view == "realtime":
        # 实时行情（不依赖AI分析）
        render_tab_realtime()

    elif sub_view == "positions":
        # 持仓管理（不依赖AI分析）
        render_tab_positions()

    elif sub_view == "trades":
        # 交易历史（不依赖AI分析）
        render_tab_trades()


if __name__ == "__main__":
    main_ui()
