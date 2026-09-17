from vera.presentation.diagnostics_copy import format_config_body, format_doctor_body


def test_doctor_body_keeps_status_and_detail() -> None:
    body = format_doctor_body(
        {
            "items": [
                {"name": "python", "status": "pass", "detail": "3.12"},
                {"name": "git", "status": "warning", "detail": "not a repository"},
            ]
        }
    )
    assert body.splitlines() == [
        "python  pass  3.12",
        "git  warning  not a repository",
    ]


def test_config_body_shows_redacted_values_not_counts() -> None:
    body = format_config_body(
        {
            "sources": {"user": "absent", "project": "/tmp/demo/.vera/config.toml"},
            "providers": {
                "deepseek": {
                    "model": "deepseek-flash",
                    "base_url": "https://example.invalid",
                    "api_key_env": "DEEPSEEK_API_KEY",
                }
            },
            "limits": {"max_tool_calls": 50},
            "editor_argv": ["nano"],
            "ui": {"theme": "default"},
        }
    )
    assert "user  absent" in body
    assert "deepseek  deepseek-flash  https://example.invalid  DEEPSEEK_API_KEY" in body
    assert "max_tool_calls  50" in body
    assert "nano" in body
    assert "theme  default" in body
    assert "sources: 2" not in body
    assert "providers: 1" not in body
    assert "sk-" not in body
