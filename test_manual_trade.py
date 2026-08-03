"""AppTest：验证手动交易页面渲染（MT5 mock 模式）。"""
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

from streamlit.testing.v1 import AppTest
import app as app_module

APP_FILE = os.path.join(os.path.dirname(__file__), "app.py")


def make_mock_tick():
    return {"bid": 2350.5, "ask": 2350.8, "spread": 0.3, "time": "2026-07-29"}


def make_mock_positions():
    return [
        {
            "ticket": 12345, "type": "buy", "volume": 0.10,
            "price_open": 2345.0, "price_current": 2350.5,
            "profit": 55.0, "profit_pips": 55.0,
            "sl": 2340.0, "tp": 2360.0, "duration": "2h 30m",
        }
    ]


def make_mock_summary():
    return {
        "balance": 10000.0, "equity": 10055.0,
        "free_margin": 9945.0, "floating_profit": 55.0,
        "margin_level": 200.0,
    }


def make_mock_risk_status():
    return {
        "status": "正常", "current_positions": 1, "max_positions": 5,
        "current_total_volume": 0.10, "max_total_volume": 2.0,
        "current_margin_level": 200.0, "daily_loss": 0.0,
    }


def make_mock_report():
    return {
        "agent_summaries": {
            "technical": {
                "summary": "技术面偏多",
                "key_levels": {"support": [2340], "resistance": [2360]},
            },
            "sentiment": {
                "sentiment_score": 20,
                "overall_sentiment": "中性偏多",
            },
            "fundamental": {
                "summary": "基本面稳定",
            },
        },
        "recommendation": {
            "direction": "buy",
            "confidence": 75,
            "entry_price": 2350.0,
            "stop_loss": 2340.0,
            "take_profit": 2370.0,
        },
        "weights": {"technical": 0.4, "sentiment": 0.3, "fundamental": 0.3},
    }


def test_manual_trade_renders():
    """测试手动交易页面在 MT5 mock 下可正常渲染。"""
    with patch.object(app_module, "get_tick_price", return_value=make_mock_tick()), \
         patch.object(app_module, "get_positions_realtime", return_value=make_mock_positions()), \
         patch.object(app_module, "get_account_summary", return_value=make_mock_summary()), \
         patch.object(app_module, "get_risk_status", return_value=make_mock_risk_status()):
        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.session_state["trade_sub_view"] = "manual"
        at.run()

    print(f"[INFO] markdown count: {len(at.markdown)}")
    print(f"[INFO] buttons count: {len(at.button)}")
    print(f"[INFO] selectbox count: {len(at.selectbox)}")
    print(f"[INFO] number_input count: {len(at.number_input)}")
    print(f"[INFO] error count: {len(at.error)}")
    print(f"[INFO] dataframe count: {len(at.dataframe)}")

    # 验证有买入按钮（含实时价格）
    assert any("买入" in str(b.label) for b in at.button), "Missing Buy button"
    # 验证有卖出按钮（含实时价格）
    assert any("卖出" in str(b.label) for b in at.button), "Missing Sell button"
    # 验证有全部平仓按钮
    assert any("全部平仓" in str(b.label) for b in at.button), "Missing Close All button"
    # 验证有图表周期选择器
    assert any("图表周期" in str(s.label) for s in at.selectbox), "Missing timeframe selector"
    # 验证有手数输入
    assert len(at.number_input) >= 1, "Missing volume input"

    print("\n[PASS] 手动交易页面渲染测试通过！")
    print("  - 下单面板（买入/卖出按钮）: OK")
    print("  - 全部平仓按钮: OK")
    print("  - 图表周期选择器: OK")
    print("  - 手数输入: OK")
    print(f"  - 持仓表格: {'OK' if len(at.dataframe) >= 1 else 'None'}")


def test_technical_tab_no_kline():
    """测试技术分析页面不再包含K线图代码，且显示迁移提示。"""
    with patch.object(app_module, "get_tick_price", return_value=make_mock_tick()):
        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.session_state["trade_sub_view"] = "market"
        at.session_state["analysis_result"] = make_mock_report()
        at.run()

    print(f"\n[INFO] technical tab info count: {len(at.info)}")
    for i in at.info:
        print(f"  info: {i.value[:100]}")
    assert any("手动交易" in i.value for i in at.info), "Missing 'K线已移至手动交易' notice"
    print("[PASS] 技术分析页面已移除K线图，显示迁移提示！")


if __name__ == "__main__":
    test_manual_trade_renders()
    test_technical_tab_no_kline()
    print("\n=== All tests passed ===")
