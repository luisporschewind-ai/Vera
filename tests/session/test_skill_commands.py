from pathlib import Path

from tests.session.test_controller import make_controller
from tests.skills.test_manifest import write_skill
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter
from vera.session.actions import ExecuteSlashCommand
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService


def _controller(tmp_path: Path):
    workspace = tmp_path / "workspace"
    user = tmp_path / "user"
    workspace.mkdir()
    user.mkdir()
    write_skill(user)
    controller = make_controller(workspace, [], adapter=FakeModelAdapter([]))
    controller.dependencies.runtime.skill_selection_service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )
    return controller


def test_skills_list_show_use_and_clear_are_structured(tmp_path: Path) -> None:
    controller = _controller(tmp_path)

    listed = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills")))
    listed_event = next(item for item in listed if isinstance(item, EventEnvelope))
    assert listed_event.type == "skill.listed"
    assert listed_event.payload["items"][0]["skill_id"] == "user:python-review"
    assert "# Skill" not in str(listed_event.payload)

    shown = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills show python-review")))
    shown_event = next(item for item in shown if isinstance(item, EventEnvelope))
    assert shown_event.type == "skill.shown"
    assert "resources" in shown_event.payload
    assert str(tmp_path) not in str(shown_event.payload)
    assert "# Skill" not in str(shown_event.payload)
    assert controller.dependencies.runtime.skill_selection_service.pending.status == "none"

    used = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills use python-review")))
    selection = next(item for item in used if item.type == "skill.selection.changed")
    assert selection.payload["selection"]["status"] == "selected"
    status = next(
        item
        for item in controller.dispatch(ExecuteSlashCommand(raw="/status"))
        if item.type == "session.status"
    )
    assert status.payload["skill_selection"]["skill_id"] == "user:python-review"

    cleared = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills clear")))
    clear_event = next(item for item in cleared if item.type == "skill.selection.changed")
    assert clear_event.payload["selection"]["mode"] == "none"


def test_skills_conflict_and_unknown_command_keep_reason_codes(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    workspace = controller.workspace
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    write_skill(builtin)
    controller.dependencies.runtime.skill_selection_service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=builtin, user_root=tmp_path / "user"))
    )

    output = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills use python-review")))
    event = next(item for item in output if item.type == "skill.selection.changed")
    assert event.payload["selection"]["status"] == "invalid"
    assert event.payload["selection"]["reason_codes"] == ["skill_name_conflict"]
    assert workspace.exists()
