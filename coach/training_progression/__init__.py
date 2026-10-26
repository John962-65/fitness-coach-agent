"""P5-C1：确定性下一次训练上下文与进阶候选。"""
from .context_service import NextTrainingContext, build_next_training_context
from .progression_service import get_next_training_options

__all__ = [
    "NextTrainingContext", "build_next_training_context",
    "get_next_training_options",
]
