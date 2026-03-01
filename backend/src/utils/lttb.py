"""LTTB (Largest Triangle Three Buckets) downsampling for time-series data.

Hard rule: Never send more than 150 data points per line to the frontend.
"""
from __future__ import annotations

MAX_POINTS = 150


def lttb_downsample(
    data: list[tuple[float, float]],
    threshold: int = MAX_POINTS,
) -> list[tuple[float, float]]:
    """Downsample time-series data using LTTB algorithm.

    Args:
        data: List of (timestamp, value) tuples, sorted by timestamp.
        threshold: Maximum number of output points.

    Returns:
        Downsampled list of (timestamp, value) tuples.
    """
    length = len(data)
    if threshold >= length or threshold < 3:
        return list(data)

    sampled: list[tuple[float, float]] = []

    # Always keep first point
    sampled.append(data[0])

    # Bucket size (excluding first and last points)
    bucket_size = (length - 2) / (threshold - 2)

    a = 0  # Index of previously selected point

    for i in range(1, threshold - 1):
        # Calculate bucket boundaries
        bucket_start = int((i - 1) * bucket_size) + 1
        bucket_end = int(i * bucket_size) + 1
        bucket_end = min(bucket_end, length - 1)

        # Calculate next bucket average for triangle area calculation
        next_bucket_start = int(i * bucket_size) + 1
        next_bucket_end = int((i + 1) * bucket_size) + 1
        next_bucket_end = min(next_bucket_end, length)

        avg_x = sum(data[j][0] for j in range(next_bucket_start, next_bucket_end)) / max(1, next_bucket_end - next_bucket_start)
        avg_y = sum(data[j][1] for j in range(next_bucket_start, next_bucket_end)) / max(1, next_bucket_end - next_bucket_start)

        # Find point in current bucket with largest triangle area
        max_area = -1.0
        max_idx = bucket_start

        point_a = data[a]

        for j in range(bucket_start, bucket_end):
            # Triangle area using cross product
            area = abs(
                (point_a[0] - avg_x) * (data[j][1] - point_a[1])
                - (point_a[0] - data[j][0]) * (avg_y - point_a[1])
            ) * 0.5

            if area > max_area:
                max_area = area
                max_idx = j

        sampled.append(data[max_idx])
        a = max_idx

    # Always keep last point
    sampled.append(data[-1])

    return sampled
