"""Q9 compliant source — paired Hypothesis test exists in same fixture set.

Pretend-path: backend/src/learning/calibrator.py
"""
def calibrate(score: float) -> float:
    return max(0.0, min(1.0, score))
