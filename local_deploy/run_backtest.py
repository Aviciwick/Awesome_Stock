"""
run_backtest.py — 聚宽策略本地回测入口

使用方法（命令行）::

    # 基本用法
    python local_deploy/run_backtest.py

    # 自定义参数
    python local_deploy/run_backtest.py \
        --start 2023-01-01 \
        --end   2023-12-31 \
        --capital 500000 \
        --strategy nice_try

运行前准备：
    pip install -r requirements.txt
"""

import argparse
import logging
import os
import sys

# 将项目根目录加入 sys.path（使 `import nice_try` 可用）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ============================================================================
# 日志配置
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================================
# 策略补丁函数
# ============================================================================

def _patch_strategy_module(module):
    """
    将本地兼容层函数注入到已加载的策略模块命名空间，
    覆盖 jqdata / jqfactor / jqlib 中的同名符号。
    """
    from local_deploy import jq_adapter
    from local_deploy.backtest_engine import (
        log, g,
        order_value, order_target_value, order_target,
        get_orders, cancel_order,
        MarketOrderStyle, LimitOrderStyle,
    )

    # 注入数据 API
    for attr in dir(jq_adapter):
        if not attr.startswith("_"):
            setattr(module, attr, getattr(jq_adapter, attr))

    # 注入框架运行时
    module.log = log
    module.g = g
    module.order_value = order_value
    module.order_target_value = order_target_value
    module.order_target = order_target
    module.get_orders = get_orders
    module.cancel_order = cancel_order
    module.MarketOrderStyle = MarketOrderStyle
    module.LimitOrderStyle = LimitOrderStyle


def _make_initialize_wrapper(strategy_module, engine):
    """
    返回包装后的 initialize 函数：
    执行策略原始 initialize，同时将 run_daily / set_option 重定向到引擎。
    """
    original_initialize = strategy_module.initialize

    def wrapped_initialize(context):
        # 用引擎方法替换模块中的 run_daily / set_option
        strategy_module.run_daily = engine.run_daily
        strategy_module.set_option = engine.set_option
        try:
            original_initialize(context)
        except Exception as e:
            logger.error(f"initialize 执行出错: {e}")
            raise

    return wrapped_initialize


# ============================================================================
# 主函数
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="聚宽量化策略本地回测运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python local_deploy/run_backtest.py --start 2023-01-01 --end 2023-06-30
  python local_deploy/run_backtest.py --start 2023-01-01 --end 2023-12-31 --capital 1000000
        """,
    )
    parser.add_argument("--start",    default="2023-01-01", help="回测开始日期 (YYYY-MM-DD)")
    parser.add_argument("--end",      default="2023-06-30",  help="回测结束日期 (YYYY-MM-DD)")
    parser.add_argument("--capital",  default=500_000, type=float, help="初始资金（元）")
    parser.add_argument("--strategy", default="nice_try",    help="策略模块名（不含 .py）")
    parser.add_argument("--loglevel", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="日志级别")
    args = parser.parse_args()

    # 更新日志级别
    logging.getLogger().setLevel(getattr(logging, args.loglevel))

    logger.info("=" * 60)
    logger.info("聚宽量化策略本地回测系统")
    logger.info("=" * 60)
    logger.info(f"策略模块 : {args.strategy}")
    logger.info(f"回测区间 : {args.start} → {args.end}")
    logger.info(f"初始资金 : {args.capital:,.0f} 元")
    logger.info("=" * 60)

    # 1. 创建回测引擎
    from local_deploy.backtest_engine import BacktestEngine
    engine = BacktestEngine(
        start=args.start,
        end=args.end,
        capital=args.capital,
    )

    # 2. 加载策略模块前，创建 mock 模块以避免 jqdata 等依赖报错
    import sys
    import types
    
    # 创建 jqdata mock 模块
    if 'jqdata' not in sys.modules:
        jqdata = types.ModuleType('jqdata')
        sys.modules['jqdata'] = jqdata
    
    # 创建 jqfactor mock 模块
    if 'jqfactor' not in sys.modules:
        jqfactor = types.ModuleType('jqfactor')
        sys.modules['jqfactor'] = jqfactor
    
    # 创建 jqlib 及其子模块 mock
    if 'jqlib' not in sys.modules:
        jqlib = types.ModuleType('jqlib')
        sys.modules['jqlib'] = jqlib
        
        # 创建 jqlib.technical_analysis
        technical_analysis = types.ModuleType('jqlib.technical_analysis')
        sys.modules['jqlib.technical_analysis'] = technical_analysis
    
    # 现在加载策略模块
    try:
        import importlib
        strategy_mod = importlib.import_module(args.strategy)
    except ModuleNotFoundError as exc:
        logger.error(f"无法加载策略模块 '{args.strategy}': {exc}")
        logger.error("请确认策略文件存在于项目根目录，且文件名与 --strategy 参数一致。")
        sys.exit(1)

    # 3. 注入本地兼容层
    _patch_strategy_module(strategy_mod)

    # 4. 包装 initialize（重定向 run_daily）
    initialize_fn = _make_initialize_wrapper(strategy_mod, engine)

    # 5. 执行回测
    try:
        engine.run(initialize_fn=initialize_fn)
    except KeyboardInterrupt:
        logger.info("\n回测被用户中断")
    except Exception as exc:
        logger.error(f"回测执行出错: {exc}", exc_info=True)
        sys.exit(1)

    # 6. 可选：保存权益曲线
    equity = engine.get_equity_curve()
    if not equity.empty:
        out_path = os.path.join(_ROOT, "backtest_results", "equity_curve.csv")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        equity.to_csv(out_path)
        logger.info(f"权益曲线已保存到: {out_path}")


if __name__ == "__main__":
    main()
