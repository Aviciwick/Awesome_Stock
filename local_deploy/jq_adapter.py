"""
jq_adapter.py — 聚宽(JoinQuant)平台 API 本地兼容层

将聚宽平台专有 API 映射到本地免费数据源（AKShare），
使 nice_try.py 等聚宽策略无需修改即可在本地环境执行。

数据源优先级：
  1. AKShare（免费，主要数据源）
  2. 内存 / 磁盘缓存（减少重复网络请求）

使用方法：
    from local_deploy.jq_adapter import *
"""

import os
import datetime as dt
import functools
import logging
import warnings
from typing import Dict, List, Optional, Union

# 彻底禁用所有代理
proxy_keys = [k for k in os.environ if 'proxy' in k.lower()]
for key in proxy_keys:
    del os.environ[key]

import numpy as np
import pandas as pd

# 禁用 requests 的代理
try:
    import requests
    requests.Session().trust_env = False
except:
    pass

# 可选依赖：AKShare
try:
    import akshare as ak
    _AKSHARE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _AKSHARE_AVAILABLE = False
    warnings.warn(
        "akshare 未安装，数据获取功能将不可用。\n"
        "请运行: pip install akshare",
        ImportWarning,
        stacklevel=2,
    )

logger = logging.getLogger(__name__)

# ============================================================================
# 内存缓存辅助
# ============================================================================

_cache: Dict[str, object] = {}


def _cache_key(*args, **kwargs) -> str:
    return str(args) + str(sorted(kwargs.items()))


