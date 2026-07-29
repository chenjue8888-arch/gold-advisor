"""
LLM 连接器模块
通过 DeepSeek API（兼容 OpenAI 接口）驱动 AI 分析。
"""

import json
import re
import sys
import time
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from config import CONFIG

# ── 常量 ─────────────────────────────────────────────────
DEEPSEEK_API_KEY = CONFIG.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def get_llm(temperature: float = 0.3, model: str = DEFAULT_MODEL) -> ChatOpenAI:
    """创建 DeepSeek ChatOpenAI 实例。

    Args:
        temperature: 采样温度，默认 0.3（金融分析需低温度保证稳定性）。
        model: 模型名，默认 "deepseek-chat"（DeepSeek V3）。

    Returns:
        ChatOpenAI: 已配置好的 LLM 实例。
    """
    if not DEEPSEEK_API_KEY:
        print("[LLM] ⚠️ DEEPSEEK_API_KEY 未配置，请检查 .env 文件")

    return ChatOpenAI(
        model=model,
        openai_api_key=DEEPSEEK_API_KEY,
        openai_api_base=DEEPSEEK_BASE_URL,
        temperature=temperature,
    )


def _build_messages(prompt: str, system_prompt: str = "") -> list:
    """构建 LangChain 消息列表。"""
    msgs = []
    if system_prompt:
        msgs.append(SystemMessage(content=system_prompt))
    msgs.append(HumanMessage(content=prompt))
    return msgs


def call_llm(prompt: str, system_prompt: str = "", temperature: float = 0.3) -> str:
    """便捷函数：发送 prompt 到 LLM 并获取文本回复。

    Args:
        prompt: 用户提示词。
        system_prompt: 系统提示词。
        temperature: 采样温度。

    Returns:
        str: LLM 回复文本，失败返回空字符串。
    """
    if not DEEPSEEK_API_KEY:
        print("[LLM] ❌ DEEPSEEK_API_KEY 未配置，无法调用")
        return ""

    try:
        print("[LLM] 正在调用 DeepSeek...")
        start = time.time()

        llm = get_llm(temperature=temperature)
        messages = _build_messages(prompt, system_prompt)
        response = llm.invoke(messages)

        elapsed = time.time() - start
        content = response.content if hasattr(response, "content") else str(response)

        # 打印 token 信息
        usage = ""
        if hasattr(response, "response_metadata"):
            meta = response.response_metadata
            token_info = meta.get("token_usage", {})
            if token_info:
                usage = f"，tokens: in={token_info.get('prompt_tokens', '?')} / out={token_info.get('completion_tokens', '?')}"

        print(f"[LLM] 响应耗时: {elapsed:.2f}秒{usage}")
        return content.strip()

    except Exception as e:
        _handle_llm_error(e)
        return ""


def call_llm_json(prompt: str, system_prompt: str = "", temperature: float = 0.1) -> dict:
    """调用 LLM 并要求返回 JSON 格式结果。

    自动在 system_prompt 末尾追加 JSON 格式要求，
    并尝试解析返回的 JSON，支持 markdown 代码块清洗。

    Args:
        prompt: 用户提示词。
        system_prompt: 系统提示词（会自动追加 JSON 格式要求）。
        temperature: 采样温度，默认 0.1（结构化输出需低随机性）。

    Returns:
        dict: 解析后的 JSON 字典，失败返回空 dict。
    """
    if not DEEPSEEK_API_KEY:
        print("[LLM] ❌ DEEPSEEK_API_KEY 未配置，无法调用")
        return {}

    # 追加 JSON 格式要求
    json_hint = "\n\n你的回复必须是合法的 JSON 格式，不要包含 markdown 代码块标记（如 ```json）。"
    full_system = system_prompt + json_hint

    raw = call_llm(prompt=prompt, system_prompt=full_system, temperature=temperature)
    if not raw:
        return {}

    # ── 解析 JSON ──
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # ── 尝试从 markdown 代码块中提取 ──
    for pattern in [
        r"```(?:json)?\s*\n?(.*?)```",   # ```json ... ```
        r"\{.*?\}",                        # { ... }
        r"\[.*?\]",                        # [ ... ]
    ]:
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1) if match.lastindex else match.group(0))
            except (json.JSONDecodeError, IndexError):
                continue

    # ── 彻底失败，打印原始回复供调试 ──
    print(f"[LLM] ⚠️ JSON 解析失败，原始回复:\n{raw[:500]}")
    return {}


def _handle_llm_error(e: Exception):
    """打印友好的 LLM 错误信息。"""
    error_str = str(e)

    if "AuthenticationError" in type(e).__name__ or "401" in error_str or "Invalid API Key" in error_str:
        print(f"[LLM] ❌ API Key 无效或已过期，请检查 .env 中的 DEEPSEEK_API_KEY")
        print(f"[LLM]    错误详情: {error_str[:200]}")
    elif "RateLimitError" in type(e).__name__ or "429" in error_str or "insufficient" in error_str.lower():
        print(f"[LLM] ❌ API 额度不足或频率超限，请检查 DeepSeek 账户余额")
        print(f"[LLM]    错误详情: {error_str[:200]}")
    elif "APITimeoutError" in type(e).__name__ or "timeout" in error_str.lower():
        print(f"[LLM] ❌ API 调用超时，请检查网络连接或稍后重试")
        print(f"[LLM]    错误详情: {error_str[:200]}")
    elif "APIConnectionError" in type(e).__name__ or "Connection" in type(e).__name__:
        print(f"[LLM] ❌ API 连接失败，请检查网络和 https://api.deepseek.com 是否可达")
        print(f"[LLM]    错误详情: {error_str[:200]}")
    else:
        print(f"[LLM] ❌ 调用失败: {error_str[:300]}")


# ── 测试代码 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  LLM 模块 - 自测")
    print("=" * 55)

    # ── 测试 1：文本回复 ──
    print("\n📝 测试 1：文本问答")
    print("-" * 40)
    result1 = call_llm(
        system_prompt="你是一个黄金投资分析师助手。",
        prompt="当前金价4050美元，VIX为19，请用一句话简要分析。",
    )
    print(f"回复: {result1}")

    # ── 测试 2：JSON 结构化输出 ──
    print("\n📊 测试 2：JSON 结构化输出")
    print("-" * 40)
    result2 = call_llm_json(
        system_prompt="你是黄金分析师。",
        prompt=(
            "当前金价4050美元，VIX为19，10年期美债收益率4.69%。"
            "请分析并返回如下JSON："
            '{"signal": "buy/sell/hold", "reason": "分析理由", "confidence": 0-100}'
        ),
    )
    if result2:
        print(f"信号: {result2.get('signal', '?')}")
        print(f"理由: {result2.get('reason', '?')}")
        print(f"信心: {result2.get('confidence', '?')}")
    else:
        print("未能获取有效的 JSON 回复")

    print("\n" + "=" * 55)
    print("  LLM 模块测试完成")
    print("=" * 55)
