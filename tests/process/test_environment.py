from __future__ import annotations

from vera.process.environment import build_child_environment


def test_child_environment_keeps_only_allowlisted_baseline() -> None:
    source = {
        "PATH": "/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "TERM": "xterm",
        "HOME": "/Users/admin",
        "DEEPSEEK_API_KEY": "secret",
        "UNRELATED": "nope",
        "VERA_STATE_DIR": "/tmp/state",
    }
    env = build_child_environment({}, purpose="verification", source=source)
    assert env.values["PATH"] == "/bin"
    assert env.values["LANG"] == "C"
    assert env.values["TERM"] == "xterm"
    assert "HOME" not in env.values
    assert "UNRELATED" not in env.values
    assert "DEEPSEEK_API_KEY" not in env.values
    assert "VERA_STATE_DIR" not in env.values
    assert "DEEPSEEK_API_KEY" in env.denied


def test_forbidden_names_are_not_inherited_or_restored() -> None:
    source = {
        "PATH": "/usr/bin",
        "DEEPSEEK_API_KEY": "ds",
        "GLM_API_KEY": "glm",
        "OPENAI_API_KEY": "oa",
        "ANTHROPIC_API_KEY": "ant",
        "GITHUB_TOKEN": "gh",
        "AUTHORIZATION": "Bearer abc",
        "AWS_SECRET_ACCESS_KEY": "aws",
        "GOOGLE_APPLICATION_CREDENTIALS": "/keys.json",
        "AZURE_CLIENT_SECRET": "az",
        "VERA_LIVE_API_KEY": "live",
        "CUSTOM_API_KEY": "custom",
        "CI_JOB_TOKEN": "ci",
    }
    overrides = {
        "DEEPSEEK_API_KEY": "restored",
        "authorization": "Bearer restored",
        "PATH": "/safe/bin",
        "GITHUB_TOKEN": "restored-token",
    }
    env = build_child_environment(overrides, purpose="verification", source=source)
    names = {key.upper() for key in env.values}
    assert env.values["PATH"] == "/safe/bin"
    assert "DEEPSEEK_API_KEY" not in names
    assert "GLM_API_KEY" not in names
    assert "OPENAI_API_KEY" not in names
    assert "ANTHROPIC_API_KEY" not in names
    assert "GITHUB_TOKEN" not in names
    assert "AUTHORIZATION" not in names
    assert "AWS_SECRET_ACCESS_KEY" not in names
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in names
    assert "AZURE_CLIENT_SECRET" not in names
    assert "VERA_LIVE_API_KEY" not in names
    assert "CUSTOM_API_KEY" not in names
    assert "CI_JOB_TOKEN" not in names
    assert "restored" not in env.values.values()
    assert "Bearer restored" not in env.values.values()


def test_case_variants_and_empty_values_cannot_bypass_denylist() -> None:
    source = {
        "PATH": "/bin",
        "deepseek_api_key": "",
        "DeepSeek_Api_Key": "secret",
        "github_token": "",
        "Authorization": "Bearer empty-bypass",
    }
    env = build_child_environment(
        {"DEEPSEEK_API_KEY": "", "OpenAI_Api_Key": "x"},
        purpose="eval_worker",
        source=source,
    )
    names = {key.upper() for key in env.values}
    assert "DEEPSEEK_API_KEY" not in names
    assert "OPENAI_API_KEY" not in names
    assert "GITHUB_TOKEN" not in names
    assert "AUTHORIZATION" not in names
    assert all(value != "secret" for value in env.values.values())
    assert all("Bearer" not in value for value in env.values.values())


def test_eval_worker_purpose_keeps_python_task_variables() -> None:
    source = {
        "PATH": "/bin",
        "HOME": "/Users/admin",
        "VIRTUAL_ENV": "/venv",
        "PYTHONPATH": "/code",
        "DEEPSEEK_API_KEY": "secret",
    }
    env = build_child_environment({}, purpose="eval_worker", source=source)
    assert env.values["HOME"] == "/Users/admin"
    assert env.values["VIRTUAL_ENV"] == "/venv"
    assert env.values["PYTHONPATH"] == "/code"
    assert "DEEPSEEK_API_KEY" not in env.values
