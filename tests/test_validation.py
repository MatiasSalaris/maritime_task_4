"""Tests for event protocol validation."""

import unittest

from maritime_swarm.communication.message_validation import validate_message


class MessageValidationTests(unittest.TestCase):
    """Verify accepted and rejected message shapes."""

    def test_task_bid_message_is_valid(self) -> None:
        validate_message({"type": "TASK_BID", "task_id": "t1", "utility": 0.7, "sender": "USV-1"})

    def test_missing_field_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_message({"type": "TASK_BID", "task_id": "t1", "sender": "USV-1"})

    def test_unknown_type_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_message({"type": "PROPOSAL", "sender": "USV-1"})


if __name__ == "__main__":
    unittest.main()
