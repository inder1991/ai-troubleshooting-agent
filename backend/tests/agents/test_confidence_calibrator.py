"""Task 2.3 — deterministic confidence formula (no LLM critic_score)."""
import inspect
from dataclasses import replace

from src.agents.confidence_calibrator import (
    ConfidenceInputs,
    compute_confidence,
)


class TestComputeConfidence:
    def test_confidence_pure_function_of_evidence_inputs(self):
        inputs = ConfidenceInputs(
            evidence_pin_count=4,
            source_diversity=3,   # logs+metrics+k8s
            baseline_delta_pct=85,
            contradiction_count=0,
            signature_match=False,
            topology_path_length=2,
        )
        c1 = compute_confidence(inputs)
        c2 = compute_confidence(inputs)
        assert c1 == c2                    # determinism
        # NOTE: the plan's Step-1 assertion was `0.5 <= c1 <= 0.85` but the
        # plan's Step-2 formula yields ~0.956 for these inputs. The Step-2
        # formula is the contract (explicit numbers), so the band here
        # reflects the formula's actual output, not the Step-1 guess.
        assert 0.9 <= c1 <= 1.0

    def test_contradictions_dominate(self):
        base = ConfidenceInputs(
            evidence_pin_count=4,
            source_diversity=3,
            baseline_delta_pct=85,
            contradiction_count=0,
            signature_match=False,
            topology_path_length=2,
        )
        with_contra = replace(base, contradiction_count=2)
        assert compute_confidence(with_contra) < compute_confidence(base) - 0.3

    def test_signature_match_boosts_only_with_evidence(self):
        no_evidence = ConfidenceInputs(
            evidence_pin_count=0,
            source_diversity=0,
            baseline_delta_pct=0,
            contradiction_count=0,
            signature_match=True,
            topology_path_length=0,
        )
        # signature alone is weak — must stay below a high-confidence band
        assert compute_confidence(no_evidence) < 0.4

    def test_critic_score_not_in_signature(self):
        sig = inspect.signature(compute_confidence)
        assert "critic_score" not in sig.parameters

    def test_confidence_clamped_to_0_1(self):
        # pile on positive factors
        boosted = ConfidenceInputs(
            evidence_pin_count=100,
            source_diversity=100,
            baseline_delta_pct=10_000,
            contradiction_count=0,
            signature_match=True,
            topology_path_length=5,
        )
        c_hi = compute_confidence(boosted)
        assert 0.0 <= c_hi <= 1.0
        # pile on negative factors
        crashed = ConfidenceInputs(
            evidence_pin_count=0,
            source_diversity=0,
            baseline_delta_pct=0,
            contradiction_count=100,
            signature_match=False,
            topology_path_length=0,
        )
        c_lo = compute_confidence(crashed)
        assert 0.0 <= c_lo <= 1.0

    def test_more_pins_raises_confidence_monotonically_until_saturation(self):
        seq = []
        for k in (0, 1, 2, 3, 4, 5, 10):
            inp = ConfidenceInputs(
                evidence_pin_count=k,
                source_diversity=2,
                baseline_delta_pct=50,
                contradiction_count=0,
                signature_match=False,
                topology_path_length=1,
            )
            seq.append(compute_confidence(inp))
        # monotonically non-decreasing
        for i in range(1, len(seq)):
            assert seq[i] >= seq[i - 1]

    def test_diversity_raises_confidence(self):
        low = ConfidenceInputs(4, 1, 50, 0, False, 1)
        high = ConfidenceInputs(4, 3, 50, 0, False, 1)
        assert compute_confidence(high) > compute_confidence(low)

    def test_baseline_delta_below_floor_adds_nothing(self):
        # 15% is the baseline-noise floor; at or below the floor, delta adds 0.
        under = ConfidenceInputs(4, 3, 10, 0, False, 1)
        at = ConfidenceInputs(4, 3, 15, 0, False, 1)
        assert compute_confidence(under) == compute_confidence(at)

    def test_baseline_delta_scales_up_to_saturation(self):
        mid = ConfidenceInputs(4, 3, 50, 0, False, 1)
        hi = ConfidenceInputs(4, 3, 100, 0, False, 1)
        saturated = ConfidenceInputs(4, 3, 500, 0, False, 1)
        assert compute_confidence(hi) > compute_confidence(mid)
        # beyond 100% delta the contribution saturates
        assert compute_confidence(saturated) == compute_confidence(hi)

    def test_signature_match_plus_evidence_exceeds_no_signature(self):
        no_sig = ConfidenceInputs(4, 3, 50, 0, False, 1)
        with_sig = replace(no_sig, signature_match=True)
        assert compute_confidence(with_sig) > compute_confidence(no_sig)

    def test_topology_path_bonus(self):
        without = ConfidenceInputs(4, 3, 50, 0, False, 0)
        with_path = ConfidenceInputs(4, 3, 50, 0, False, 2)
        assert compute_confidence(with_path) > compute_confidence(without)


class TestConfidenceInputsShape:
    def test_inputs_dataclass_has_exact_fields(self):
        fields = {
            f.name for f in ConfidenceInputs.__dataclass_fields__.values()
        }
        assert fields == {
            "evidence_pin_count",
            "source_diversity",
            "baseline_delta_pct",
            "contradiction_count",
            "signature_match",
            "topology_path_length",
        }
