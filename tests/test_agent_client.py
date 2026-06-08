"""The agent-loop convenience layer (aigg_memory.agent) — the in-process contract a host
(aigg-monopoly) imports. Provenance splits the discernment q into a faculty channel (learned
myself, E1) and a social channel (a peer warned me, E2); track_record reads self-learned skill
(E4 legibility). Domain-agnostic: topic/marker are arbitrary strings."""
from pathlib import Path

from aigg_memory import agent


def test_believes_topic_and_marker(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    agent.record_episode(tmp_path, corpus, "trap_pump", "pump offers are traps",
                         match=["pump", "trap"], asserted_by="self", kind="belief")
    assert agent.believes(tmp_path, corpus, "pump")
    assert agent.believes(tmp_path, corpus, "pump", marker="trap")
    assert not agent.believes(tmp_path, corpus, "pump", marker="manipulator")  # marker absent
    assert not agent.believes(tmp_path, corpus, "rugpull")                     # topic absent


def test_faculty_channel_self_asserted(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    # reflect stamps asserted_by="self"; that is the FACULTY channel (learned myself, E1)
    agent.record_episode(tmp_path, corpus, "trap_pump", "pump offers are traps",
                         match=["pump", "trap"], asserted_by="self", kind="belief")
    d = agent.discernment(tmp_path, corpus, "pump", talent=0.2)
    assert d["faculty"] == 1.0 and d["social"] == 0.0
    assert d["q"] == 1.0   # clamp(0.2 + 1.0 + 0.0)


def test_social_channel_other_asserted(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    # a warning relayed from a peer (asserted_by != me/"self") is the SOCIAL channel (E2)
    agent.record_episode(tmp_path, corpus, "trap_pump", "pump offers are traps",
                         match=["pump", "trap"], asserted_by="friend", kind="belief")
    d = agent.discernment(tmp_path, corpus, "pump")
    assert d["social"] == 1.0 and d["faculty"] == 0.0
    # the agent's OWN id also counts as faculty (it learned it itself, even if stamped with its id)
    agent.record_episode(tmp_path, "npcs/me/memory", "trap_rug", "rug offers are traps",
                         match=["rug", "trap"], asserted_by="me", kind="belief")
    assert agent.discernment(tmp_path, "npcs/me/memory", "rug")["faculty"] == 1.0


def test_track_record_counts_self_learned_with_evidence(tmp_path: Path) -> None:
    corpus = "npcs/me/memory"
    agent.record_episode(tmp_path, corpus, "trap_pump", "pump traps", match=["pump", "trap"],
                         asserted_by="self", kind="belief", derived_from=["e1", "e2"])
    agent.record_episode(tmp_path, corpus, "trap_warned", "rug traps", match=["rug", "trap"],
                         asserted_by="someone_else", kind="belief")   # social, not self-learned
    tr = agent.track_record(tmp_path, corpus)
    assert tr["learned"] == 1            # only the self-asserted belief counts as learned skill
    assert tr["evidence"] == 2           # its two derived_from episodes
    assert tr["skill"] == 1.2


def test_record_episode_roundtrips(tmp_path: Path) -> None:
    from aigg_memory.memory import MemoryUnit
    agent.record_episode(tmp_path, "memory", "burn_0", "got rugged", match=["rug"], asserted_by="shill")
    u = MemoryUnit.from_text((tmp_path / "memory" / "burn_0" / "SKILL.md").read_text())
    assert u.kind == "episodic" and u.frontmatter["asserted_by"] == "shill"
