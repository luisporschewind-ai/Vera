from pathlib import Path

from vera.contracts.skills import SkillSelection
from vera.session.controller import SessionSnapshot


def test_session_snapshot_defaults_to_no_skill(tmp_path: Path) -> None:
    snapshot = SessionSnapshot(
        session_id="session_1",
        active_run_id=None,
        pending_approval_id=None,
        model_profile="fake",
        closed=False,
    )

    assert snapshot.skill_selection == SkillSelection()
