"""项目配置模块：集中管理 API 密钥、MT5 连接参数及默认交易品种。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 从项目根目录加载 .env 文件
load_dotenv(Path(__file__).resolve().parent / ".env")

CONFIG = {
    # DeepSeek API 密钥，用于 LangChain / LangGraph 大语言模型调用
    "DEEPSEEK_API_KEY": os.getenv("DEEPSEEK_API_KEY", ""),

    # MetaTrader 5 账户登录号
    "MT5_LOGIN": os.getenv("MT5_LOGIN", ""),
    # MetaTrader 5 账户密码
    "MT5_PASSWORD": os.getenv("MT5_PASSWORD", ""),
    # MetaTrader 5 服务器名称（如 "MetaQuotes-Demo"）
    "MT5_SERVER": os.getenv("MT5_SERVER", ""),

    # NewsAPI 密钥，用于获取黄金相关新闻资讯
    "NEWS_API_KEY": os.getenv("NEWS_API_KEY", ""),

    # Alpha Vantage 密钥，用于获取宏观经济与金融数据
    "ALPHA_VANTAGE_API_KEY": os.getenv("ALPHA_VANTAGE_API_KEY", ""),

    # 默认交易品种（MT5 符号），黄金通常为 XAUUSD
    "DEFAULT_SYMBOL": "XAUUSD",
    # K 线默认时间周期（MT5 常量名，如 TIMEFRAME_H1）
    "DEFAULT_TIMEFRAME": "TIMEFRAME_H1",
    # 默认拉取的历史 K 线数量
    "DEFAULT_BARS": 500,
}
