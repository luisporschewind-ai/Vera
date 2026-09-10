from vera.redaction import Redactor


def test_redactor_removes_secret_from_nested_payload() -> None:
    redactor = Redactor(["sk-live-secret"])
    value = {"error": "Bearer sk-live-secret", "nested": ["sk-live-secret"]}
    assert redactor.redact(value) == {
        "error": "Bearer [REDACTED]",
        "nested": ["[REDACTED]"],
    }


def test_redactor_replaces_sensitive_keys() -> None:
    redactor = Redactor([])
    value = {"api_key": "a", "authorization": "b", "token": "c", "password": "d"}
    assert redactor.redact(value) == {
        "api_key": "[REDACTED]",
        "authorization": "[REDACTED]",
        "token": "[REDACTED]",
        "password": "[REDACTED]",
    }
