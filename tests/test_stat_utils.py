import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ClashRoyaleManager"))

from utils.war_math import average_medals_per_deck, calculate_win_rate_from_average_medals


class StatUtilsTests(unittest.TestCase):
    def test_calculate_win_rate_from_average_medals_round_trips_known_values(self):
        for win_rate in [0, 0.25, 0.5, 0.75, 1]:
            medals = average_medals_per_deck(win_rate)
            calculated = calculate_win_rate_from_average_medals(medals)

            self.assertAlmostEqual(calculated, win_rate, places=6)

    def test_calculate_win_rate_returns_none_outside_possible_range(self):
        self.assertIsNone(calculate_win_rate_from_average_medals(99))
        self.assertIsNone(calculate_win_rate_from_average_medals(226))


if __name__ == "__main__":
    unittest.main()
