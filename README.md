# 🏆 黄金投资智能顾问 (Gold Advisor AI)

基于多智能体架构的黄金(XAU/USD)买卖点位AI分析系统。融合技术指标、财经新闻情绪、宏观经济基本面三个维度，通过 LangGraph 编排并行分析，生成可解释的投资建议。

## 技术栈

| 层级 | 技术 |
|------|------|
| 编排引擎 | LangGraph — 多智能体状态图编排 |
| 大模型 | DeepSeek API — 推理驱动（兼容 OpenAI 接口） |
| 行情数据 | MetaTrader 5 — 实时黄金 K 线 |
| 技术指标 | pandas-ta — MA/EMA/RSI/MACD/KDJ/布林带/ATR |
| 宏观数据 | Alpha Vantage / Yahoo Finance / 新浪财经（多源降级） |
| 新闻获取 | NewsAPI / Google News / 新浪财经（多源降级） |
| Web 界面 | Streamlit + Plotly — 交互式图表看板 |

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                        collect_data                          │
│         MT5行情 · 财经新闻 · 宏观经济 · 多源降级               │
└──────┬────────────────────┬────────────────────┬─────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  technical   │   │  sentiment   │   │ fundamental  │
│  Agent (45%) │   │  Agent (25%) │   │   Agent (30%)│
│  技术指标分析  │   │  新闻情绪分析  │   │  宏观基本面分析 │
└──────┬───────┘   └──────┬───────┘   └──────┬───────┘
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
              ┌────────────────────┐
              │   strategy engine   │
              │ 加权汇总 · 信号融合  │
              │ 风控计算 · 报告生成  │
              └─────────┬──────────┘
                        ▼
                   ┌────────┐
                   │ output │
                   │  最终报告 │
                   └────────┘
```

- **权重分配**：技术面 45% · 情绪面 25% · 基本面 30%
- **信号判定**：综合得分 > 30 → BUY · < -30 → SELL · 之间 → HOLD
- **三档风控**：保守(止损2%/仓位10%) · 平衡(止损3%/仓位20%) · 激进(止损5%/仓位30%)

## 快速开始

### 环境要求

- Windows 操作系统
- Python 3.10 ~ 3.12
- MetaTrader 5 客户端（已安装并登录账户）

### 安装步骤

```powershell
# 1. 克隆项目
git clone <your-repo-url>
cd gold-advisor

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate

# 3. 安装依赖
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. 配置环境变量（复制模板并填入真实值）
copy .env.example .env

# 5. 启动 Web 界面
streamlit run app.py
```

### 验证安装

```powershell
python verify_env.py
```

## 项目结构

```
gold-advisor/
├── app.py                          # Streamlit Web 界面（5 个分析 Tab）
├── main.py                         # 命令行入口（LangGraph 完整工作流）
├── config.py                       # 配置加载（读取 .env）
├── requirements.txt                # Python 依赖清单
├── verify_env.py                   # 环境验证脚本
├── .env                            # 环境变量（API Keys，不提交 Git）
├── .env.example                    # 环境变量模板
├── data/                           # 报告 JSON 输出目录
├── src/
│   ├── data/
│   │   ├── mt5_data.py             # MT5 行情数据获取（连接/金价/K线）
│   │   ├── macro_data.py           # 宏观经济数据（DXY/VIX/美债收益率）
│   │   └── news_data.py            # 财经新闻获取（中英文双源降级）
│   ├── agents/
│   │   ├── technical_agent.py      # 技术分析 Agent（指标计算 + LLM）
│   │   ├── sentiment_agent.py      # 情绪分析 Agent（新闻分析 + LLM）
│   │   ├── fundamental_agent.py    # 基本面 Agent（宏观分析 + LLM）
│   │   └── test_integration.py     # 三 Agent 联调测试
│   ├── strategy/
│   │   └── engine.py               # 策略引擎（信号融合/风控/报告）
│   ├── graph/
│   │   └── workflow.py             # LangGraph 工作流编排
│   └── utils/
│       └── llm.py                  # LLM 连接器（DeepSeek 调用封装）
└── tests/
```

## 配置说明

在项目根目录创建 `.env` 文件，包含以下变量：

```env
# DeepSeek API（必填）
DEEPSEEK_API_KEY=sk-your-deepseek-api-key

# MetaTrader 5 账户（必填）
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server

# NewsAPI（可选，无 Key 则用 Google News RSS 备源）
NEWS_API_KEY=your_newsapi_key

# Alpha Vantage（可选，用于美债收益率，免费 Key 有频率限制）
ALPHA_VANTAGE_API_KEY=your_alphavantage_key
```

至少需要配置 **DeepSeek API Key** 和 **MT5 账户信息**，系统即可正常运行（新闻和宏观数据有降级方案）。

## 功能特性

- **三维度并行分析**：技术面(45%) + 情绪面(25%) + 基本面(30%)，通过 LangGraph 并行执行
- **三档风控**：保守/平衡/激进，自动计算止损止盈和仓位
- **信号一致性检测**：三 Agent 方向分歧时自动预警
- **风险回报比校验**：RR < 1 时标记不建议入场
- **多数据源降级**：DXY(Alpha Vantage → Frankfurter)、VIX(Yahoo → 新浪)、新闻(NewsAPI → Google News → 新浪)，中英文双源
- **交互式可视化**：K 线图、RSI/MACD 副图、得分仪表盘、风控表格
- **报告持久化**：CLI 模式下自动保存 JSON 报告到 `data/` 目录
- **完整错误处理**：每个节点独立 try-except，部分失败不中断整体流程

## 使用方式

### Web 界面（推荐）

```powershell
streamlit run app.py
```

侧边栏选择 K 线周期/数量/风险偏好 → 点击「🚀 开始分析」→ 查看 5 个 Tab 的完整报告。

### 命令行

```powershell
python main.py
```

运行完整 LangGraph 工作流，终端输出最终报告，同时保存 JSON 到 `data/gold_report_XXXXXXXX_XXXXXX.json`。

## 免责声明

本报告由 AI 生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。系统分析结果基于历史数据和统计模型，不保证未来表现。使用者应独立判断并自行承担交易风险。
