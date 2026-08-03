"""AppTest: 验证 AI 交易员聊天界面渲染。"""
import sys, os
sys.path.insert(0, os.path.dirname("D:/gold-advisor"))
os.chdir("D:/gold-advisor")

from unittest.mock import patch, MagicMock
from streamlit.testing.v1 import AppTest

print("=" * 55)
print("  AI 交易员页面 - AppTest")
print("=" * 55)

# ── 测试 1: 默认状态（未开启AI交易员）──
print("\n📋 测试 1: 默认状态（未开启AI交易员）")
print("-" * 40)
try:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.run()
    # 应该看到综合建议页面的提示
    has_info = any("分析" in str(i.value) for i in at.info)
    print(f"  info 元素数: {len(at.info)}")
    print(f"  包含分析提示: {has_info}")
    print(f"  错误数: {len(at.exception)}")
    for e in at.exception:
        print(f"  ERROR: {e}")
    if len(at.exception) == 0:
        print("  [PASS] 默认状态渲染正常")
    else:
        print("  [FAIL] 存在异常")
except Exception as e:
    print(f"  [FAIL] 异常: {e}")

# ── 测试 2: 开启AI交易员 ──
print("\n📋 测试 2: 开启AI交易员（技术面）")
print("-" * 40)
try:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["ai_trader_view"] = True
    at.session_state["ai_trader_type"] = "technical"
    at.run()

    # 检查是否有交易员标题
    markdown_texts = [str(m.value) for m in at.markdown]
    has_trader_name = any("技术面交易员" in t for t in markdown_texts)
    has_online = any("在线" in t for t in markdown_texts)

    # 检查是否有欢迎消息（ChatMessage 用 .markdown 访问内容）
    has_welcome = any("技术面交易员" in str(c) for c in at.chat_message)

    # 检查是否有清空按钮
    has_clear_btn = any("清空" in str(b.label) for b in at.button)

    # 检查错误
    errors = at.exception

    print(f"  markdown 元素数: {len(at.markdown)}")
    print(f"  chat_message 元素数: {len(at.chat_message)}")
    print(f"  button 元素数: {len(at.button)}")
    print(f"  包含交易员名称: {has_trader_name}")
    print(f"  包含在线状态: {has_online}")
    print(f"  包含欢迎消息: {has_welcome}")
    print(f"  包含清空按钮: {has_clear_btn}")
    print(f"  错误数: {len(errors)}")
    for e in errors:
        print(f"  ERROR: {e}")

    if len(errors) == 0 and has_trader_name:
        print("  [PASS] AI交易员页面渲染正常")
    else:
        print("  [FAIL] 存在问题")
except Exception as e:
    print(f"  [FAIL] 异常: {e}")
    import traceback
    traceback.print_exc()

# ── 测试 3: 切换到情绪面交易员 ──
print("\n📋 测试 3: 切换到情绪面交易员")
print("-" * 40)
try:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["ai_trader_view"] = True
    at.session_state["ai_trader_type"] = "sentiment"
    at.run()

    markdown_texts = [str(m.value) for m in at.markdown]
    has_sentiment = any("情绪面交易员" in t for t in markdown_texts)
    errors = at.exception

    print(f"  包含情绪面交易员: {has_sentiment}")
    print(f"  错误数: {len(errors)}")
    for e in errors:
        print(f"  ERROR: {e}")

    if len(errors) == 0 and has_sentiment:
        print("  [PASS] 情绪面交易员渲染正常")
    else:
        print("  [FAIL] 存在问题")
except Exception as e:
    print(f"  [FAIL] 异常: {e}")

# ── 测试 4: 切换到基本面交易员 ──
print("\n📋 测试 4: 切换到基本面交易员")
print("-" * 40)
try:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["ai_trader_view"] = True
    at.session_state["ai_trader_type"] = "fundamental"
    at.run()

    markdown_texts = [str(m.value) for m in at.markdown]
    has_fundamental = any("基本面交易员" in t for t in markdown_texts)
    errors = at.exception

    print(f"  包含基本面交易员: {has_fundamental}")
    print(f"  错误数: {len(errors)}")
    for e in errors:
        print(f"  ERROR: {e}")

    if len(errors) == 0 and has_fundamental:
        print("  [PASS] 基本面交易员渲染正常")
    else:
        print("  [FAIL] 存在问题")
except Exception as e:
    print(f"  [FAIL] 异常: {e}")

# ── 测试 5: 对话历史独立性 ──
print("\n📋 测试 5: 对话历史独立性")
print("-" * 40)
try:
    at = AppTest.from_file("app.py", default_timeout=30)
    at.session_state["ai_trader_view"] = True
    at.session_state["ai_trader_type"] = "technical"
    # 预设技术面历史
    at.session_state["ai_trader_chat_technical"] = [
        {"role": "assistant", "content": "技术面欢迎消息"},
        {"role": "user", "content": "RSI怎么看？"},
        {"role": "assistant", "content": "RSI分析..."},
    ]
    at.run()

    # 检查历史消息是否渲染
    chat_msgs = at.chat_message
    print(f"  chat_message 数量: {len(chat_msgs)}")
    print(f"  错误数: {len(at.exception)}")

    if len(chat_msgs) >= 3 and len(at.exception) == 0:
        print("  [PASS] 对话历史渲染正常")
    else:
        print("  [FAIL] 对话历史渲染异常")
except Exception as e:
    print(f"  [FAIL] 异常: {e}")

print("\n" + "=" * 55)
print("  测试完成")
print("=" * 55)
