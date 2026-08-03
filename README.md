# 🏆 黄金投资智能顾问 (Gold Advisor AI)

基于 LangGraph 多智能体架构的黄金(XAU/USD)买卖点位 AI 分析系统，融合**技术指标**、**新闻情绪**、**宏观经济**三个维度，通过 3 个 AI Agent 并行分析生成投资建议。支持 Web 交互看板、AI 交易员对话、MT5 实时交易执行。

> 📌 **本项目是一个完整的 AI 应用端到端项目**：从数据采集 → AI 分析 → 策略决策 → 交易执行 → Web 交互，适合学习 LLM 应用开发、多智能体编排、量化交易系统设计。

---

## 📖 目录

- [功能特性](#-功能特性)
- [技术栈](#-技术栈)
- [架构设计](#-架构设计)
- [快速开始](#-快速开始)
- [API Key 获取指南](#-api-key-获取指南)
- [配置说明](#-配置说明)
- [项目结构](#-项目结构)
- [使用方式](#-使用方式)
- [常见问题 (FAQ)](#-常见问题-faq)
- [免责声明](#-免责声明)

---

## ✨ 功能特性

### 核心分析引擎
- **三维度并行分析**：技术面(45%) + 情绪面(25%) + 基本面(30%)，LangGraph 并行执行
- **加权信号融合**：综合得分 > 30 → BUY · < -30 → SELL · 之间 → HOLD
- **三档风控**：保守(止损2%/仓位10%) · 平衡(止损3%/仓位20%) · 激进(止损5%/仓位30%)
- **信号一致性检测**：三 Agent 方向分歧时自动预警
- **风险回报比校验**：RR < 1 时标记不建议入场

### Web 交互看板
- **综合建议**：买卖方向 + 置信度 + 实时金价 + AI 决策理由
- **MT5 风格手动交易页**：左面板(下单+SL/TP) + 右K线图(布林带+均线) + 底部持仓管理
- **K 线图**：多周期切换（M1/M30/H1/H4/D1），蜡烛图 + 布林带 + MA5 + MA10，红涨绿跌
- **技术指标表**：RSI / MACD / KDJ / 布林带 / ATR 实时数值与研判
- **新闻情绪分析**：中文+英文新闻源，情绪评分，可点击展开查看新闻详情
- **AI 交易员对话**：技术面 / 情绪面 / 基本面 3 个独立 AI 交易员，实时数据驱动对话

### 交易系统
- **MT5 实盘执行**：开仓/平仓/改单/批量平仓/持仓查询
- **风控预检**：下单前自动校验保证金、仓位、止损，不满足条件时阻止下单
- **交易日志**：所有交易自动记录 JSONL 日志，支持历史查询和统计

### 数据保障
- **多源降级**：DXY(Alpha Vantage → Frankfurter)、VIX(Yahoo → 新浪)、新闻(NewsAPI → Google → 新浪)
- **中英文双源新闻**：覆盖面更广，避免单一语言偏向

---

## 🛠 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 编排引擎 | LangGraph | 多智能体状态图编排，并行执行 |
| 大模型 | DeepSeek API | 推理驱动，兼容 OpenAI 接口 |
| LLM 框架 | LangChain | Prompt 模板、流式输出、对话历史管理 |
| 行情数据 | MetaTrader 5 | 实时黄金 K 线 + 实时报价 |
| 技术指标 | pandas-ta | MA/EMA/RSI/MACD/KDJ/布林带/ATR |
| 宏观数据 | Alpha Vantage / Yahoo / 新浪 | 多源降级 |
| 新闻获取 | NewsAPI / Google / 新浪 | 中英文双源 |
| Web 界面 | Streamlit + Plotly | 交互式图表看板 |

---

## 🏗 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      collect_data                            │
│       MT5行情 · 财经新闻 · 宏观经济 · 多源降级                  │
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
              ┌────────────────────────┐
              │    strategy engine      │
              │  加权汇总 · 信号融合     │
              │  风控计算 · 报告生成     │
              └───────────┬────────────┘
                          ▼
              ┌───────────────────────┐
              │      Web 交互层        │
              │  看板 / 交易 / AI对话    │
              └───────────────────────┘
```

---

## 🚀 快速开始

### 前置条件

| 要求 | 说明 |
|------|------|
| 操作系统 | **Windows**（MT5 仅支持 Windows） |
| Python | 3.10 ~ 3.12 |
| MetaTrader 5 | 已安装并登录交易账户（模拟账户也可） |
| DeepSeek API Key | 用于 AI 分析（[免费注册获取](https://platform.deepseek.com)） |

### 安装步骤

```powershell
# 1. 克隆项目
git clone https://github.com/chenjue8888-arch/gold-advisor.git
cd gold-advisor

# 2. 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate

# 3. 安装依赖
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# 4. 配置环境变量
copy .env.example .env
# 用记事本打开 .env，填入你的 API Key（详见下方配置说明）

# 5. 启动 Web 界面
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`，即可使用。

### 验证安装

```powershell
python verify_env.py
```

---

## 🔑 API Key 获取指南

### 必填（缺一不可正常运行）

| Key | 用途 | 获取方式 | 费用 |
|-----|------|---------|------|
| **DEEPSEEK_API_KEY** | AI 分析引擎 | 1. 访问 [platform.deepseek.com](https://platform.deepseek.com)<br>2. 注册账号 → API Keys → 创建新 Key | 充值 ¥10 可用数月 |
| **MT5_LOGIN** | 行情数据来源 | 1. 下载 [MetaTrader 5](https://www.metatrader5.com)<br>2. 注册模拟账户（MT5内直接申请）<br>3. 记下登录号、密码、服务器名 | 免费（模拟账户） |

### 可选（无 Key 时自动降级到免费数据源）

| Key | 用途 | 降级方案 | 获取方式 |
|-----|------|---------|---------|
| **NEWS_API_KEY** | 英文黄金新闻 | 自动降级到 Google News RSS | [newsapi.org](https://newsapi.org) 免费注册 |
| **ALPHA_VANTAGE_API_KEY** | 美债收益率 | 自动降级到公开数据 | [alphavantage.co](https://alphavantage.co) 免费注册 |

---

## ⚙️ 配置说明

编辑 `.env` 文件（项目根目录）：

```env
# ====== 必填 ======
# DeepSeek API（AI 分析引擎）
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# MetaTrader 5 账户（行情数据 + 交易执行）
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=ICMarkets-Demo

# ====== 可选（不填也能用，会自动降级） ======
NEWS_API_KEY=your_newsapi_key_here
ALPHA_VANTAGE_API_KEY=your_alphavantage_key_here
```

> ⚠️ `.env` 文件已加入 `.gitignore`，不会被上传到 GitHub。请勿将真实 Key 写在代码中。

---

## 📁 项目结构

```
gold-advisor/
├── app.py                          # Streamlit Web 主界面
├── main.py                         # 命令行入口（LangGraph 工作流）
├── config.py                       # 配置加载
├── requirements.txt                # Python 依赖
├── verify_env.py                   # 环境验证脚本
├── .env                            # 环境变量（不提交 Git）
├── .env.example                    # 环境变量模板
├── data/                           # 分析报告 + 交易日志输出
├── ai_traders/                     # AI 交易员配置
│   ├── technical_trader.md         #   技术面交易员 Prompt
│   ├── sentiment_trader.md         #   情绪面交易员 Prompt
│   ├── fundamental_trader.md       #   基本面交易员 Prompt
│   └── trader_engine.py            #   交易员引擎（加载Prompt + 数据 + LLM对话）
├── src/
│   ├── data/                       # 数据获取模块
│   │   ├── mt5_data.py             #   MT5 行情数据
│   │   ├── macro_data.py           #   宏观经济数据（DXY/VIX/美债）
│   │   └── news_data.py            #   财经新闻（中英文双源）
│   ├── agents/                     # AI Agent 模块
│   │   ├── technical_agent.py      #   技术分析 Agent
│   │   ├── sentiment_agent.py      #   情绪分析 Agent
│   │   └── fundamental_agent.py    #   基本面 Agent
│   ├── strategy/                   # 策略引擎
│   │   └── engine.py               #   信号融合 + 风控 + 报告
│   ├── graph/                      # LangGraph 编排
│   │   └── workflow.py             #   多智能体工作流
│   ├── trading/                    # 交易执行
│   │   ├── executor.py             #   MT5 开仓/平仓/改单
│   │   ├── realtime.py             #   实时报价 + 持仓监控
│   │   ├── risk_guard.py           #   风控预检
│   │   └── logger.py               #   交易日志
│   └── utils/
│       └── llm.py                  # DeepSeek LLM 调用封装
└── tests/                          # 测试文件
```

---

## 📊 使用方式

### Web 界面（推荐）

```powershell
streamlit run app.py
```

启动后浏览器访问 `http://localhost:8501`。

#### 页面导航

| 侧边栏 Tab | 功能 |
|-----------|------|
| **综合分析** | 完整分析看板：买卖信号 + 置信度 + 三个 Agent 研判 + 风险参数 |
| **行情分析** | 技术指标表格 + 新闻情绪列表（可展开查看详情） |
| **手动交易** 🆕 | MT5 桌面端风格：左边下单面板 + 右边K线图 + 底部持仓管理 |
| **AI 交易员** 🆕 | 技术面/情绪面/基本面 3 个 AI 专家，实时数据驱动对话 |

#### 使用流程

1. 侧边栏选择 K 线周期 + 数量 + 风险偏好
2. 点击 "🚀 开始分析" → 等待 AI 生成报告
3. 切换 Tab 查看不同维度的分析结果
4. 在「手动交易」页面查看 K 线图并执行买卖
5. 在「AI 交易员」页面与 AI 专家自由对话

### 命令行

```powershell
python main.py
```

运行 LangGraph 工作流，终端输出报告，JSON 保存到 `data/` 目录。

---

## ❓ 常见问题 (FAQ)

### Q1: 启动报错 `ModuleNotFoundError: No module named 'MetaTrader5'`

**原因**：MT5 Python 包未安装，或 Python 版本不兼容。

**解决**：
```powershell
pip install MetaTrader5
```
如果仍然失败，确保 Python 版本在 3.10 ~ 3.12 之间（MT5 不支持 3.13+）。

### Q2: 点击"开始分析"后一直转圈、没有结果

**可能原因**：
1. DeepSeek API Key 未配置或无效 → 检查 `.env` 文件
2. MT5 未启动或未登录 → 先打开 MT5 客户端，确认已登录账户
3. 网络代理导致 API 请求失败 → 关闭代理或配置 `NO_PROXY`

### Q3: MT5 连接失败 (`connect_mt5() returned False`)

**解决步骤**：
1. 确保 MetaTrader 5 客户端正在运行
2. 确保已登录交易账户（模拟账户即可）
3. 检查 `.env` 中 `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` 是否正确
4. 如果使用 IC Markets 等经纪商，`MT5_SERVER` 通常是 `ICMarkets-Demo`

### Q4: K 线图显示为空

1. 在侧边栏点击 "刷新行情" 按钮
2. 确认 MT5 客户端正在运行且已登录
3. 确认市场开放时间（黄金交易时间：工作日 06:00 - 次日 05:00 GMT+8）

### Q5: AI 交易员对话报错

确保 `.env` 中 `DEEPSEEK_API_KEY` 已正确配置且有余额。可以在 [platform.deepseek.com](https://platform.deepseek.com) 查看余额。

### Q6: 没有 MT5 账户怎么办？

可以直接在 MetaTrader 5 客户端内注册**免费模拟账户**：
1. 打开 MT5 → 文件 → 开设模拟账户
2. 选择经纪商（推荐 IC Markets） → 填写信息 → 完成
3. 记下登录号、密码、服务器名，填入 `.env`

完全免费，可用于开发和测试。

### Q7: DeepSeek API 调用失败 / 余额不足

DeepSeek 国内访问偶尔不稳定，解决方案：
1. 在 `.env` 中临时切换到其他兼容 OpenAI 接口的模型（如通义千问、GLM）
2. 修改 `src/utils/llm.py` 中的 `base_url` 和 `model` 参数

---

## ⚠️ 免责声明

本系统由 AI 生成分析结果，**仅供参考，不构成投资建议**。投资有风险，入市需谨慎。

- 系统分析基于历史数据和统计模型，不保证未来表现
- AI 交易员给出的建议仅供参考，不构成买卖指令
- 使用自动交易功能前，请先在模拟账户中充分测试
- 使用者应独立判断并自行承担交易风险
