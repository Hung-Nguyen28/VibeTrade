"""P4 — Deterministic Research Team & Explainable Personas (VibeTrade v1.1)."""

from src.vibetrade.research.analysts import (
    FocusFeatureVector,
    MicrostructureLiquidityMetrics,
    TrendMomentumMetrics,
    VolumeVolatilityMetrics,
    extract_analysts_features,
)
from src.vibetrade.research.crucible import CrucibleEngine
from src.vibetrade.research.models import (
    EvidenceItem,
    ResearchHistorySnapshot,
    ResearchReport,
)
from src.vibetrade.research.researchers import (
    BearResearcher,
    BullResearcher,
    ResearcherScore,
)

__all__ = [
    "BearResearcher",
    "BullResearcher",
    "CrucibleEngine",
    "EvidenceItem",
    "FocusFeatureVector",
    "MicrostructureLiquidityMetrics",
    "ResearchHistorySnapshot",
    "ResearchReport",
    "ResearcherScore",
    "TrendMomentumMetrics",
    "VolumeVolatilityMetrics",
    "extract_analysts_features",
]
