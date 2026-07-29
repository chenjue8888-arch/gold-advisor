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
from src.data.mt5_data import get_gold_klines, get_current_price
from src.agents.technical_agent import calculate_indicators

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
    page_icon="🏆",
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
</style>
""", unsafe_allow_html=True)

# ============================================================
# 标题
# ============================================================
col1, col2 = st.columns([1, 5])
with col1:
    st.markdown("### 🏆")
with col2:
    st.title("黄金投资智能顾问 (XAU/USD)")
st.caption("Powered by LangGraph + DeepSeek + MetaTrader 5  |  多维度分析 · AI 驱动决策")

# ============================================================
# 侧边栏
# ============================================================
with st.sidebar:
    st.header("⚙️ 分析参数")

    timeframe = st.selectbox(
        "K线周期",
        options=["H1", "H4", "D1"],
        index=0,
        help="H1=1小时, H4=4小时, D1=日线"
    )
    kline_count = st.slider(
        "K线数量",
        min_value=100, max_value=1000, value=500, step=100,
    )
    risk_profile = st.radio(
        "风险偏好",
        options=["conservative", "moderate", "aggressive"],
        index=1,
        format_func=lambda x: {"conservative": "🛡️ 保守", "moderate": "⚖️ 平衡", "aggressive": "🚀 激进"}[x],
    )

    st.divider()

    start_btn = st.button("🚀 开始分析", width="stretch", type="primary")

    st.divider()
    st.caption("⚠️ 本报告由AI生成，仅供参考\n不构成投资建议。投资有风险，入市需谨慎。")


# ============================================================
# 辅助函数
# ============================================================


def _signal_class(signal: str) -> str:
    return {"buy": "buy", "sell": "sell", "hold": "hold"}.get(signal, "hold")


def _signal_html(signal: str) -> str:
    icon = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "🟡 观望"}
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
    c1.metric("📈 综合得分", f"{score:+.1f}", delta=None)
    c2.metric("🎯 置信度", f"{conf}%", delta=None)
    c3.metric("💰 当前金价", f"${price:.2f}" if price else "—")

    # ── 得分仪表盘 + 柱状图 ──
    col_g, col_b = st.columns([1, 1])
    with col_g:
        st.plotly_chart(_score_gauge(score), width="stretch", key="overview_gauge")
    with col_b:
        dims = ["技术分析", "情绪分析", "基本面"]
        vals = [scores.get("technical", 0), scores.get("sentiment", 0), scores.get("fundamental", 0)]
        colors_bar = [RED if v > 0 else (GREEN if v < 0 else YELLOW) for v in vals]
        bar_fig = go.Figure(go.Bar(
            x=vals, y=dims, orientation="h",
            marker_color=colors_bar,
            text=[f"{v:+.1f}" for v in vals], textposition="outside",
        ))
        bar_fig.update_layout(
            title="各维度得分", height=250,
            paper_bgcolor="rgba(0,0,0,0)", font_color="#fff",
            xaxis_range=[-100, 100], xaxis=dict(zeroline=True, zerolinecolor="#555"),
        )
        st.plotly_chart(bar_fig, width="stretch")

    # ── 风控 ──
    st.subheader("⚖️ 风控方案")
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
            st.warning("⚠️ 风险回报比 < 1，潜在亏损大于盈利，不建议入场！")

    # ── 信号一致性 ──
    st.info(f"🔗 信号一致性：{report.get('consensus', '无法判断')}")

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
    """渲染技术分析 Tab。"""
    summaries = report.get("agent_summaries", {})
    tech = summaries.get("technical", {})

    # ── K 线图 ──
    st.subheader("📈 K线图与均线")
    if kline_df is not None and not kline_df.empty:
        # 确保 time 列是 datetime 类型
        if not pd.api.types.is_datetime64_any_dtype(kline_df["time"]):
            kline_df = kline_df.copy()
            kline_df["time"] = pd.to_datetime(kline_df["time"])

        fig = make_subplots(
            rows=3, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.04,
            row_heights=[0.5, 0.25, 0.25],
            subplot_titles=("XAU/USD 价格", "RSI (14)", "MACD"),
        )

        # K线
        fig.add_trace(go.Candlestick(
            x=kline_df["time"],
            open=kline_df["open"], high=kline_df["high"],
            low=kline_df["low"], close=kline_df["close"],
            name="XAUUSD",
            increasing_line_color=GREEN, decreasing_line_color=RED,
        ), row=1, col=1)

        # 均线
        if indicators:
            ma = indicators.get("ma", {})
            for key, color in [("ma5", "#FFD700"), ("ma10", "#FF8C00"),
                                ("ma20", "#00BFFF"), ("ma60", "#FF69B4")]:
                val = ma.get(key)
                if val is not None:
                    target_time = kline_df["time"].iloc[-1]
                    fig.add_hline(y=val, line_dash="dot", line_color=color,
                                  annotation_text=key.upper(), row=1, col=1)

        # 支撑阻力
        kl = tech.get("key_levels", {}) if isinstance(tech.get("key_levels"), dict) else {}
        for lvl in kl.get("support", []):
            fig.add_hline(y=lvl, line_dash="dash", line_color="rgba(0,200,83,0.5)",
                          annotation_text=f"S:{lvl}", row=1, col=1)
        for lvl in kl.get("resistance", []):
            fig.add_hline(y=lvl, line_dash="dash", line_color="rgba(255,75,75,0.5)",
                          annotation_text=f"R:{lvl}", row=1, col=1)

        # RSI
        rsi_val = indicators.get("rsi") if indicators else None
        if rsi_val is not None:
            fig.add_trace(go.Scatter(
                x=[kline_df["time"].iloc[-1]], y=[rsi_val],
                mode="markers+text", text=[f"{rsi_val:.1f}"],
                textposition="top center", marker=dict(size=12, color=YELLOW),
                name="RSI", showlegend=False,
            ), row=2, col=1)
        fig.add_hline(y=70, line_dash="dash", line_color="rgba(255,75,75,0.5)", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="rgba(0,200,83,0.5)", row=2, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color="#555", row=2, col=1)

        # MACD
        macd = indicators.get("macd", {}) if indicators else {}
        if macd.get("macd") is not None:
            x_end = kline_df["time"].iloc[-1]
            fig.add_trace(go.Bar(
                x=[x_end], y=[macd.get("histogram", 0)],
                marker_color=RED if macd.get("histogram", 0) < 0 else GREEN,
                name="MACD Hist", showlegend=False,
            ), row=3, col=1)

        fig.update_layout(
            template="plotly_dark", height=700,
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0.1)",
            xaxis_rangeslider_visible=False,
            hovermode="x unified",
            margin=dict(l=20, r=20, t=40, b=20),
        )
        fig.update_yaxes(title_text="价格", row=1, col=1)
        fig.update_yaxes(title_text="RSI", range=[0, 100], row=2, col=1)
        fig.update_yaxes(title_text="MACD", row=3, col=1)

        st.plotly_chart(fig, width="stretch")
    else:
        st.info("K线数据暂不可用，请确保MT5已连接")

    # ── 技术指标表格 ──
    if indicators:
        st.subheader("📊 技术指标")
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
                "🟢 上方" if v and price_val > v else ("🔴 下方" if v else "—")
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
        st.info(f"🤖 AI 研判：{tech['summary']}")


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
        st.subheader("📋 新闻列表")
        try:
            news_df = pd.DataFrame(news)
            cols = ["title", "source", "published_at"]
            display_cols = [c for c in cols if c in news_df.columns]
            if display_cols:
                st.dataframe(news_df[display_cols], width="stretch", hide_index=True)
        except Exception:
            st.text(f"新闻数量：{len(news)} 条（格式不兼容表格展示）")

    # ── AI 分析 ──
    if sent.get("analysis"):
        st.info(f"🤖 AI 分析：{sent.get('analysis', '暂无')}")


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
        st.subheader("📊 宏观指标快照")
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
        st.info(f"🌍 宏观环境：{fund['macro_environment']}")
    if fund.get("outlook"):
        st.info(f"🔮 AI 展望：{fund['outlook']}")
    if fund.get("recommendation"):
        st.metric("建议", fund["recommendation"])


# ============================================================
# Tab 5：完整报告
# ============================================================
def render_tab_report(report: dict):
    """渲染完整报告 Tab。"""
    st.subheader("📋 完整分析报告")

    # 报告文本
    fs = report.get("final_signal", "hold")
    icon = {"buy": "🟢 买入", "sell": "🔴 卖出", "hold": "🟡 观望"}
    price = report.get("current_price", 0)
    score = report.get("combined_score", 0)
    conf = report.get("confidence", 0)
    risk = report.get("risk_management", {})
    summaries = report.get("agent_summaries", {})

    md = f"""### 🏆 黄金投资智能顾问 - 分析报告

