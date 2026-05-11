"""
Layer 3 — Governance: Alpha Lifecycle Engine

所有 alpha 都会衰减。系统必须跟踪 alpha 从出生到衰退的全生命周期。
"""

from datetime import datetime
from core.protocols import AlphaLifecycle, AlphaStatus


class AlphaLifecycleEngine:
    """Alpha 生命周期管理引擎"""

    def __init__(self):
        self.alphas: dict[str, AlphaLifecycle] = {}

    def register_alpha(self, alpha_id: str, peak_sharpe: float = 0):
        """注册新的 alpha 策略"""
        self.alphas[alpha_id] = AlphaLifecycle(
            alpha_id=alpha_id,
            peak_sharpe=peak_sharpe,
            current_sharpe=peak_sharpe,
            status=AlphaStatus.BIRTH,
        )

    def update_performance(self, alpha_id: str, current_sharpe: float):
        """更新 alpha 表现"""
        alpha = self.alphas.get(alpha_id)
        if not alpha:
            return

        alpha.current_sharpe = current_sharpe
        alpha.decay_score = max(0, (alpha.peak_sharpe - current_sharpe) / max(0.01, alpha.peak_sharpe))

        # 状态转换
        if alpha.decay_score > 0.5:
            alpha.status = AlphaStatus.DECAYING
        if alpha.decay_score > 0.8:
            alpha.status = AlphaStatus.DEPRECATED
        if current_sharpe < 0:
            alpha.status = AlphaStatus.RETIRED

    def get_decaying_alphas(self) -> list[AlphaLifecycle]:
        """获取所有正在衰退的 alpha"""
        return [a for a in self.alphas.values() if a.status in [AlphaStatus.DECAYING, AlphaStatus.DEPRECATED]]

    def should_retire(self, alpha_id: str) -> bool:
        """判断 alpha 是否应该退休"""
        alpha = self.alphas.get(alpha_id)
        if not alpha:
            return True
        return alpha.status in [AlphaStatus.DEPRECATED, AlphaStatus.RETIRED]
