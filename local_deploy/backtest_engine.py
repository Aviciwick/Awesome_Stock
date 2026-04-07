"""
backtest_engine.py — 聚宽(JoinQuant)策略本地回测引擎

实现聚宽框架的核心运行时对象：
  - Context / Portfolio / Position
  - log 对象（兼容 log.info / log.error / log.warning / log.debug）
  - order_value / order_target_value / order_target 下单函数
  - run_daily 调度器
  - set_option / g 全局命名空间

使用方法：
    from local_deploy.backtest_engine import BacktestEngine
    engine = BacktestEngine(start="2023-01-01", end="2023-12-31", capital=500_000)
    engine.run()
"""

import datetime as dt
import logging
import sys
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from .jq_adapter import (
    get_trade_days,
    get_price,
    get_current_data,
    get_security_info,
    clear_cache,
)

# ============================================================================
# 日志兼容层
# ============================================================================

class _JQLogger:
    """
    模拟聚宽 ``log`` 对象，将日志转发到标准 Python logging。

    支持 log.info / log.error / log.warning / log.debug。
    ``log.set_level`` 调用会更新底层 Logger 的级别。
    """

    _LEVEL_MAP = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "system": logging.CRITICAL,
    }

    def __init__(self, name: str = "jq.strategy"):
        self._logger = logging.getLogger(name)
        if not self._logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(
                logging.Formatter("[%(asctime)s %(levelname)s] %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S")
            )
            self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def set_level(self, category: str, level: str):
        lvl = self._LEVEL_MAP.get(level.lower(), logging.INFO)
        self._logger.setLevel(lvl)

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(str(msg), *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._logger.debug(str(msg), *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(str(msg), *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(str(msg), *args, **kwargs)


log = _JQLogger()


# ============================================================================
# 持仓与资产组合
# ============================================================================

class Position:
    """模拟单只股票持仓。"""

    def __init__(self, security: str, amount: int = 0, avg_cost: float = 0.0):
        self.security = security
        self.total_amount = amount          # 总持仓量（股）
        self.closeable_amount = amount      # 可卖出量
        self.avg_cost = avg_cost            # 平均成本
        self.price = avg_cost               # 最新价（盘中更新）
        self.value = amount * avg_cost      # 持仓市值

    def update_price(self, price: float):
        self.price = price
        self.value = self.total_amount * price

    @property
    def returns(self) -> float:
        """当前收益率（浮动）。"""
        if self.avg_cost == 0:
            return 0.0
        return (self.price - self.avg_cost) / self.avg_cost


class Portfolio:
    """模拟资产组合（聚宽 ``context.portfolio``）。"""

    def __init__(self, starting_cash: float):
        self.starting_cash: float = starting_cash
        self.available_cash: float = starting_cash
        self.locked_cash: float = 0.0
        self.positions: Dict[str, Position] = {}
        self.total_value: float = starting_cash
        self.inout_cash: float = 0.0  # 累计出入金
        self.transferable_cash: float = starting_cash  # 可取资金
        self._commission_rate: float = 3e-4   # 0.03% 佣金
        self._stamp_tax: float = 1e-3         # 0.1% 印花税（卖出收取）
        self._min_commission: float = 5.0     # 最低佣金
    
    @property
    def long_positions(self) -> Dict[str, Position]:
        """返回所有多头持仓（与聚宽接口兼容）。"""
        return self.positions
    
    @property
    def short_positions(self) -> Dict[str, Position]:
        """返回所有空头持仓（与聚宽接口兼容）。"""
        return {}

    @property
    def positions_value(self) -> float:
        return sum(p.value for p in self.positions.values())
    
    @property
    def returns(self) -> float:
        """累计收益率"""
        if self.starting_cash == 0:
            return 0.0
        return (self.total_value - self.starting_cash) / self.starting_cash

    def refresh_total_value(self):
        self.total_value = self.available_cash + self.locked_cash + self.positions_value

    def _calc_commission(self, price: float, amount: int, is_sell: bool = False) -> float:
        trade_value = price * amount
        comm = max(trade_value * self._commission_rate, self._min_commission)
        tax = trade_value * self._stamp_tax if is_sell else 0.0
        return comm + tax


class _OrderStyle:
    """通用订单风格占位（与聚宽接口保持兼容）。"""
    pass


class MarketOrderStyle(_OrderStyle):
    """市价单风格。"""

    def __init__(self, price: float = 0.0):
        self.price = price


class LimitOrderStyle(_OrderStyle):
    """限价单风格。"""

    def __init__(self, price: float):
        self.price = price


# ============================================================================
# 上下文对象
# ============================================================================

class Context:
    """
    模拟聚宽 ``context`` 对象。

    主要属性：
      current_dt     — 当前模拟时间（datetime）
      previous_date  — 上一交易日（date）
      portfolio      — Portfolio 对象
    """

    def __init__(self, starting_cash: float):
        self.portfolio: Portfolio = Portfolio(starting_cash)
        self.current_dt: dt.datetime = dt.datetime.now()
        self.previous_date: dt.date = dt.date.today() - dt.timedelta(days=1)
        self._current_data_cache = None

    @property
    def current_date(self) -> dt.date:
        return self.current_dt.date()


# ============================================================================
# 全局变量命名空间（g 对象）
# ============================================================================

class _GlobalNamespace:
    """模拟聚宽 ``g`` 全局命名空间。"""

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)

    def __repr__(self):
        attrs = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        return f"<GlobalNamespace {attrs}>"


g = _GlobalNamespace()


# ============================================================================
# 下单函数
# ============================================================================

def _execute_order(
    context: Context,
    security: str,
    amount: int,
    price: float,
    order_style: Optional[_OrderStyle] = None,
) -> Optional[str]:
    """
    内部执行单笔订单。

    Args:
        amount: 正数为买入，负数为卖出。
    Returns:
        订单 ID（字符串）或 None（失败时）。
    """
    portfolio = context.portfolio

    if amount == 0:
        return None

    # 使用传入价格或最新价
    exec_price = price
    if order_style and hasattr(order_style, "price") and order_style.price > 0:
        exec_price = order_style.price

    if exec_price <= 0:
        log.warning(f"下单失败：{security} 价格无效 ({exec_price})")
        return None

    is_sell = amount < 0

    # 计算手续费
    trade_value = abs(amount) * exec_price
    commission = portfolio._calc_commission(exec_price, abs(amount), is_sell)

    if is_sell:
        pos = portfolio.positions.get(security)
        if pos is None or pos.closeable_amount < abs(amount):
            log.warning(f"卖出失败：{security} 持仓不足")
            return None
        pos.total_amount += amount          # amount 为负
        pos.closeable_amount += amount
        portfolio.available_cash += trade_value - commission
        if pos.total_amount <= 0:
            del portfolio.positions[security]
    else:
        cost = trade_value + commission
        if cost > portfolio.available_cash:
            # 按可用资金调整买入量（整手 100 股）
            # 按可用资金调整买入量（整手 100 股）
            # 每股总成本 = 成交价 × (1 + 佣金率)
            cost_per_share = exec_price * (1 + portfolio._commission_rate)
            max_lots = int(portfolio.available_cash / (cost_per_share * 100))
            max_amount = max_lots * 100
            if max_amount <= 0:
                log.warning(f"买入失败：{security} 可用资金不足")
                return None
            amount = max_amount
            trade_value = amount * exec_price
            commission = portfolio._calc_commission(exec_price, amount, False)
            cost = trade_value + commission

        portfolio.available_cash -= cost
        if security in portfolio.positions:
            pos = portfolio.positions[security]
            total_cost = pos.avg_cost * pos.total_amount + trade_value
            pos.total_amount += amount
            pos.closeable_amount += amount
            pos.avg_cost = total_cost / pos.total_amount if pos.total_amount > 0 else 0
        else:
            portfolio.positions[security] = Position(security, amount, exec_price)

    portfolio.refresh_total_value()
    order_id = f"{security}_{context.current_dt.strftime('%Y%m%d%H%M%S')}_{abs(amount)}"
    log.debug(f"订单执行: {'卖出' if is_sell else '买入'} {security} "
              f"{abs(amount)} 股 @ {exec_price:.2f}，手续费 {commission:.2f}")
    return order_id


def _get_latest_price(security: str, context: Context) -> float:
    """获取最新成交价（用于市价单执行）。"""
    try:
        cd = get_current_data()
        if security in cd:
            p = cd[security].last_price
            if p > 0:
                return p
    except Exception:
        pass

    # 回退：取最近一日收盘价
    try:
        df = get_price(security, end_date=str(context.current_date), count=1,
                       fields=["close"])
        if not df.empty:
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def order_value(
    security: str,
    value: float,
    order_style: Optional[_OrderStyle] = None,
):
    """
    按金额下单（对标聚宽 ``order_value``）。

    Args:
        value: 正数为买入目标金额，负数为卖出目标金额（元）。
    """
    from .backtest_engine import _current_context
    context = _current_context
    if context is None:
        log.warning("order_value: context 未设置")
        return None

    price = _get_latest_price(security, context)
    if price <= 0:
        return None

    raw_amount = value / price
    amount = int(raw_amount / 100) * 100  # 整手 100 股
    if abs(amount) < 100:
        return None

    return _execute_order(context, security, amount, price, order_style)


def order_target_value(
    security: str,
    target_value: float,
    order_style: Optional[_OrderStyle] = None,
):
    """
    调整持仓至目标金额（对标聚宽 ``order_target_value``）。

    Args:
        target_value: 0 表示清仓；正数为目标市值（元）。
    """
    from .backtest_engine import _current_context
    context = _current_context
    if context is None:
        log.warning("order_target_value: context 未设置")
        return None

    portfolio = context.portfolio
    price = _get_latest_price(security, context)
    if price <= 0:
        return None

    current_amount = 0
    if security in portfolio.positions:
        current_amount = portfolio.positions[security].total_amount

    target_amount = int(target_value / price / 100) * 100
    delta = target_amount - current_amount

    if abs(delta) < 100:
        return None

    return _execute_order(context, security, delta, price, order_style)


def order_target(
    security: str,
    amount: int,
    order_style: Optional[_OrderStyle] = None,
):
    """调整持仓至目标股数（对标聚宽 ``order_target``）。"""
    from .backtest_engine import _current_context
    context = _current_context
    if context is None:
        return None

    portfolio = context.portfolio
    price = _get_latest_price(security, context)
    if price <= 0:
        return None

    current_amount = 0
    if security in portfolio.positions:
        current_amount = portfolio.positions[security].total_amount

    delta = amount - current_amount
    if abs(delta) < 100:
        return None

    return _execute_order(context, security, delta, price, order_style)


def get_orders(only_open: bool = False) -> Dict:
    """返回空字典（本地模式下订单即时成交）。"""
    return {}


def cancel_order(order_id):
    """占位：本地模式订单即时成交，无需撤单。"""
    pass


# ============================================================================
# 回测引擎主类
# ============================================================================

# 全局 context 引用（供下单函数在不传 context 参数时使用）
_current_context: Optional[Context] = None


class BacktestEngine:
    """
    聚宽策略本地回测引擎。

    使用方法::

        from local_deploy.backtest_engine import BacktestEngine
        engine = BacktestEngine(
            start="2023-01-01",
            end="2023-12-31",
            capital=500_000,
            strategy_module="nice_try",
        )
        engine.run()

    策略模块（strategy_module）需要实现聚宽标准接口，
    至少包含 ``initialize(context)`` 函数。
    """

    def __init__(
        self,
        start: str,
        end: str,
        capital: float = 500_000.0,
        strategy_module: Optional[str] = None,
        commission_rate: float = 3e-4,
        stamp_tax: float = 1e-3,
    ):
        self.start = pd.Timestamp(start).date()
        self.end = pd.Timestamp(end).date()
        self.capital = capital
        self.strategy_module = strategy_module
        self.commission_rate = commission_rate
        self.stamp_tax = stamp_tax

        self.context = Context(capital)
        self.context.portfolio._commission_rate = commission_rate
        self.context.portfolio._stamp_tax = stamp_tax

        # 调度表：{time_str: [func, ...]}
        self._schedule: Dict[str, List[Callable]] = defaultdict(list)

        # 每日模拟交易时间点（按时间顺序）
        self._intraday_times: List[str] = [
            "09:25", "09:28", "09:28:10",
            "09:30", "09:35", "09:40", "09:45", "09:50", "09:55",
            "10:00", "10:05", "10:10", "10:15", "10:20", "10:25", "10:30",
            "10:31", "10:35", "10:40", "10:45", "10:50", "10:55",
            "11:00", "11:01", "11:05",
            "13:05", "13:10", "13:15", "13:20", "13:25", "13:30",
            "13:31", "13:35", "13:40", "13:45", "13:50", "13:55",
            "14:00", "14:01", "14:05", "14:10", "14:15", "14:20", "14:25", "14:30",
            "14:31", "14:35", "14:40", "14:45", "14:50",
            "15:00", "15:05",
        ]

        # 绩效记录
        self._daily_equity: List[Tuple[dt.date, float]] = []

        # 策略函数引用
        self._initialize_fn: Optional[Callable] = None
        self._handle_data_fn: Optional[Callable] = None

    # -------------------------------------------------------------------------
    # 调度接口（替代聚宽 run_daily）
    # -------------------------------------------------------------------------

    def run_daily(self, func: Callable, time: str, reference_security: str = ""):
        """将函数注册到指定时间点执行。"""
        self._schedule[time].append(func)
        log.debug(f"注册调度: {func.__name__} @ {time}")

    def set_option(self, key: str, value=None):
        """兼容聚宽 set_option（本地模式下仅记录日志）。"""
        log.debug(f"set_option({key}={value}) — 本地模式下忽略")

    # -------------------------------------------------------------------------
    # 策略加载
    # -------------------------------------------------------------------------

    def load_strategy(self, module_name: str):
        """
        动态加载策略模块并提取 initialize / handle_data 函数。

        使用 importlib 避免硬编码模块名。
        """
        import importlib
        mod = importlib.import_module(module_name)
        self._initialize_fn = getattr(mod, "initialize", None)
        self._handle_data_fn = getattr(mod, "handle_data", None)

    def _inject_globals(self, strategy_globals: dict):
        """
        向策略模块的全局命名空间注入本地兼容函数。
        使策略代码中的 ``run_daily``、``log``、``g`` 等直接可用。
        """
        injectables = {
            # 框架函数
            "run_daily": self.run_daily,
            "set_option": self.set_option,
            "log": log,
            "g": g,
            # 下单函数
            "order_value": order_value,
            "order_target_value": order_target_value,
            "order_target": order_target,
            "get_orders": get_orders,
            "cancel_order": cancel_order,
            "MarketOrderStyle": MarketOrderStyle,
            "LimitOrderStyle": LimitOrderStyle,
            # 数据函数（从 jq_adapter 导入）
        }
        from . import jq_adapter
        for name in dir(jq_adapter):
            if not name.startswith("_"):
                injectables[name] = getattr(jq_adapter, name)
        strategy_globals.update(injectables)

    # -------------------------------------------------------------------------
    # 辅助：更新持仓市值
    # -------------------------------------------------------------------------

    def _update_positions_value(self):
        """按最新行情刷新所有持仓的市值。"""
        if not self.context.portfolio.positions:
            return
        try:
            cd = get_current_data()
            for sec, pos in self.context.portfolio.positions.items():
                if sec in cd and cd[sec].last_price > 0:
                    pos.update_price(cd[sec].last_price)
            self.context.portfolio.refresh_total_value()
        except Exception as e:
            log.debug(f"刷新持仓市值失败: {e}")

    # -------------------------------------------------------------------------
    # 主回测循环
    # -------------------------------------------------------------------------

    def run(self, initialize_fn: Optional[Callable] = None):
        """
        执行回测。

        Args:
            initialize_fn: 直接传入策略的 initialize 函数。
                           若为 None，则使用 load_strategy 加载的函数。
        """
        global _current_context
        _current_context = self.context

        fn = initialize_fn or self._initialize_fn
        if fn is None:
            raise ValueError("未找到 initialize 函数。请调用 load_strategy() 或直接传入 initialize_fn 参数。")

        log.info(f"回测开始: {self.start} → {self.end}，初始资金: {self.capital:,.0f} 元")

        # 执行策略初始化
        fn(self.context)

        trade_days = get_trade_days(start_date=str(self.start), end_date=str(self.end))
        if not trade_days:
            log.error("指定日期范围内无交易日")
            return

        log.info(f"共 {len(trade_days)} 个交易日")

        for i, trade_day in enumerate(trade_days):
            # 设置上一交易日
            if i > 0:
                self.context.previous_date = trade_days[i - 1]
            else:
                # 尝试获取 start 前一交易日
                prev_days = get_trade_days(end_date=str(trade_day), count=2)
                if len(prev_days) >= 2:
                    self.context.previous_date = prev_days[-2]
                else:
                    self.context.previous_date = trade_day - dt.timedelta(days=1)

            clear_cache()
            self._update_positions_value()

            # 按时间点执行调度函数
            for time_str in self._intraday_times:
                if time_str not in self._schedule:
                    continue
                # 更新 context.current_dt
                try:
                    if ":" in time_str:
                        parts = time_str.split(":")
                        h, m = int(parts[0]), int(parts[1])
                        s = int(parts[2]) if len(parts) > 2 else 0
                    else:
                        h, m, s = 9, 30, 0
                    self.context.current_dt = dt.datetime(
                        trade_day.year, trade_day.month, trade_day.day, h, m, s
                    )
                except Exception:
                    self.context.current_dt = dt.datetime(
                        trade_day.year, trade_day.month, trade_day.day, 9, 30, 0
                    )

                for func in self._schedule[time_str]:
                    try:
                        func(self.context)
                    except Exception as e:
                        log.error(f"[{trade_day} {time_str}] {func.__name__} 执行失败: {e}")

            # 盘后更新
            self._update_positions_value()
            equity = self.context.portfolio.total_value
            self._daily_equity.append((trade_day, equity))

            if (i + 1) % 20 == 0 or i == len(trade_days) - 1:
                ret = (equity - self.capital) / self.capital * 100
                log.info(f"[{trade_day}] 总资产: {equity:,.0f} 元，累计收益: {ret:.2f}%")

        self._print_summary()

    # -------------------------------------------------------------------------
    # 绩效汇总
    # -------------------------------------------------------------------------

    def _print_summary(self):
        """打印回测绩效汇总。"""
        if not self._daily_equity:
            return

        dates, values = zip(*self._daily_equity)
        equity_series = pd.Series(list(values), index=pd.to_datetime(list(dates)))

        total_return = (equity_series.iloc[-1] - self.capital) / self.capital
        annual_return = (1 + total_return) ** (252 / len(equity_series)) - 1

        daily_returns = equity_series.pct_change().dropna()
        # 年化因子：使用实际回测交易日天数（不超过 252）
        actual_days = max(len(equity_series), 1)
        annualize = np.sqrt(min(actual_days, 252))
        sharpe = (daily_returns.mean() / daily_returns.std() * annualize
                  if daily_returns.std() > 0 else 0.0)

        # 最大回撤
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax
        max_drawdown = drawdown.min()

        log.info("\n" + "=" * 50)
        log.info("📊 回测绩效汇总")
        log.info("=" * 50)
        log.info(f"  回测区间   : {dates[0]} → {dates[-1]}")
        log.info(f"  初始资金   : {self.capital:>12,.0f} 元")
        log.info(f"  期末资产   : {equity_series.iloc[-1]:>12,.0f} 元")
        log.info(f"  总收益率   : {total_return:>10.2%}")
        log.info(f"  年化收益率 : {annual_return:>10.2%}")
        log.info(f"  最大回撤   : {max_drawdown:>10.2%}")
        log.info(f"  夏普比率   : {sharpe:>10.2f}")
        log.info("=" * 50)

    def get_equity_curve(self) -> pd.Series:
        """返回每日总资产曲线（pd.Series）。"""
        if not self._daily_equity:
            return pd.Series(dtype=float)
        dates, values = zip(*self._daily_equity)
        return pd.Series(list(values), index=pd.to_datetime(list(dates)), name="equity")