---

#### 📊 综合决策
| 项目 | 数值 |
|------|------|
| 最终信号 | {icon.get(fs, fs)} |
| 综合得分 | {score:+.1f} / 100 |
| 置信度 | {conf}% |
| 当前金价 | ${price:.2f} |

---

#### ⚖️ 风控方案
| 项目 | 数值 |
|------|------|
| 入场价 | ${risk.get('entry_price', 0):.2f} |
| 止损价 | ${risk.get('stop_loss', 0):.2f} |
| 止盈价 | ${risk.get('take_profit', 0):.2f} |
| 风险收益比 | 1:{risk.get('risk_reward_ratio', 0):.2f} |
| 建议仓位 | {risk.get('position_size', '—')} |

---

#### 📈 技术分析
- 信号：{summaries.get('technical', {}).get('signal', '—').upper()}
- 趋势：{summaries.get('technical', {}).get('trend', '—')}
- 置信度：{summaries.get('technical', {}).get('confidence', 0)}%

> {summaries.get('technical', {}).get('summary', '暂无')}

#### 📰 情绪分析
- 情绪：{summaries.get('sentiment', {}).get('overall_sentiment', '—')}
- 得分：{summaries.get('sentiment', {}).get('sentiment_score', 0)}
- 氛围：{summaries.get('sentiment', {}).get('market_mood', '—')}

