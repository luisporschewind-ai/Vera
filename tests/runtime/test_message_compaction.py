from vera.models.base import ModelMessage, ModelToolCall
from vera.runtime.context import compact_run_messages, normalize_tool_transcript


def _tool(call_id: str, content: str = "ok") -> ModelMessage:
    return ModelMessage(role="tool", content=content, tool_call_id=call_id)


def _assistant(*call_ids: str, reasoning: str | None = None) -> ModelMessage:
    return ModelMessage(
        role="assistant",
        content="",
        reasoning_content=reasoning,
        tool_calls=tuple(
            ModelToolCall(call_id=call_id, name="list_directory", arguments={"path": "."})
            for call_id in call_ids
        ),
    )


def test_parallel_tool_round_is_kept_intact() -> None:
    messages = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="analyze"),
        _assistant(*(f"c{index}" for index in range(10)), reasoning="先读这些文件"),
        *(_tool(f"c{index}", "x" * 20) for index in range(10)),
    ]

    compacted = compact_run_messages(messages, max_bytes=1_000_000, max_tool_messages=8)

    assert [message.role for message in compacted] == [
        "system",
        "user",
        "assistant",
        *["tool"] * 10,
    ]
    assert compacted[2].reasoning_content == "先读这些文件"
    assert [call.call_id for call in compacted[2].tool_calls] == [
        f"c{index}" for index in range(10)
    ]
    assert all(message.tool_call_id for message in compacted if message.role == "tool")


def test_older_tool_round_is_dropped_as_a_unit() -> None:
    messages = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="list"),
        _assistant("old_1", "old_2", reasoning="旧一轮"),
        _tool("old_1"),
        _tool("old_2"),
        _assistant(*(f"c{index}" for index in range(8)), reasoning="新一轮"),
        *(_tool(f"c{index}") for index in range(8)),
    ]

    compacted = compact_run_messages(messages, max_bytes=1_000_000, max_tool_messages=8)
    remaining_ids = {
        message.tool_call_id
        for message in compacted
        if message.role == "tool" and message.tool_call_id
    }
    assistants = [message for message in compacted if message.role == "assistant"]
    assert remaining_ids == {f"c{index}" for index in range(8)}
    assert len(assistants) == 1
    assert assistants[0].reasoning_content == "新一轮"
    assert {call.call_id for call in assistants[0].tool_calls} == remaining_ids
    notice = compacted[1]
    assert notice.role == "user"
    assert "dropped untrusted tool results" in notice.content
    assert notice.tool_call_id is None


def test_repeated_compaction_keeps_a_single_drop_notice() -> None:
    first = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="list"),
        _assistant(*(f"old{index}" for index in range(8))),
        *(_tool(f"old{index}") for index in range(8)),
    ]
    compacted = compact_run_messages(first, max_bytes=1_000_000, max_tool_messages=8)
    compacted.append(_assistant(*(f"new{index}" for index in range(8))))
    compacted.extend(_tool(f"new{index}") for index in range(8))
    compacted = compact_run_messages(compacted, max_bytes=1_000_000, max_tool_messages=8)
    notices = [message for message in compacted if _is_notice(message)]
    assert len(notices) == 1
    assert '"count":8' in notices[0].content
    assistants = [message for message in compacted if message.role == "assistant"]
    assert len(assistants) == 1
    assert [call.call_id for call in assistants[0].tool_calls] == [
        f"new{index}" for index in range(8)
    ]


def _is_notice(message: ModelMessage) -> bool:
    return message.role == "user" and "dropped untrusted tool results" in message.content


def test_normalize_drops_tool_results_that_do_not_follow_tool_calls() -> None:
    messages = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="hi"),
        ModelMessage(role="assistant", content="hello"),
        _tool("orphan"),
        _assistant("c1"),
        _tool("c1"),
    ]
    normalized = normalize_tool_transcript(messages)
    assert [message.role for message in normalized] == [
        "system",
        "user",
        "assistant",
        "assistant",
        "tool",
    ]
    assert normalized[-1].tool_call_id == "c1"
    assert normalized[2].tool_calls == ()


def test_oversize_single_round_omits_bodies_then_peels_oldest_tools() -> None:
    messages = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="analyze"),
        _assistant(*(f"c{index}" for index in range(6)), reasoning="先读完"),
        *(_tool(f"c{index}", "x" * 400) for index in range(6)),
    ]
    compacted = compact_run_messages(messages, max_bytes=500, max_tool_messages=8)
    tools = [message for message in compacted if message.role == "tool"]
    assistants = [message for message in compacted if message.role == "assistant"]
    assert assistants
    assert assistants[0].reasoning_content == "先读完"
    assert {call.call_id for call in assistants[0].tool_calls} == {
        message.tool_call_id for message in tools if message.tool_call_id
    }
    used = sum(len(message.content.encode("utf-8")) for message in compacted)
    assert used < 500
    assert len(tools) < 6


def test_compact_keeps_recent_tools_when_under_limit() -> None:
    messages = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="hi"),
        _assistant("c1", reasoning="先看目录"),
        _tool("c1"),
    ]
    compacted = compact_run_messages(messages, max_bytes=1_000_000, max_tool_messages=8)
    assert [message.role for message in compacted] == ["system", "user", "assistant", "tool"]
    assert compacted[-1].tool_call_id == "c1"
    assert compacted[2].reasoning_content == "先看目录"