def _cached(func):
    """为无副作用的数据获取函数提供内存级缓存。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = func.__name__ + _cache_key(*args, **kwargs)
        if key not in _cache:
            _cache[key] = func(*args, **kwargs)
        return _cache[key]

    return wrapper


def clear_cache():
    """清空内存缓存（每个交易日开始时调用）。"""
    _cache.clear()


# ============================================================================
# 代码格式转换工具
# ============================================================================

def _to_akshare_code(jq_code: str) -> str:
    """
    将聚宽格式代码（'000001.XSHE'）转换为 AKShare 格式（'000001'）。
    对于指数代码（XSHG/XSHE），保留 6 位纯数字部分。
    """
    if "." in jq_code:
        return jq_code.split(".")[0]
    return jq_code


def _to_jq_code(raw_code: str) -> str:
    """
    将 6 位原始代码转换为聚宽格式（'000001' → '000001.XSHE'）。
    沪市：6 字头 → XSHG；深市：0/2/3 字头 → XSHE。
    """
    if "." in raw_code:
        return raw_code
    if raw_code.startswith("6"):
        return f"{raw_code}.XSHG"
    return f"{raw_code}.XSHE"


def normalize_code(code: str) -> str:
    """标准化为聚宽格式代码（兼容接口）。"""
    return _to_jq_code(_to_akshare_code(code))


# ============================================================================
# 交易日历
# ============================================================================

@_cached
def _get_trade_calendar() -> pd.DatetimeIndex:
    """从 AKShare 获取 A 股交易日历（全量历史）。"""
    if not _AKSHARE_AVAILABLE:
        raise RuntimeError("akshare 未安装")
    df = ak.tool_trade_date_hist_sina()
    dates = pd.to_datetime(df.iloc[:, 0])
    return pd.DatetimeIndex(sorted(dates))


def get_trade_days(
    start_date: Optional[Union[str, dt.date]] = None,
    end_date: Optional[Union[str, dt.date]] = None,
    count: Optional[int] = None,
) -> List[dt.date]:
    """
    获取交易日列表。

    接口与聚宽 ``get_trade_days`` 保持一致：
      - 若提供 ``count``，返回截至 ``end_date`` 最近 ``count`` 个交易日。
      - 否则返回 [start_date, end_date] 范围内全部交易日。
    """
    calendar = _get_trade_calendar()

    def _to_date(d) -> dt.date:
        if d is None:
            return dt.date.today()
        if isinstance(d, dt.datetime):
            return d.date()
        if isinstance(d, dt.date):
            return d
        return pd.Timestamp(d).date()

    if count is not None:
        ed = _to_date(end_date)
        mask = calendar <= pd.Timestamp(ed)
        days = calendar[mask][-count:]
    else:
        sd = _to_date(start_date)
        ed = _to_date(end_date)
        mask = (calendar >= pd.Timestamp(sd)) & (calendar <= pd.Timestamp(ed))
        days = calendar[mask]

    return [d.date() for d in days]


def get_shifted_date(date, days: int, days_type: str = "T") -> dt.date:
    """
    将日期向前/后移动指定天数。

    days_type:
      'T' — 交易日偏移（默认）
      'D' — 自然日偏移
    """
    if isinstance(date, str):
        date = pd.Timestamp(date).date()
    elif isinstance(date, dt.datetime):
        date = date.date()

    if days_type == "D":
        return date + dt.timedelta(days=days)

    calendar = _get_trade_calendar()
    idx = calendar.searchsorted(pd.Timestamp(date))
    target_idx = idx + days
    target_idx = max(0, min(target_idx, len(calendar) - 1))
    return calendar[target_idx].date()


# ============================================================================
# 证券信息
# ============================================================================

class SecurityInfo:
    """模拟聚宽 ``SecurityInfo`` 对象。"""

    def __init__(
        self,
        code: str,
        display_name: str = "",
        name: str = "",
        start_date: Optional[dt.date] = None,
        end_date: Optional[dt.date] = None,
        type: str = "stock",
        concepts: Optional[List[Dict]] = None,
    ):
        self.code = code
        self.display_name = display_name or name or code
        self.name = name or display_name or code
        self.start_date = start_date or dt.date(2000, 1, 1)
        self.end_date = end_date or dt.date(2099, 12, 31)
        self.type = type
        self.concepts = concepts or []


@_cached
def _get_stock_name_map() -> Dict[str, str]:
    """返回 {6位代码: 股票名称} 字典。"""
    if not _AKSHARE_AVAILABLE:
        return {}
    df = ak.stock_info_a_code_name()
    return dict(zip(df["code"].astype(str).str.zfill(6), df["name"]))


def get_security_info(code: str, date: Optional[str] = None) -> SecurityInfo:
    """
    获取证券基本信息。

    Args:
        code: 聚宽格式代码（如 '000001.XSHE'）。
        date: 可选，查询日期（本地模式暂忽略，保持接口兼容）。

    Returns:
        SecurityInfo 对象，含 display_name、start_date 等属性。
    """
    raw = _to_akshare_code(code)
    name_map = _get_stock_name_map()
    name = name_map.get(raw, raw)

    # 尝试获取上市日期
    start_date = dt.date(2000, 1, 1)
    try:
        if _AKSHARE_AVAILABLE and raw.isdigit():
            info_df = ak.stock_individual_info_em(symbol=raw)
            if info_df is not None and not info_df.empty:
                row = info_df[info_df.iloc[:, 0].str.contains("上市时间|上市日期", na=False)]
                if not row.empty:
                    val = row.iloc[0, 1]
                    if val and str(val) not in ("--", "None", "nan"):
                        start_date = pd.Timestamp(val).date()
    except Exception:
        pass

    return SecurityInfo(
        code=code,
        display_name=name,
        name=name,
        start_date=start_date,
    )


# ============================================================================
# 全量证券列表
# ============================================================================

@_cached
def get_all_securities(security_type: str = "stock", date: Optional[str] = None) -> pd.DataFrame:
    """
    获取所有上市证券列表（对标聚宽 ``get_all_securities``）。

    Returns:
        以 JQ 格式代码为索引的 DataFrame，含 display_name、start_date 列。
    """
    if not _AKSHARE_AVAILABLE:
        return pd.DataFrame(columns=["display_name", "start_date"])

    df = ak.stock_info_a_code_name()
    df = df.rename(columns={"code": "raw_code", "name": "display_name"})
    df["raw_code"] = df["raw_code"].astype(str).str.zfill(6)
    df.index = df["raw_code"].apply(_to_jq_code)
    df["start_date"] = dt.date(2000, 1, 1)
    return df[["display_name", "start_date"]]


# ============================================================================
# 历史行情数据
# ============================================================================

def _fetch_daily_hist(raw_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    从 AKShare 获取单只股票日线数据，返回标准化 DataFrame。

    列名：date, open, close, high, low, volume, money, high_limit, low_limit
    """
    if not _AKSHARE_AVAILABLE:
        return pd.DataFrame()

    try:
        df = ak.stock_zh_a_hist(
            symbol=raw_code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
        if df is None or df.empty:
            return pd.DataFrame()

        col_map = {
            "日期": "date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "money",
            "涨跌幅": "pct_change",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df["date"] = pd.to_datetime(df["date"])

        # 计算涨跌停价（A 股规则：±10%，ST ±5%）
        df = df.sort_values("date").reset_index(drop=True)
        if "pct_change" not in df.columns:
            df["pct_change"] = df["close"].pct_change() * 100

        # 以收盘价估算涨跌停（前收盘的 ±10%）
        prev_close = df["close"].shift(1)
        df["high_limit"] = (prev_close * 1.10).round(2)
        df["low_limit"] = (prev_close * 0.90).round(2)

        return df

    except Exception as e:
        logger.warning(f"获取 {raw_code} 历史数据失败: {e}")
        return pd.DataFrame()


def _fetch_index_hist(raw_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取指数历史日线数据。"""
    if not _AKSHARE_AVAILABLE:
        return pd.DataFrame()
    try:
        symbol_map = {
            "000001": "sh000001",
            "399001": "sz399001",
            "000300": "sh000300",
            "000905": "sh000905",
        }
        symbol = symbol_map.get(raw_code, f"sh{raw_code}")
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(
            columns={"date": "date", "open": "open", "high": "high",
                     "low": "low", "close": "close", "volume": "volume"}
        )
        df["date"] = pd.to_datetime(df["date"])
        mask = (df["date"] >= pd.Timestamp(start_date)) & (df["date"] <= pd.Timestamp(end_date))
        return df[mask].reset_index(drop=True)
    except Exception as e:
        logger.warning(f"获取指数 {raw_code} 历史数据失败: {e}")
        return pd.DataFrame()


def get_price(
    security: Union[str, List[str]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    frequency: str = "daily",
    fields: Optional[List[str]] = None,
    count: Optional[int] = None,
    panel: bool = True,
    fill_paused: bool = True,
    skip_paused: bool = False,
) -> pd.DataFrame:
    """
    获取历史行情数据（对标聚宽 ``get_price``）。

    与聚宽的差异：
      - 仅支持日线频率（frequency='daily'/'1d'）。
      - panel 参数已忽略，始终返回长格式 DataFrame（含 code 列）。
      - count 优先于 start_date，以 end_date 为基准向前取 count 条。

    Returns:
        DataFrame，列含 code, date, open, close, high, low, volume, money,
        high_limit, low_limit（视 fields 参数裁剪）。
    """
    if isinstance(security, str):
        security = [security]

    # 确定日期范围
    ed = pd.Timestamp(end_date) if end_date else pd.Timestamp.today()
    if count is not None:
        trade_days = get_trade_days(end_date=ed.date(), count=count + 5)
        if len(trade_days) < 1:
            return pd.DataFrame()
        sd = pd.Timestamp(trade_days[0])
    else:
        sd = pd.Timestamp(start_date) if start_date else pd.Timestamp("2020-01-01")

    sd_str = sd.strftime("%Y-%m-%d")
    ed_str = ed.strftime("%Y-%m-%d")

    all_frames = []
    for jq_code in security:
        raw = _to_akshare_code(jq_code)
        # 判断是否为指数
        is_index = jq_code.endswith(".XSHG") and not raw.startswith("6")
        if is_index or raw.startswith(("0000", "3990", "0003", "0009")):
            df = _fetch_index_hist(raw, sd_str, ed_str)
        else:
            df = _fetch_daily_hist(raw, sd_str, ed_str)
        if df.empty:
            continue
        df["code"] = jq_code
        all_frames.append(df)

    if not all_frames:
        return pd.DataFrame()

    result = pd.concat(all_frames, ignore_index=True)
    result = result.sort_values(["code", "date"]).reset_index(drop=True)

    # 按 count 裁剪（每只股票取最后 count 行）
    if count is not None:
        result = (
            result.groupby("code", group_keys=False)
            .apply(lambda g: g.tail(count))
            .reset_index(drop=True)
        )

    if fields:
        keep = ["code", "date"] + [f for f in fields if f in result.columns]
        result = result[keep]

    return result


def attribute_history(
    security: str,
    count: int,
    unit: str = "1d",
    fields: Optional[List[str]] = None,
    skip_paused: bool = True,
    df: bool = True,
) -> Union[pd.DataFrame, Dict[str, np.ndarray]]:
    """
    获取单只股票历史数据（对标聚宽 ``attribute_history``）。

    Args:
        security: 聚宽格式代码。
        count: 获取的历史 K 线条数（不含当日）。
        unit: 周期（仅支持 '1d'）。
        fields: 字段列表。
        skip_paused: 是否跳过停牌日（本地模式：启用时删除无成交量行）。
        df: True 返回 DataFrame，False 返回 {field: np.ndarray} 字典。

    Returns:
        DataFrame 或字典，行/数组长度恰好为 count（不足时补 NaN）。
    """
    today = dt.date.today()
    trade_days = get_trade_days(end_date=today, count=count + 30)
    if not trade_days:
        return pd.DataFrame() if df else {}

    start = trade_days[0]
    end = trade_days[-1]
    result_df = get_price(
        security,
        start_date=str(start),
        end_date=str(end),
        fields=fields,
        count=count + 10,
    )

    if result_df.empty:
        empty = pd.DataFrame(index=range(count), columns=fields or [])
        return empty if df else {f: np.full(count, np.nan) for f in (fields or [])}

    # 删除 code 列（attribute_history 不含该列）
    if "code" in result_df.columns:
        result_df = result_df.drop(columns=["code"])

    if "date" in result_df.columns:
        result_df = result_df.set_index("date")

    if skip_paused and "volume" in result_df.columns:
        result_df = result_df[result_df["volume"] > 0]

    result_df = result_df.tail(count)

    if not df:
        return {col: result_df[col].values for col in result_df.columns if col in (fields or result_df.columns)}

    return result_df


# ============================================================================
# 实时行情（CurrentData）
# ============================================================================

class _StockCurrentData:
    """
    模拟聚宽 ``CurrentData[stock]`` 对象。
    回测模式下以最近交易日收盘数据填充；实盘模式下使用 AKShare 实时数据。
    """

    def __init__(
        self,
        code: str,
        name: str = "",
        last_price: float = 0.0,
        high_limit: float = 0.0,
        low_limit: float = 0.0,
        day_open: float = 0.0,
        is_st: bool = False,
        paused: bool = False,
    ):
        self.code = code
        self.name = name
        self.last_price = last_price
        self.high_limit = high_limit
        self.low_limit = low_limit
        self.day_open = day_open
        self.is_st = is_st
        self.paused = paused


class _CurrentDataProxy(dict):
    """
    dict 子类，访问不存在的键时返回空的 ``_StockCurrentData``，
    与聚宽行为一致（避免 KeyError）。
    """

    def __missing__(self, key):
        return _StockCurrentData(code=key)


def get_current_data() -> _CurrentDataProxy:
    """
    获取当前时间点的行情快照（对标聚宽 ``get_current_data``）。

    本地模式下拉取最近交易日行情作为替代。

    Returns:
        可按股票代码索引的字典，值为 ``_StockCurrentData``。
    """
    proxy = _CurrentDataProxy()
    if not _AKSHARE_AVAILABLE:
        return proxy

    try:
        df = ak.stock_zh_a_spot_em()
        col_map = {
            "代码": "code",
            "名称": "name",
            "最新价": "last_price",
            "涨停": "high_limit",
            "跌停": "low_limit",
            "今开": "day_open",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "code" not in df.columns:
            return proxy

        for _, row in df.iterrows():
            raw = str(row.get("code", "")).zfill(6)
            jq = _to_jq_code(raw)
            name = str(row.get("name", ""))
            is_st = "ST" in name.upper() or "*ST" in name.upper()
            paused = float(row.get("last_price", 0) or 0) == 0
            proxy[jq] = _StockCurrentData(
                code=jq,
                name=name,
                last_price=float(row.get("last_price", 0) or 0),
                high_limit=float(row.get("high_limit", 0) or 0),
                low_limit=float(row.get("low_limit", 0) or 0),
                day_open=float(row.get("day_open", 0) or 0),
                is_st=is_st,
                paused=paused,
            )
    except Exception as e:
        logger.warning(f"获取实时行情失败: {e}")

    return proxy


# ============================================================================
# 估值数据
# ============================================================================

def get_valuation(
    security: Union[str, List[str]],
    start_date: Optional[Union[str, dt.date]] = None,
    end_date: Optional[Union[str, dt.date]] = None,
    fields: Optional[List[str]] = None,
    count: Optional[int] = None,
) -> pd.DataFrame:
    """
    获取估值数据（对标聚宽 ``get_valuation``）。

    本地实现通过 AKShare ``stock_a_lg_indicator`` 获取基本估值指标。
    支持字段：pe_ratio, pb_ratio, market_cap, circulating_market_cap, turnover_ratio。

    Returns:
        DataFrame，含 code、date 及所请求字段。
    """
    if isinstance(security, str):
        security = [security]

    if not _AKSHARE_AVAILABLE:
        return pd.DataFrame(columns=["code", "date"] + (fields or []))

    if end_date is None:
        end_date = dt.date.today()
    if isinstance(end_date, dt.datetime):
        end_date = end_date.date()
    if isinstance(end_date, str):
        end_date = pd.Timestamp(end_date).date()

    results = []
    for jq_code in security:
        raw = _to_akshare_code(jq_code)
        try:
            df = ak.stock_a_lg_indicator(symbol=raw)
            if df is None or df.empty:
                continue
            df = df.rename(
                columns={
                    "trade_date": "date",
                    "pe": "pe_ratio",
                    "pb": "pb_ratio",
                    "总市值": "market_cap",
                    "流通市值": "circulating_market_cap",
                    "换手率": "turnover_ratio",
                }
            )
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["date"] <= pd.Timestamp(end_date)]
            if count:
                df = df.tail(count)
            df["code"] = jq_code
            results.append(df)
        except Exception as e:
            logger.debug(f"获取 {jq_code} 估值数据失败: {e}")

    if not results:
        return pd.DataFrame(columns=["code", "date"] + (fields or []))

    out = pd.concat(results, ignore_index=True)
    if fields:
        keep = ["code", "date"] + [f for f in fields if f in out.columns]
        out = out[keep]
    return out


# ============================================================================
# 财务数据（简化版）
# ============================================================================

def get_fundamentals(query_object=None, date: Optional[str] = None) -> pd.DataFrame:
    """
    获取财务基本面数据（对标聚宽 ``get_fundamentals``）。

    本地实现仅支持通过 ``query(valuation)`` 形式的简单查询。
    受 AKShare 接口限制，不支持完整的 SQLAlchemy 风格查询对象；
    建议用 ``get_valuation`` 代替。

    Returns:
        空 DataFrame（含基本列），后续版本将扩展实现。
    """
    logger.warning(
        "get_fundamentals 在本地模式下功能受限，建议改用 get_valuation。"
    )
    return pd.DataFrame()


# ============================================================================
# 资金流数据
# ============================================================================

def get_money_flow(
    security: Union[str, List[str]],
    start_date: Optional[Union[str, dt.date]] = None,
    end_date: Optional[Union[str, dt.date]] = None,
    fields: Optional[List[str]] = None,
    count: Optional[int] = None,
) -> pd.DataFrame:
    """
    获取个股资金流向数据（对标聚宽 ``get_money_flow``）。

    返回字段（AKShare 可用）：
      date, code, net_amount_main（主力净流入额，万元），
      net_pct_main（主力净流入占比，%）

    注意：AKShare 的资金流数据与聚宽字段名不完全一致，
    使用时请参考下方映射说明。
    """
    if isinstance(security, str):
        security = [security]

    if not _AKSHARE_AVAILABLE:
        return pd.DataFrame()

    if end_date is None:
        end_date = dt.date.today()
    if isinstance(end_date, str):
        end_date = pd.Timestamp(end_date).date()
    if isinstance(end_date, dt.datetime):
        end_date = end_date.date()

    if start_date is None:
        start_date = end_date - dt.timedelta(days=10)
    if isinstance(start_date, str):
        start_date = pd.Timestamp(start_date).date()

    results = []
    for jq_code in security:
        raw = _to_akshare_code(jq_code)
        try:
            df = ak.stock_individual_fund_flow(
                stock=raw,
                market="sh" if jq_code.endswith("XSHG") else "sz",
            )
            if df is None or df.empty:
                continue
            df = df.rename(
                columns={
                    "日期": "date",
                    "主力净流入-净额": "net_amount_main",
                    "主力净流入-净占比": "net_pct_main",
                    "超大单净流入-净额": "net_amount_xl",
                    "大单净流入-净额": "net_amount_l",
                    "中单净流入-净额": "net_amount_m",
                    "小单净流入-净额": "net_amount_s",
                }
            )
            df["date"] = pd.to_datetime(df["date"])
            mask = (df["date"] >= pd.Timestamp(start_date)) & (
                df["date"] <= pd.Timestamp(end_date)
            )
            df = df[mask]
            df["code"] = jq_code
            results.append(df)
        except Exception as e:
            logger.debug(f"获取 {jq_code} 资金流数据失败: {e}")

    if not results:
        return pd.DataFrame()

    out = pd.concat(results, ignore_index=True)
    if fields:
        keep = ["code", "date"] + [f for f in fields if f in out.columns]
        out = out[keep]
    return out


# ============================================================================
# 集合竞价数据
# ============================================================================

def get_call_auction(
    security: Union[str, List[str]],
    start_date: Optional[Union[str, dt.date]] = None,
    end_date: Optional[Union[str, dt.date]] = None,
    fields: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    获取集合竞价数据（对标聚宽 ``get_call_auction``）。

    本地实现：AKShare 暂无完整集合竞价历史接口，
    此函数返回空 DataFrame 并发出警告。
    如需精确集合竞价数据，请使用 JQData 本地版（付费）。

    Returns:
        空 DataFrame，含 code, date, time, current, volume 列。
    """
    logger.warning(
        "get_call_auction：AKShare 暂不支持历史集合竞价数据，返回空 DataFrame。\n"
        "依赖集合竞价数据的逻辑（如 sell_limit_down）在本地回测中将跳过。"
    )
    return pd.DataFrame(columns=["code", "date", "time", "current", "volume"])


# ============================================================================
# 因子数据（简化版）
# ============================================================================

def get_factor_values(
    securities: List[str],
    factors: Union[str, List[str]],
    end_date: Optional[Union[str, dt.date]] = None,
    count: int = 1,
) -> Dict[str, pd.DataFrame]:
    """
    获取聚宽因子库数据（对标聚宽 ``get_factor_values``）。

    本地实现支持以下因子（通过 AKShare 计算）：
      - VOL5: 5 日平均换手率（通过 get_valuation 获取）

    其他因子返回 NaN 填充的 DataFrame，并发出警告。

    Returns:
        {factor_name: DataFrame}，DataFrame 行为日期，列为代码。
    """
    if isinstance(factors, str):
        factors = [factors]

    result = {}
    for factor in factors:
        df = pd.DataFrame(
            index=[end_date],
            columns=securities,
            dtype=float,
        )
        df.index = pd.to_datetime(df.index)

        if factor == "VOL5" and _AKSHARE_AVAILABLE:
            for jq_code in securities:
                try:
                    val_df = get_valuation(
                        jq_code,
                        end_date=end_date,
                        fields=["turnover_ratio"],
                        count=5,
                    )
                    if not val_df.empty and "turnover_ratio" in val_df.columns:
                        mean_vol5 = val_df["turnover_ratio"].mean()
                        df.loc[df.index[0], jq_code] = mean_vol5
                except Exception:
                    pass
        else:
            logger.warning(f"因子 '{factor}' 在本地模式下暂不支持，返回 NaN。")

        result[factor] = df

    return result


# ============================================================================
# 框架级工具函数（供 backtest_engine 使用）
# ============================================================================

def get_index_stocks(index_symbol: str, date: Optional[str] = None) -> List[str]:
    """
    获取指数成分股列表（如 '000300.XSHG' → 沪深 300 成分股）。

    Returns:
        聚宽格式代码列表。
    """
    if not _AKSHARE_AVAILABLE:
        return []

    raw = _to_akshare_code(index_symbol)
    index_map = {
        "000300": "000300",
        "000905": "000905",
        "000852": "000852",
        "399006": "399006",
    }
    symbol = index_map.get(raw, raw)

    try:
        df = ak.index_stock_cons_weight_csindex(symbol=symbol)
        if df is None or df.empty:
            return []
        code_col = next((c for c in df.columns if "成分券代码" in c or "code" in c.lower()), None)
        if not code_col:
            return []
        return [_to_jq_code(str(c).zfill(6)) for c in df[code_col]]
    except Exception as e:
        logger.warning(f"获取指数 {index_symbol} 成分股失败: {e}")
        return []


# ============================================================================
# 聚宽框架占位函数（由 backtest_engine 注入实现）
# ============================================================================

def set_option(key: str, value=None):
    """占位：接受并忽略 set_option 调用（由 backtest_engine 覆盖）。"""
    logger.debug(f"set_option({key}={value}) — 本地模式下忽略")


def run_daily(func, time: str, reference_security: str = ""):
    """占位：由 backtest_engine.BacktestEngine 在 initialize 中注入真实实现。"""
    logger.debug(f"run_daily 占位 — {func.__name__} @ {time}（由 backtest_engine 管理）")
