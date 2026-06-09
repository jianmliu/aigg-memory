"""Small local models (e.g. Ollama gemma4) wrap structured output in a ```json fence and often
add prose around it; the parsers must tolerate that, not only the bare JSON a cloud model emits.
Regression for the MUD-over-Ollama report: reflect/plan returned empty because the fenced+prose
reply was dropped. The clean-JSON path must stay identical (cloud models unaffected)."""
from aigg_memory.extract import (parse_reflections, parse_plans, parse_observations,
                                 parse_reconciliation, parse_curation)

FENCED_PROSE = (
    "Sure! Here are the higher-level beliefs I synthesized from the episodes:\n\n"
    "```json\n"
    '[{"slug": "trap_pump", "name": "Pump is a trap", "description": "pump offers are traps",\n'
    '  "derived_from": ["burn_pump_0", "burn_pump_1"]}]\n'
    "```\n\n"
    "Let me know if you'd like anything adjusted."
)


def test_reflections_tolerates_fenced_block_inside_prose() -> None:
    out = parse_reflections(FENCED_PROSE)
    assert len(out) == 1
    assert out[0]["slug"] == "trap_pump" and out[0]["derived_from"] == ["burn_pump_0", "burn_pump_1"]


def test_plans_tolerates_prose_before_a_bare_array() -> None:
    txt = ('Based on the goal and the invitation, the plan is: '
           '[{"slug":"attend_party","name":"Attend","valid_from":"2026-02-14T17:00",'
           '"derived_from":["goal_socialize","invite_party"]}]  — hope that helps!')
    out = parse_plans(txt)
    assert len(out) == 1 and out[0]["derived_from"] == ["goal_socialize", "invite_party"]


def test_reconciliation_tolerates_fence_and_trailing_prose() -> None:
    txt = '```json\n{"relation":"temporal","current":"loc_bj","reason":"moved"}\n```\nDone.'
    assert parse_reconciliation(txt) == {"relation": "temporal", "current": "loc_bj", "reason": "moved"}


def test_observations_tolerates_object_in_prose() -> None:
    txt = ('Here is the observation:\n```json\n'
           '{"memories":[{"slug":"likes_dark_mode","name":"likes dark mode","kind":"semantic"}]}\n```')
    out = parse_observations(txt)
    assert len(out) == 1 and out[0]["slug"] == "likes_dark_mode"


def test_curation_tolerates_fenced_prose() -> None:
    txt = 'My verdicts:\n```json\n[{"id":"x","verdict":"trivial","reason":"chatter"}]\n```'
    out = parse_curation(txt)
    assert out and out[0]["verdict"] == "trivial"


def test_clean_bare_json_still_parses_identically() -> None:   # cloud models unaffected
    assert parse_reflections('[{"slug":"s","derived_from":["e"]}]')[0]["slug"] == "s"
    assert parse_reconciliation('{"relation":"none"}')["relation"] == "none"


def test_observation_coerces_object_body_and_string_match() -> None:
    # small models sometimes return body as an object and match as a string — coerce, don't break
    txt = ('```json\n[{"slug":"prefers_dawn","name":"Dawn","kind":"procedural",'
           '"description":"trains at dawn","match":"dawn","body":{"time":"dawn","exclude":"night"}}]\n```')
    out = parse_observations(txt)
    assert len(out) == 1
    assert isinstance(out[0]["body"], str) and "dawn" in out[0]["body"]
    assert out[0]["match"] == ["dawn"]


def test_no_json_degrades_safely() -> None:
    assert parse_reflections("I cannot help with that request.") == []
    assert parse_plans("Sorry, no plans.") == []
    assert parse_reconciliation("unclear") == {"relation": "uncertain", "current": "", "reason": ""}
