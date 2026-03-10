import pytest
from src.agents.confidence_calibrator import BayesianConfidenceCalibrator

class TestBayesianCalibrator:
    def setup_method(self):
        self.calibrator = BayesianConfidenceCalibrator()

    def test_default_prior_is_065(self):
        result = self.calibrator.calibrate(agent_name="log_agent", critic_score=1.0, evidence_count=10)
        assert 0.6 <= result <= 0.7

    def test_low_critic_score_reduces_confidence(self):
        high = self.calibrator.calibrate("log_agent", critic_score=0.9, evidence_count=3)
        low = self.calibrator.calibrate("log_agent", critic_score=0.3, evidence_count=3)
        assert high > low

    def test_more_evidence_increases_confidence(self):
        few = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=1)
        many = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=5)
        assert many > few

    def test_evidence_weight_has_diminishing_returns(self):
        w3 = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=3)
        w5 = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=5)
        w10 = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=10)
        assert (w5 - w3) >= (w10 - w5)

    def test_update_priors_adjusts_accuracy(self):
        self.calibrator.update_priors("log_agent", was_correct=True)
        self.calibrator.update_priors("log_agent", was_correct=True)
        self.calibrator.update_priors("log_agent", was_correct=True)
        result = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=3)
        default_result = BayesianConfidenceCalibrator().calibrate("log_agent", critic_score=0.8, evidence_count=3)
        assert result > default_result

    def test_update_priors_decreases_on_wrong(self):
        self.calibrator.update_priors("log_agent", was_correct=False)
        self.calibrator.update_priors("log_agent", was_correct=False)
        result = self.calibrator.calibrate("log_agent", critic_score=0.8, evidence_count=3)
        default_result = BayesianConfidenceCalibrator().calibrate("log_agent", critic_score=0.8, evidence_count=3)
        assert result < default_result

    def test_confidence_clamped_0_to_1(self):
        result = self.calibrator.calibrate("log_agent", critic_score=1.0, evidence_count=100)
        assert 0.0 <= result <= 1.0
        result2 = self.calibrator.calibrate("log_agent", critic_score=0.0, evidence_count=0)
        assert 0.0 <= result2 <= 1.0

    def test_breakdown_returns_all_factors(self):
        breakdown = self.calibrator.get_calibration_breakdown("log_agent", critic_score=0.8, evidence_count=3)
        assert "calibrated_confidence" in breakdown
        assert "factors" in breakdown
        assert "agent_prior" in breakdown["factors"]
        assert "critic_score" in breakdown["factors"]
        assert "evidence_weight" in breakdown["factors"]
        assert "evidence_count" in breakdown["factors"]
