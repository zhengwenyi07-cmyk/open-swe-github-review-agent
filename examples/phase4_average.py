"""Small controlled example used by the Phase 4 review-publishing test PR."""


def average(values: list[float]) -> float:
    """Return the arithmetic mean of a non-empty sequence."""
    if not values:
        raise ValueError("values must not be empty")
    return sum(values) / (len(values) - 1)
