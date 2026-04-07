# 多因子打板策略项目 Code Wiki

## 目录
1. [项目概述](#1-项目概述)
2. [项目架构](#2-项目架构)
3. [核心模块说明](#3-核心模块说明)
4. [关键类与函数](#4-关键类与函数)
5. [依赖关系](#5-依赖关系)
6. [项目运行方式](#6-项目运行方式)
7. [开发与维护](#7-开发与维护)

---

## 1. 项目概述

### 1.1 项目简介
本项目是一个基于聚宽(JoinQuant)平台的多因子打板策略系统，融合了涨停板策略与多因子评分系统。策略通过五大交易模式捕捉不同市场环境下的投资机会，使用六维度评分系统进行股票筛选，并配备多层风险控制机制。

项目同时提供了完整的本地化部署方案，使策略代码无需修改即可在本地环境运行。

### 1.2 核心特性
- **五大交易模式**：连板龙头、一进二、弱转强、首板低开、反向首板低开
- **六维度评分系统**：涨停分、技术分、放量MA分、主线分、情绪分、主力资金分
- **动态优先级调整**：根据市场趋势自动调整策略优先级
- **三层风控体系**：买入前风控、持仓中风控、卖出逻辑优化
- **本地回测支持**：完整的聚宽API兼容层，基于AKShare数据源

### 1.3 项目结构
```
/workspace/
├── nice_try.py              # 主策略文件（聚宽平台）
├── requirements.txt         # 依赖库清单
├── README.md                # 项目说明文档
├── .gitignore               # Git忽略配置
└── local_deploy/            # 本地部署模块
    ├── __init__.py          # 包初始化
    ├── jq_adapter.py        # 聚宽API兼容层
    ├── backtest_engine.py   # 本地回测引擎
    └── run_backtest.py      # 回测入口脚本
```

---

## 2. 项目架构

### 2.1 整体架构
项目采用分层架构设计，分为以下几个主要层次：

```
┌─────────────────────────────────────────────────────────┐
│                    策略层 (Strategy Layer)                │
│                      nice_try.py                          │
│  包含：策略逻辑、选股、评分、交易执行、风控                  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  框架层 (Framework Layer)                  │
│                backtest_engine.py                         │
│  包含：Context、Portfolio、Position、log、订单执行、调度器  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  数据层 (Data Layer)                       │
│                  jq_adapter.py                            │
│  包含：聚宽API映射、AKShare数据源、内存缓存                  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  外部数据源 (External Data)                │
│                    AKShare / 聚宽平台                       │
└─────────────────────────────────────────────────────────┘
```

### 2.2 核心模块关系图
```
┌─────────────────────────────────────────────────────────────┐
│                        回测入口                                │
│                    run_backtest.py                           │
└────────────────┬────────────────────────────────────────────┘
                 │
         ┌───────▼────────┐
         │                │
         │  策略加载与注入  │
         │                │
         └───────┬────────┘
                 │
         ┌───────▼──────────┐
         │                  │
         │  backtest_engine │
         │   (回测引擎)      │
         │                  │
         └──┬──────────────┘
            │
    ┌───────┴───────────────┐
    │                       │
┌───▼───────────┐   ┌──────▼───────┐
│               │   │              │
│   Context     │   │   Portfolio  │
│               │   │              │
└───┬───────────┘   └──────┬───────┘
    │                       │
    └───────┬───────────────┘
            │
    ┌───────▼──────────┐
    │                  │
    │   jq_adapter     │
    │   (API兼容层)     │
    │                  │
    └──────────────────┘
            │
    ┌───────▼──────────┐
    │                  │
    │     AKShare      │
    │   (外部数据源)    │
    │                  │
    └──────────────────┘
```

---

## 3. 核心模块说明

### 3.1 主策略模块 ([nice_try.py](file:///workspace/nice_try.py))

#### 3.1.1 模块职责
- 策略逻辑的核心实现
- 股票筛选与评分系统
- 交易执行与风险管理
- 定时任务调度

#### 3.1.2 主要功能分区
| 功能分区 | 行号范围 | 说明 |
|---------|---------|------|
| 初始化函数 | 22-98 | 策略初始化、全局变量设置、定时任务注册 |
| 本地热点概念计算 | 168-315 | 计算昨日涨停股、统计热门概念、主线评分 |
| 股票筛选与评分 | 320-715 | 评分筛选、资金流数据获取、买入评分计算 |
| 技术指标计算 | 718-1009 | 同花顺指标、放量大跌检测、5分钟卖出检测 |
| 盘前盘后统计 | 1012-1065 | 盘前数据统计、盘后数据统计 |
| 卖出逻辑 | 1067-1218 | 涨停低开止损、空仓判断 |
| 选股逻辑 | 1256-1317 | 获取股票列表 |
| 买入逻辑 | 1372-1916 | 买入主函数、量能数据获取 |
| 周五优化逻辑 | 1997-2084 | 周五尾盘优化交易逻辑 |
| 因子计算函数 | 2086-2875 | 各类因子评分计算函数 |
| 工具函数 | 2876-3448 | 辅助工具函数 |

#### 3.1.3 核心策略参数
```python
g.position_limit = 2              # 最大持仓数量
g.min_score = 14                   # 最低评分要求
g.concept_num = 8                  # 热点概念最大个数
g.jqfactor = 'VOL5'                # 聚宽因子（5日平均换手率）
```

### 3.2 聚宽API兼容层 ([local_deploy/jq_adapter.py](file:///workspace/local_deploy/jq_adapter.py))

#### 3.2.1 模块职责
- 将聚宽平台专有API映射到本地免费数据源（AKShare）
- 提供内存缓存减少重复网络请求
- 保持与聚宽平台一致的接口签名

#### 3.2.2 主要功能模块
| 功能模块 | 说明 |
|---------|------|
| 内存缓存辅助 | `_cache`、`_cached`、`clear_cache` |
| 代码格式转换 | `_to_akshare_code`、`_to_jq_code`、`normalize_code` |
| 交易日历 | `_get_trade_calendar`、`get_trade_days`、`get_shifted_date` |
| 证券信息 | `SecurityInfo`、`_get_stock_name_map`、`get_security_info`、`get_all_securities` |
| 历史行情数据 | `_fetch_daily_hist`、`_fetch_index_hist`、`get_price`、`attribute_history` |
| 实时行情 | `_StockCurrentData`、`_CurrentDataProxy`、`get_current_data` |
| 估值数据 | `get_valuation` |
| 财务数据 | `get_fundamentals`（简化版） |
| 资金流数据 | `get_money_flow` |
| 集合竞价数据 | `get_call_auction`（暂不支持） |
| 因子数据 | `get_factor_values`（仅支持VOL5） |

#### 3.2.3 数据源映射关系
| 数据类型 | 聚宽函数 | 本地实现 | AKShare接口 |
|---------|---------|---------|------------|
| 交易日历 | `get_trade_days` | ✅ | `tool_trade_date_hist_sina` |
| 证券信息 | `get_security_info` | ✅ | `stock_info_a_code_name` |
| 日线行情 | `get_price` | ✅ | `stock_zh_a_hist` |
| 指数行情 | `get_price` | ✅ | `stock_zh_index_daily` |
| 估值数据 | `get_valuation` | ✅ | `stock_a_lg_indicator` |
| 资金流向 | `get_money_flow` | ✅ | `stock_individual_fund_flow` |
| 集合竞价 | `get_call_auction` | ❌ | 无 |
| 因子数据 | `get_factor_values` | 部分 | 通过估值数据计算 |

### 3.3 本地回测引擎 ([local_deploy/backtest_engine.py](file:///workspace/local_deploy/backtest_engine.py))

#### 3.3.1 模块职责
- 实现聚宽框架的核心运行时对象
- 提供Context、Portfolio、Position等核心类
- 实现订单执行系统
- 提供定时任务调度器
- 计算回测绩效指标

#### 3.3.2 核心类
| 类名 | 说明 | 主要属性/方法 |
|-----|------|--------------|
| `_JQLogger` | 模拟聚宽log对象 | `info()`、`error()`、`warning()`、`debug()`、`set_level()` |
| `Position` | 模拟单只股票持仓 | `total_amount`、`closeable_amount`、`avg_cost`、`update_price()` |
| `Portfolio` | 模拟资产组合 | `positions`、`available_cash`、`total_value`、`refresh_total_value()` |
| `Context` | 模拟聚宽context对象 | `current_dt`、`previous_date`、`portfolio` |
| `_GlobalNamespace` | 模拟聚宽g对象 | 全局变量命名空间 |
| `BacktestEngine` | 回测引擎主类 | `run()`、`load_strategy()`、`_print_summary()`、`get_equity_curve()` |

#### 3.3.3 订单执行函数
| 函数名 | 说明 |
|-------|------|
| `order_value()` | 按金额下单 |
| `order_target_value()` | 调整持仓至目标金额 |
| `order_target()` | 调整持仓至目标股数 |
| `_execute_order()` | 内部执行单笔订单 |

#### 3.3.4 绩效指标计算
- 总收益率
- 年化收益率
- 最大回撤
- 夏普比率

### 3.4 回测入口脚本 ([local_deploy/run_backtest.py](file:///workspace/local_deploy/run_backtest.py))

#### 3.4.1 模块职责
- 提供命令行接口
- 策略模块加载与注入
- 回测参数配置
- 结果保存与输出

#### 3.4.2 主要流程
1. 解析命令行参数
2. 创建BacktestEngine实例
3. 动态加载策略模块
4. 注入本地兼容层函数
5. 包装initialize函数
6. 执行回测
7. 保存权益曲线

---

## 4. 关键类与函数

### 4.1 主策略关键函数

#### 4.1.1 初始化函数
```python
def initialize(context):
    """策略初始化函数"""
```
**职责**：
- 设置策略选项（使用真实价格、避免未来数据）
- 初始化全局变量g
- 注册定时任务（盘前统计、选股、买入、卖出等）

#### 4.1.2 股票筛选函数
```python
def filter_stocks_by_score_optimized(stocks, context, min_score=14, max_stocks=100):
    """优化后的根据评分筛选股票函数"""
```
**职责**：
- 对候选股票进行六维度评分
- 根据评分阈值和模式过滤
- 缓存评分结果
- 返回符合条件的股票列表

#### 4.1.3 评分计算函数
```python
def calculate_buy_score_optimized(stock, context, money_flow_map):
    """计算买入评分（包含全部6个因子）"""
```
**职责**：
- 调用各因子评分函数
- 汇总总分
- 返回评分结果字典

#### 4.1.4 因子评分函数
| 函数名 | 说明 | 分值范围 |
|-------|------|---------|
| `calculate_limit_up_score_optimized()` | 涨停评分 | 0-5 |
| `calculate_technical_score_optimized()` | 技术评分 | 0-5 |
| `calculate_volume_ma_score_optimized()` | 放量MA评分 | 0-5 |
| `calculate_mainline_score_optimized()` | 主线评分 | 0-5 |
| `calculate_sentiment_score_optimized()` | 情绪评分 | 0-5 |
| `calculate_main_force_flow_score()` | 主力资金评分 | 0-5 |

#### 4.1.5 买入函数
```python
def buy(context):
    """买入主函数"""
```
**职责**：
- 获取合格股票列表
- 根据策略优先级排序
- 执行买入操作
- 记录交易日志

#### 4.1.6 卖出检测函数
```python
def sell_limit_per5min(context):
    """每5分钟检测持仓股票是否需要卖出"""
```
**职责**：
- 检测同花顺指标的波段卖信号
- 检测放量大跌信号
- 执行紧急止损或波段卖出

### 4.2 回测引擎关键类

#### 4.2.1 BacktestEngine类
```python
class BacktestEngine:
    """聚宽策略本地回测引擎"""
```

**主要方法**：
| 方法 | 说明 |
|-----|------|
| `__init__(start, end, capital, ...)` | 初始化回测引擎 |
| `load_strategy(module_name)` | 加载策略模块 |
| `run(initialize_fn)` | 执行回测 |
| `_print_summary()` | 打印回测绩效汇总 |
| `get_equity_curve()` | 返回权益曲线 |

**核心属性**：
- `context`: Context对象
- `_schedule`: 调度表
- `_intraday_times`: 每日模拟交易时间点
- `_daily_equity`: 每日权益记录

#### 4.2.2 Portfolio类
```python
class Portfolio:
    """模拟资产组合"""
```

**主要属性**：
| 属性 | 说明 |
|-----|------|
| `starting_cash` | 初始资金 |
| `available_cash` | 可用现金 |
| `locked_cash` | 锁定现金 |
| `positions` | 持仓字典 {security: Position} |
| `total_value` | 总资产 |
| `positions_value` | 持仓总市值 |

**主要方法**：
| 方法 | 说明 |
|-----|------|
| `refresh_total_value()` | 刷新总资产 |
| `_calc_commission()` | 计算手续费 |

### 4.3 API兼容层关键函数

#### 4.3.1 get_price函数
```python
def get_price(security, start_date=None, end_date=None, ...):
    """获取历史行情数据"""
```

**参数说明**：
- `security`: 证券代码或代码列表
- `start_date`: 开始日期
- `end_date`: 结束日期
- `count`: 获取条数（优先于start_date）
- `fields`: 字段列表

**返回值**：包含code、date及行情字段的DataFrame

#### 4.3.2 attribute_history函数
```python
def attribute_history(security, count, unit='1d', ...):
    """获取单只股票历史数据"""
```

**参数说明**：
- `security`: 证券代码
- `count`: 获取的历史K线条数
- `unit`: 周期（仅支持'1d'）
- `fields`: 字段列表

**返回值**：DataFrame或字典

#### 4.3.3 get_current_data函数
```python
def get_current_data():
    """获取当前时间点的行情快照"""
```

**返回值**：可按股票代码索引的字典，值为`_StockCurrentData`对象

#### 4.3.4 get_valuation函数
```python
def get_valuation(security, start_date=None, end_date=None, ...):
    """获取估值数据"""
```

**支持字段**：
- `pe_ratio`: 市盈率
- `pb_ratio`: 市净率
- `market_cap`: 总市值
- `circulating_market_cap`: 流通市值
- `turnover_ratio`: 换手率

#### 4.3.5 get_money_flow函数
```python
def get_money_flow(security, start_date=None, end_date=None, ...):
    """获取个股资金流向数据"""
```

**返回字段**：
- `net_amount_main`: 主力净流入额（万元）
- `net_pct_main`: 主力净流入占比（%）
- `net_amount_l`: 大单净流入额
- `net_amount_m`: 中单净流入额
- `net_amount_s`: 小单净流入额

---

## 5. 依赖关系

### 5.1 依赖库清单

#### 5.1.1 核心依赖（必需）
| 库名 | 版本要求 | 用途 |
|-----|---------|------|
| numpy | >=1.24.0 | 数值计算 |
| pandas | >=2.0.0 | 数据处理与分析 |
| akshare | >=1.14.0 | 免费金融数据源 |

#### 5.1.2 技术分析库
| 库名 | 版本要求 | 用途 |
|-----|---------|------|
| pandas-ta | >=0.3.14b0 | 纯Python技术指标库 |

#### 5.1.3 可视化库（可选）
| 库名 | 版本要求 | 用途 |
|-----|---------|------|
| matplotlib | >=3.7.0 | 绘制回测权益曲线 |

#### 5.1.4 其他工具库
| 库名 | 版本要求 | 用途 |
|-----|---------|------|
| requests | >=2.31.0 | HTTP请求 |
| python-dateutil | >=2.8.2 | 日期处理 |
| pytz | >=2023.3 | 时区处理 |
| tqdm | >=4.65.0 | 进度条 |

### 5.2 内部模块依赖关系

```
nice_try.py (主策略)
    ↓ (依赖)
┌─── jq_adapter.py (API兼容层)
│       ↓ (依赖)
│       └── AKShare (外部数据源)
│
└─── backtest_engine.py (回测引擎)
        ↓ (依赖)
        └── jq_adapter.py

run_backtest.py (入口脚本)
    ↓ (依赖)
    ├── backtest_engine.py
    └── nice_try.py (策略模块)
```

### 5.3 可选依赖

#### 5.3.1 Tushare Pro
```python
# tushare>=1.4.0
```
- 需要申请token
- 数据较全
- 可替代AKShare作为数据源

#### 5.3.2 JQData本地版
```python
# jqdatasdk>=1.9.0
```
- 聚宽官方本地数据
- 付费
- 数据最完整，与聚宽平台一致

#### 5.3.3 TA-Lib
```python
# ta-lib>=0.4.28
```
- C库实现的技术指标
- 性能更好
- 需要先安装C库

---

## 6. 项目运行方式

### 6.1 聚宽平台运行

#### 6.1.1 注册聚宽账号
访问：https://www.joinquant.com/

#### 6.1.2 创建策略
1. 登录后点击"策略研究" → "策略编辑器"
2. 创建新策略，复制 [nice_try.py](file:///workspace/nice_try.py) 代码
3. 设置策略参数

#### 6.1.3 配置回测参数
```python
起始资金：100000 - 1000000
回测周期：建议先测试 2023-01-01 至 2023-12-31
运行频率：日线
基准：沪深300 (000300.XSHG)
手续费：默认（3‱佣金 + 1‰印花税）
```

#### 6.1.4 运行回测
点击"运行回测"按钮，等待回测完成。

### 6.2 本地回测运行

#### 6.2.1 环境准备
```bash
# 1. 克隆或下载项目
cd /workspace

# 2. 安装依赖
pip install -r requirements.txt
```

#### 6.2.2 基本用法
```bash
# 使用默认参数（2023年上半年，50万初始资金）
python local_deploy/run_backtest.py
```

#### 6.2.3 自定义参数
```bash
python local_deploy/run_backtest.py \
    --start 2023-01-01 \
    --end   2023-12-31 \
    --capital 500000 \
    --strategy nice_try \
    --loglevel INFO
```

#### 6.2.4 命令行参数说明
| 参数 | 默认值 | 说明 |
|-----|-------|------|
| `--start` | 2023-01-01 | 回测开始日期 (YYYY-MM-DD) |
| `--end` | 2023-06-30 | 回测结束日期 (YYYY-MM-DD) |
| `--capital` | 500000 | 初始资金（元） |
| `--strategy` | nice_try | 策略模块名（不含.py） |
| `--loglevel` | INFO | 日志级别 (DEBUG/INFO/WARNING/ERROR) |

#### 6.2.5 回测输出示例
```
============================================================
聚宽量化策略本地回测系统
============================================================
策略模块 : nice_try
回测区间 : 2023-01-01 → 2023-12-31
初始资金 : 500,000 元
============================================================
[2023-01-03 09:25:00 INFO] 回测开始: 2023-01-03 → 2023-12-29，初始资金: 500,000 元
[2023-01-03 09:25:00 INFO] 共 242 个交易日
...
==================================================
📊 回测绩效汇总
==================================================
  回测区间   : 2023-01-03 → 2023-12-29
  初始资金   :      500,000 元
  期末资产   :      612,480 元
  总收益率   :      22.50%
  年化收益率 :      22.50%
  最大回撤   :      -8.32%
  夏普比率   :        1.45
==================================================
权益曲线已保存到: /workspace/backtest_results/equity_curve.csv
```

### 6.3 结果查看

#### 6.3.1 控制台输出
- 回测进度日志
- 交易明细日志
- 最终绩效汇总

#### 6.3.2 文件输出
- 权益曲线数据：`backtest_results/equity_curve.csv`

---

## 7. 开发与维护

### 7.1 代码组织规范

#### 7.1.1 文件命名
- 策略文件：`*.py`（如`nice_try.py`）
- 本地部署模块：`local_deploy/`目录下
- 文档文件：`*.md`

#### 7.1.2 函数命名
- 公开函数：使用下划线分隔（如`get_price`）
- 内部函数：以下划线开头（如`_to_akshare_code`）
- 类名：使用驼峰命名（如`BacktestEngine`）

### 7.2 扩展开发指南

#### 7.2.1 添加新的数据源
在 [jq_adapter.py](file:///workspace/local_deploy/jq_adapter.py) 中：
1. 导入新的数据源库
2. 实现对应的数据获取函数
3. 保持与聚宽API一致的接口签名

#### 7.2.2 添加新的因子
在 [nice_try.py](file:///workspace/nice_try.py) 中：
1. 实现新的因子评分函数
2. 在`calculate_buy_score_optimized`中调用
3. 更新评分汇总逻辑

#### 7.2.3 添加新的交易模式
在 [nice_try.py](file:///workspace/nice_try.py) 中：
1. 实现新模式的选股逻辑
2. 更新优先级配置
3. 在`filter_stocks_by_score_optimized`中添加过滤条件

### 7.3 常见问题

#### 7.3.1 本地回测速度慢
- 原因：AKShare需要网络请求数据
- 解决：增加缓存、使用付费数据源（JQData）

#### 7.3.2 集合竞价数据缺失
- 原因：AKShare不提供历史集合竞价数据
- 解决：使用JQData本地版或忽略相关逻辑

#### 7.3.3 因子数据不完整
- 原因：本地仅支持VOL5因子
- 解决：通过其他数据源计算或使用付费因子库

### 7.4 优化建议

#### 7.4.1 短期优化（1-2周）
- 增加最大回撤控制（建议15%）
- 增加单日最大亏损限制（建议5%）
- 完善异常处理，避免策略崩溃
- 统一日志规范

#### 7.4.2 中期优化（1-2月）
- 模块化重构，拆分文件
- 参数配置化，便于调优
- 增加回测验证，优化因子权重
- 批量查询优化，提升性能

#### 7.4.3 长期规划（3-6月）
- 引入机器学习因子挖掘
- 多策略组合，降低单一策略风险
- 实盘监控与自动调参系统
- 风险预警与熔断机制

---

## 附录

### A. 参考资料
- [聚宽API文档](https://www.joinquant.com/help/api/help?name=api)
- [多因子策略入门](https://www.joinquant.com/post/1399)
- [五合一打板策略](https://www.joinquant.com/post/67584)
- [AKShare文档](https://akshare.akfamily.xyz/)

### B. 风险提示
- 涨停板策略固有风险：追高风险大，需要严格止损
- 市场环境风险：极端行情下策略可能失效
- 技术风险：数据延迟或错误、网络故障、策略代码bug

### C. 使用建议
- 先在模拟账户测试至少3个月
- 初始资金不超过总资产的10%
- 设置严格的止损线
- 定期检查策略表现
- 关注市场环境变化

---

**文档版本**：1.0  
**最后更新**：2026-04-07  
**维护者**：项目开发团队
