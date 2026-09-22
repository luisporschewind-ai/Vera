from pathlib import Path

from tests.session.test_controller import make_controller
from tests.skills.test_manifest import write_skill
from vera.contracts.events import EventEnvelope
from vera.session.actions import ExecuteSlashCommand
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService


def test_skill_commands_remain_readable_without_terminal_dimensions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    user = tmp_path / "user"
    workspace.mkdir()
    user.mkdir()
    write_skill(user)
    controller = make_controller(workspace, [])
    controller.dependencies.runtime.skill_selection_service = SkillSelectionService(
        SkillRegistry(SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=user))
    )

    output = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills")))
    event = next(item for item in output if isinstance(item, EventEnvelope))

    assert event.type == "skill.listed"
    assert "python-review" in str(event.payload["text"])
    assert "\x1b" not in str(event.payload)