#### 🏦 基本面分析
- 信号：{summaries.get('fundamental', {}).get('signal', '—').upper()}
- 展望：{summaries.get('fundamental', {}).get('outlook', '—')}

---

#### ⚖️ 权重
- 技术面 45% | 情绪面 25% | 基本面 30%
- 一致性：{report.get('consensus', '—')}

---

> ⚠️ 免责声明：{report.get('disclaimer', '本报告由AI生成，仅供参考。')}

🕐 报告时间：{report.get('timestamp', '—')}
"""
    st.markdown(md)

    # ── 下载按钮 ──
    report_json = json.dumps(_sanitize_report(report), ensure_ascii=False, indent=2, default=str)
    st.download_button(
        label="📥 下载报告 (JSON)",
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
# 主界面
# ============================================================

def main_ui():
    """主界面入口。"""
    global timeframe, kline_count, risk_profile, start_btn

    # ── 初始化 session_state ──
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "kline_data" not in st.session_state:
        st.session_state.kline_data = None
    if "news_data" not in st.session_state:
        st.session_state.news_data = None
    if "macro_snapshot" not in st.session_state:
        st.session_state.macro_snapshot = None

    # ── 点击分析按钮 ──
    if start_btn:
        with st.spinner("📡 正在采集市场数据（约 1 分钟）..."):
            try:
                # 运行完整工作流
                state = run_advisor()
                report = state.get("final_report", {})
                st.session_state.analysis_result = report

                # 从 state 中提取数据
                st.session_state.news_data = state.get("news_list", [])
                fund_res = state.get("fundamental_result", {})
                st.session_state.macro_snapshot = fund_res.get("macro_snapshot", {})

                # K 线从 state 获取（工作流内部已获取过）
                kdf = state.get("klines")
                if kdf is not None and not kdf.empty:
                    st.session_state.kline_data = kdf

                st.success("✅ 分析完成！")
                st.rerun()

            except Exception as e:
                st.error(f"❌ 分析失败: {e}")
                import traceback
                st.code(traceback.format_exc())

    # ── 结果展示 ──
    report = st.session_state.analysis_result
    kline_df = st.session_state.kline_data
    news = st.session_state.news_data
    macro_sn = st.session_state.macro_snapshot

    if report is None:
        st.info("👈 请点击左侧「🚀 开始分析」按钮启动分析")
        # 展示空状态占位
        return

    # ── 计算指标（用于绘图）──
    indicators = None
    if kline_df is not None and not kline_df.empty:
        try:
            indicators = calculate_indicators(kline_df)
        except Exception:
            pass

    # ── Tabs ──
    tabs = st.tabs([
        "📊 综合建议",
        "📈 技术分析",
        "📰 情绪分析",
        "🏦 基本面分析",
        "📋 分析报告",
    ])

    with tabs[0]:
        render_tab_overview(report, indicators)

    with tabs[1]:
        render_tab_technical(kline_df, indicators, report)

    with tabs[2]:
        render_tab_sentiment(report, news)

    with tabs[3]:
        render_tab_fundamental(report, macro_sn)

    with tabs[4]:
        render_tab_report(report)


if __name__ == "__main__":
    main_ui()
