"""Q9 violation — learning/ source file with no paired Hypothesis test.

Pretend-path: backend/src/learning/calibrator.py
"""
def calibrate(score: float) -> float:
    return max(0.0, min(1.0, score))
