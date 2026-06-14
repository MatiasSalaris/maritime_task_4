"""Reason-then-act parsing and live reasoning streaming.

These cover the streaming decision path: the LLM emits prose reasoning, then a
sentinel, then a JSON action block. We must (a) recover the action JSON robustly
even when the small open-weight model wraps it in fences or drops the sentinel,
and (b) stream only the reasoning prose to the chain-of-thought panel — never a
half-printed sentinel.
"""

from __future__ import annotations

from maritime_swarm.ai_control.planner import _ReasoningStreamer, split_reason_action


def test_split_clean_reason_then_act():
    text = (
        "I see unknown c003 to my south. I will close and identify it.\n"
        '###ACTION###\n'
        '{"messages":[{"to":"all","type":"proposal","content":"taking c003"}],'
        '"action":{"tool":"investigate_contact","args":{"contact_id":"c003"}}}'
    )
    reasoning, action = split_reason_action(text)
    assert reasoning.startswith("I see unknown c003")
    assert action["action"]["tool"] == "investigate_contact"
    assert action["messages"][0]["type"] == "proposal"


def test_split_fenced_json_without_sentinel():
    text = 'Reasoning here.\n```json\n{"action":{"tool":"patrol_sector","args":{"sector":"NW"}}}\n```'
    reasoning, action = split_reason_action(text)
    assert action["action"]["tool"] == "patrol_sector"


def test_split_prose_only_yields_no_action():
    reasoning, action = split_reason_action("Just thinking, no decision yet.")
    assert action == {}
    assert "thinking" in reasoning


def test_streamer_emits_only_prose_even_when_sentinel_is_split():
    out: list[str] = []
    streamer = _ReasoningStreamer(out.append)
    # the sentinel "###ACTION###" arrives split across several deltas
    for delta in ["I will ", "go south", ".", "##", "#ACT", "ION###", '{"action":{}}']:
        streamer.feed(delta)
    streamer.flush()
    assert "".join(out) == "I will go south."


def test_streamer_flushes_prose_only_reply():
    out: list[str] = []
    streamer = _ReasoningStreamer(out.append)
    streamer.feed("No action needed right now.")
    streamer.flush()
    assert "".join(out) == "No action needed right now."
