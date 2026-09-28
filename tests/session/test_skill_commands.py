import shutil
from pathlib import Path

from tests.session.test_controller import make_controller
from tests.skills.test_manifest import write_skill
from vera.bootstrap import RuntimeDependencies
from vera.contracts.events import EventEnvelope
from vera.models.base import FakeModelAdapter, ModelTurn
from vera.runtime.engine import VeraRuntime
from vera.session.actions import ExecuteSlashCommand, SubmitPrompt
from vera.session.controller import SessionController
from vera.skills.discovery import SkillDiscovery
from vera.skills.registry import SkillRegistry
from vera.skills.selection import SkillSelectionService
from vera.tools.registry import ToolRegistry


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


def test_skills_use_rejects_duplicate_full_id_in_one_source(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    shutil.copytree(tmp_path / "user" / "python-review", tmp_path / "user" / "duplicate")

    outputs = tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills use user:python-review")))
    event = next(item for item in outputs if item.type == "skill.selection.changed")
    assert event.payload["selection"]["status"] == "invalid"
    assert event.payload["selection"]["reason_codes"] == ["skill_name_conflict"]
    assert controller.snapshot().skill_selection.status == "invalid"


def test_selected_skill_survives_session_resume_and_is_consumed_once(tmp_path: Path) -> None:
    first = _controller(tmp_path)
    tuple(first.dispatch(ExecuteSlashCommand(raw="/skills use user:python-review")))
    session_id = first.snapshot().session_id
    loaded = first.session_store.load(session_id, first.workspace)

    adapter = FakeModelAdapter([ModelTurn(assistant_text="done", finish_reason="stop")])
    selection = SkillSelectionService(
        SkillRegistry(
            SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=tmp_path / "user")
        )
    )
    runtime = VeraRuntime(
        adapter,
        ToolRegistry(),
        first.dependencies.config.state_dir,
        skill_selection_service=selection,
    )
    resumed = SessionController(
        RuntimeDependencies(runtime=runtime, config=first.dependencies.config),
        first.workspace,
        "fake",
        session_store=first.session_store,
        loaded_session=loaded,
    )

    assert resumed.snapshot().skill_selection.skill_id == "user:python-review"
    events = tuple(resumed.dispatch(SubmitPrompt(text="review")))
    assert any(event.type == "skill.snapshot.bound" for event in events)
    assert any("# Skill" in message.content for message in adapter.requests[0].messages)
    assert first.session_store.load(session_id, first.workspace).skill_selection.mode == "none"


def test_selected_skill_survives_model_switch(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills use user:python-review")))
    adapter = FakeModelAdapter([ModelTurn(assistant_text="done", finish_reason="stop")])
    replacement = VeraRuntime(
        adapter,
        ToolRegistry(),
        controller.dependencies.config.state_dir,
        skill_selection_service=SkillSelectionService(
            SkillRegistry(
                SkillDiscovery(builtin_root=tmp_path / "builtin", user_root=tmp_path / "user")
            )
        ),
    )
    controller.runtime_builder = lambda _workspace, _profile: RuntimeDependencies(
        runtime=replacement, config=controller.dependencies.config
    )

    tuple(controller.dispatch(ExecuteSlashCommand(raw="/model fake")))

    assert controller.snapshot().skill_selection.skill_id == "user:python-review"
    events = tuple(controller.dispatch(SubmitPrompt(text="review")))
    assert any(event.type == "skill.snapshot.bound" for event in events)
    assert any("# Skill" in message.content for message in adapter.requests[0].messages)


def test_bound_skill_consumption_is_saved_before_event_is_delivered(tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    tuple(controller.dispatch(ExecuteSlashCommand(raw="/skills use user:python-review")))

    output = controller.dispatch(SubmitPrompt(text="review"))
    for event in output:
        if isinstance(event, EventEnvelope) and event.type == "skill.snapshot.bound":
            break
    else:
        raise AssertionError("selected Skill was not bound")

    loaded = controller.session_store.load(controller.snapshot().session_id, controller.workspace)
    output.close()
    assert loaded.skill_selection.mode == "none"
