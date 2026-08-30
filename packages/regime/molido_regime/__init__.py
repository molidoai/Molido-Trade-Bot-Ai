from molido_regime.engine import MarketRegimeEngine, REGIMES

try:
    # numpy/scikit-learn are only guaranteed present where the ML signal is
    # actually used (trading-engine) -- not a hard dependency of this package.
    from molido_regime.ml_engine import MLVolatilityDetector, get_default_detector
except ImportError:  # pragma: no cover
    MLVolatilityDetector = None  # type: ignore
    get_default_detector = None  # type: ignore

__all__ = ["MarketRegimeEngine", "REGIMES", "MLVolatilityDetector", "get_default_detector"]
