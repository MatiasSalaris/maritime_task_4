"""Tests for deterministic utility scoring and assignment."""

import unittest

from maritime_swarm.domain.utility_scoring import calculate_utility, select_winner


class UtilityTests(unittest.TestCase):
    """Verify deterministic task allocation helpers."""

    def test_utility_score_matches_expected_formula(self) -> None:
        utility, components = calculate_utility((42, 36), 91, 0.74, (58, 72))
        self.assertEqual(utility, 0.78)
        self.assertAlmostEqual(components["normalized_battery"], 0.91)

    def test_select_winner_uses_highest_utility(self) -> None:
        winner, bid = select_winner({
            "USV-1": {"utility": 0.627},
            "USV-2": {"utility": 0.780},
        })
        self.assertEqual(winner, "USV-2")
        self.assertEqual(bid["utility"], 0.780)

    def test_select_winner_tie_breaks_by_agent_id(self) -> None:
        winner, _ = select_winner({"USV-2": {"utility": 0.5}, "USV-1": {"utility": 0.5}})
        self.assertEqual(winner, "USV-1")


if __name__ == "__main__":
    unittest.main()
