"""Pure war analytics math helpers."""

from typing import Optional


def average_medals_per_deck(win_rate: float) -> float:
    """Get the average medals per deck value at the specified PvP win rate."""
    return (-25 * win_rate**3) + (25 * win_rate**2) + (125 * win_rate) + 100


def calculate_win_rate_from_average_medals(avg_medals_per_deck: float) -> Optional[float]:
    """Estimate the win rate needed to produce a medals-per-deck value."""
    min_medals = average_medals_per_deck(0)
    max_medals = average_medals_per_deck(1)

    if not min_medals <= avg_medals_per_deck <= max_medals:
        return None

    low = 0
    high = 1

    for _ in range(40):
        mid = (low + high) / 2

        if average_medals_per_deck(mid) < avg_medals_per_deck:
            low = mid
        else:
            high = mid

    return (low + high) / 2
