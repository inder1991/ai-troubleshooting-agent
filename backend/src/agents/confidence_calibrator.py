"""Bayesian confidence calibration for agent findings."""

class BayesianConfidenceCalibrator:
    """Bayesian calibration: prior × critic_score × evidence_weight → posterior."""
    DEFAULT_PRIOR = 0.65

    def __init__(self):
        self.agent_priors: dict[str, float] = {}

    def calibrate(self, agent_name: str, critic_score: float, evidence_count: int) -> float:
        prior = self.agent_priors.get(agent_name, self.DEFAULT_PRIOR)
        evidence_weight = 0.5 + 0.5 * evidence_count / (1 + evidence_count)
        raw = prior * critic_score * evidence_weight
        return round(min(1.0, max(0.0, raw)), 3)

    def update_priors(self, agent_name: str, was_correct: bool):
        current = self.agent_priors.get(agent_name, self.DEFAULT_PRIOR)
        self.agent_priors[agent_name] = 0.9 * current + 0.1 * (1.0 if was_correct else 0.0)

    def get_calibration_breakdown(self, agent_name: str, critic_score: float, evidence_count: int) -> dict:
        prior = self.agent_priors.get(agent_name, self.DEFAULT_PRIOR)
        evidence_weight = 0.5 + 0.5 * evidence_count / (1 + evidence_count)
        return {
            "calibrated_confidence": self.calibrate(agent_name, critic_score, evidence_count),
            "factors": {
                "agent_prior": round(prior, 3),
                "critic_score": round(critic_score, 3),
                "evidence_weight": round(evidence_weight, 3),
                "evidence_count": evidence_count,
            },
        }
