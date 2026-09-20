from vera.git.parsers import parse_status_porcelain_v2


def test_porcelain_v2_parser_keeps_status_facts_and_nul_paths() -> None:
    payload = b"\0".join(
        [
            b"# branch.oid abc123",
            b"# branch.head main",
            b"# branch.upstream origin/main",
            b"# branch.ab +2 -1",
            b"1 M. N... 100644 100644 100644 abc abc staged.txt",
            b"1 .M S... 160000 160000 160000 abc def submodule",
            b"2 R. N... 100644 100644 100644 old new R100 renamed.txt",
            b"old name.txt",
            b"u UU N... 100644 100644 100644 100644 a b c conflict.txt",
            b"? -leading\nname.txt",
            "1 .M N... 100644 100644 100644 abc def Unicode-文件.txt".encode(),
            b"",
        ]
    )

    parsed = parse_status_porcelain_v2(payload)

    assert parsed.head_oid == "abc123"
    assert parsed.branch == "main"
    assert parsed.upstream == "origin/main"
    assert parsed.ahead == 2
    assert parsed.behind == 1
    assert parsed.detached is False
    assert parsed.unborn is False
    assert [entry.path for entry in parsed.entries] == [
        "staged.txt",
        "submodule",
        "renamed.txt",
        "conflict.txt",
        "-leading\nname.txt",
        "Unicode-文件.txt",
    ]
    assert parsed.entries[0].staged == "M"
    assert parsed.entries[0].unstaged == "."
    assert parsed.entries[1].submodule == "S..."
    assert parsed.entries[2].original_path == "old name.txt"
    assert parsed.entries[3].conflicted is True
    assert parsed.entries[4].untracked is True


def test_porcelain_v2_parser_handles_unborn_and_detached_headers() -> None:
    unborn = parse_status_porcelain_v2(b"# branch.oid (initial)\0# branch.head main\0? file.txt\0")
    detached = parse_status_porcelain_v2(b"# branch.oid abc\0# branch.head (detached)\0")

    assert unborn.head_oid is None
    assert unborn.unborn is True
    assert unborn.branch == "main"
    assert detached.head_oid == "abc"
    assert detached.detached is True
    assert detached.branch is None
