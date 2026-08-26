import json
from pathlib import Path

import pytest

from agent_yield.ingest import (
    context_per_call,
    incomplete_calls,
    ingest,
    load_ingested,
    load_records,
    median_agent_total,
)


def _line(**kw):
    """Build a transcript line in the verified real shape."""
    return json.dumps({
        "type": "assistant",
        "timestamp": kw.get("ts", "2026-08-24T12:00:00.000Z"),
        "sessionId": kw.get("session", "s1"),
        "isSidechain": kw.get("sub", False),
        "agentId": kw.get("agent"),
        "requestId": kw["req"],
        "message": {
            "id": kw["msg"],
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": kw.get("inp", 0),
                "output_tokens": kw.get("out", 0),
                "cache_creation_input_tokens": kw.get("cw", 0),
                "cache_read_input_tokens": kw.get("cr", 0),
            },
            "stop_reason": kw.get("stop"),
        },
    })


def test_duplicate_message_and_request_pairs_are_counted_once(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        _line(req="r1", msg="m1", cr=100) + "\n"
        + _line(req="r1", msg="m1", cr=100) + "\n",
        encoding="utf-8",
    )
    assert len(load_records([path])) == 1


def _can_symlink(tmp_path: Path) -> bool:
    """Windows refuses symlinks without Administrator or Developer Mode.

    Probed rather than guessed from `sys.platform`: the privilege is a
    machine setting, not a platform constant, and a Windows box with
    Developer Mode on should run the symlink arm rather than skip it.
    """
    probe, link = tmp_path / "_probe", tmp_path / "_probe.link"
    probe.write_text("x", encoding="utf-8")
    try:
        link.symlink_to(probe)
    except (OSError, NotImplementedError):
        return False
    link.unlink()
    return True


@pytest.mark.parametrize("how", ["symlink", "copy"])
def test_a_subagent_transcript_reached_twice_is_billed_once(tmp_path, how):
    """The 2026-08-26 layout: the agent transcript lives under the project
    directory and `tasks/<agentId>.output` is a SYMLINK to it, so a walk of both
    roots hands `load_records` the same file under two paths. 84 of the 142
    transcripts on the Mac are symlinks -- see `discovery`. Nothing but the
    `(message_id, request_id)` dedup stands between that and a doubled subagent
    bill, which is the number §3.1 decomposes.

    Two arms because the symlink arm cannot run everywhere: Windows raises
    WinError 1314 without Administrator or Developer Mode. The dedup key is
    `(message_id, request_id)` and never inspects the inode, so the copy arm
    exercises the identical code path and is the one that runs on an
    unprivileged Windows box. The symlink arm is what reproduces the real Mac
    layout, so it is kept and SKIPPED BY NAME rather than deleted -- an
    unnamed skip here would be the silence issue #29 is about.
    """
    real = tmp_path / "agent-a1.jsonl"
    real.write_text(_line(req="r1", msg="m1", cr=90_000, sub=True, agent="a1") + "\n",
                    encoding="utf-8")
    second = tmp_path / "a1.output"
    if how == "symlink":
        if not _can_symlink(tmp_path):
            pytest.skip("symlink privilege not held (Windows without Developer Mode)")
        second.symlink_to(real)
    else:
        second.write_bytes(real.read_bytes())

    records = load_records([real, second])
    assert len(records) == 1
    assert records[0].usage.cache_read_tokens == 90_000
    assert records[0].is_subagent


def test_records_without_ids_are_kept_not_dropped(tmp_path):
    path = tmp_path / "s.jsonl"
    line = json.dumps({
        "type": "assistant", "timestamp": "2026-08-24T12:00:00.000Z",
        "message": {"usage": {"cache_read_input_tokens": 50}},
    })
    path.write_text(line + "\n" + line + "\n", encoding="utf-8")
    assert len(load_records([path])) == 2


def test_empty_and_corrupt_files_do_not_abort_the_walk(tmp_path):
    (tmp_path / "empty.output").write_text("", encoding="utf-8")
    (tmp_path / "junk.output").write_text("{not json\n", encoding="utf-8")
    good = tmp_path / "good.jsonl"
    good.write_text(_line(req="r1", msg="m1", cr=7) + "\n", encoding="utf-8")
    records = load_records(
        [tmp_path / "empty.output", tmp_path / "junk.output", good]
    )
    assert len(records) == 1


def test_reproduces_the_case_study_context_per_call(tmp_path):
    """docs/case-study.md 2026-08-24: 942,865,149 cache-read over 6,910 calls."""
    path = tmp_path / "s.jsonl"
    per_call = 942_865_149 // 6_910
    remainder = 942_865_149 - per_call * 6_910
    lines = [
        _line(req=f"r{i}", msg=f"m{i}", cr=per_call + (remainder if i == 0 else 0))
        for i in range(6_910)
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    records = load_records([path])
    assert len(records) == 6_910
    assert round(context_per_call(records)) == 136_449


def test_reproduces_the_case_study_median_agent(tmp_path):
    """docs/case-study.md: 77 subagents, median 12,385,765."""
    path = tmp_path / "subs.jsonl"
    totals = ([1_000_000] * 38) + [12_385_765] + ([68_475_554] * 38)
    lines = [
        _line(req=f"r{i}", msg=f"m{i}", sub=True, agent=f"a{i}", cr=total)
        for i, total in enumerate(totals)
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    records = load_records([path])
    assert median_agent_total(records) == 12_385_765


def test_ingest_persists_and_reloads_identically(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_text(_line(req="r1", msg="m1", cr=5, out=2), encoding="utf-8")
    dest = tmp_path / ".agent-yield" / "calls.jsonl"
    assert ingest(dest, [src]) == 1
    reloaded = load_ingested(dest)
    assert reloaded[0].usage.cache_read_tokens == 5
    assert reloaded[0].usage.output_tokens == 2


def test_ingest_is_idempotent_across_runs(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_text(_line(req="r1", msg="m1", cr=5), encoding="utf-8")
    dest = tmp_path / ".agent-yield" / "calls.jsonl"
    ingest(dest, [src])
    ingest(dest, [src])
    assert len(load_ingested(dest)) == 1


def test_ingest_is_idempotent_for_unkeyed_records_too(tmp_path):
    src = tmp_path / "s.jsonl"
    line = json.dumps({
        "type": "assistant", "timestamp": "2026-08-24T12:00:00.000Z",
        "message": {"usage": {"cache_read_input_tokens": 50}},
    })
    src.write_text(line + "\n", encoding="utf-8")
    dest = tmp_path / ".agent-yield" / "calls.jsonl"
    ingest(dest, [src])
    ingest(dest, [src])
    assert len(load_ingested(dest)) == 1


def test_deeply_nested_json_does_not_abort_the_walk(tmp_path):
    """json.loads raises RecursionError, not ValueError, on nested input."""
    path = tmp_path / "s.jsonl"
    path.write_text(
        "[" * 20000 + "\n"
        + json.dumps({
            "timestamp": "2026-08-25T12:00:00Z",
            "requestId": "req_deep",
            "message": {"id": "msg_deep", "usage": {"input_tokens": 7}},
        })
        + "\n",
        encoding="utf-8",
    )
    records = load_records([path])
    assert [r.request_id for r in records] == ["req_deep"]


def test_the_ttl_split_survives_the_persisted_round_trip(tmp_path):
    """A flat-only persisted line loses the split, and the total still adds up.

    That is what makes the loss dangerous: nothing looks wrong afterwards. The
    persisted shape has to be the nested shape `Usage.from_payload` parses.
    """
    src = tmp_path / "s.jsonl"
    src.write_text(json.dumps({
        "type": "assistant",
        "timestamp": "2026-08-26T12:00:00.000Z",
        "sessionId": "s1",
        "requestId": "r1",
        "message": {
            "id": "m1",
            "model": "claude-opus-5",
            "usage": {
                "input_tokens": 2,
                "output_tokens": 4_634,
                "cache_creation_input_tokens": 7_071,
                "cache_read_input_tokens": 15_435,
                "cache_creation": {
                    "ephemeral_5m_input_tokens": 4_071,
                    "ephemeral_1h_input_tokens": 3_000,
                },
            },
        },
    }) + "\n")

    dest = tmp_path / "calls.jsonl"
    ingest(dest, [tmp_path])
    (held,) = load_ingested(dest)
    assert held.usage.cache_creation_5m == 4_071
    assert held.usage.cache_creation_1h == 3_000
    assert held.usage.cache_creation_unattributed == 0


# -- One call, several records ------------------------------------------------
#
# Claude Code writes one record per content block. They share
# `(message.id, requestId)` and their cache and input figures, and only the last
# -- the one carrying a `stop_reason` -- has the call's real `output_tokens`.

def test_the_terminal_record_wins_not_the_first(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        _line(req="r1", msg="m1", out=1, cr=5_417, cw=3_153) + "\n"
        + _line(req="r1", msg="m1", out=197, cr=5_417, cw=3_153,
                stop="tool_use") + "\n"
    )
    (record,) = load_records([path])
    assert record.usage.output_tokens == 197
    assert record.usage.cache_read_tokens == 5_417
    assert not record.incomplete


def test_a_later_terminal_record_does_not_lose_to_an_earlier_one(tmp_path):
    """Two terminal records under one id are a continuation or a retry.

    Not more of the same call: taking the larger would be picking a number
    rather than a call. The archive holds no such group -- which is exactly why
    it is asserted here, where it can be constructed.
    """
    path = tmp_path / "s.jsonl"
    path.write_text(
        _line(req="r1", msg="m1", out=4_096, stop="max_tokens") + "\n"
        + _line(req="r1", msg="m1", out=9_000, stop="end_turn") + "\n"
    )
    (record,) = load_records([path])
    assert record.usage.output_tokens == 4_096


def test_a_group_with_no_terminal_record_is_marked_incomplete(tmp_path):
    """The case the archived arms hold and no synthetic guess would have found.

    Two such groups on baton-r1, two on baton-r2, none on either reader arm --
    and the shortfall against the CLI's own accounting is non-zero on precisely
    the arms that have them. The largest record is the best lower bound
    available, and the flag is what stops a caller reporting it as exact.
    """
    path = tmp_path / "s.jsonl"
    path.write_text(
        _line(req="r1", msg="m1", out=4) + "\n"
        + _line(req="r1", msg="m1", out=6) + "\n"
    )
    (record,) = load_records([path])
    assert record.usage.output_tokens == 6
    assert record.incomplete
    assert incomplete_calls([record]) == 1


def test_unkeyed_records_are_kept_and_never_called_incomplete(tmp_path):
    # They cannot be grouped, so nothing here knows whether they finished.
    path = tmp_path / "s.jsonl"
    path.write_text(json.dumps({
        "type": "assistant",
        "timestamp": "2026-08-24T12:00:00.000Z",
        "message": {"id": None, "usage": {"output_tokens": 7}},
    }) + "\n")
    records = load_records([path])
    assert [r.usage.output_tokens for r in records] == [7]
    assert incomplete_calls(records) == 0


def test_the_incomplete_flag_survives_the_persisted_round_trip(tmp_path):
    src = tmp_path / "s.jsonl"
    src.write_text(
        _line(req="r1", msg="m1", out=4) + "\n"
        + _line(req="r2", msg="m2", out=99, stop="end_turn") + "\n"
    )
    dest = tmp_path / "calls.jsonl"
    ingest(dest, [tmp_path])
    held = {r.message_id: r for r in load_ingested(dest)}
    assert held["m1"].incomplete and held["m1"].stop_reason is None
    assert not held["m2"].incomplete and held["m2"].stop_reason == "end_turn"


def test_a_record_carrying_a_unicode_line_separator_survives_whole(tmp_path):
    """#62. `str.splitlines()` cuts JSONL on seven characters JSONL does not.

    The assertion is that the record is PRESENT AND COMPLETE, not that the
    count is right. On the real transcript this was found on, the count WAS
    right: the character sat in the terminal record, that record vanished, a
    sibling kept the call alive, and the only visible symptom was the call
    being marked incomplete with a 2,663-token lower bound for its output.
    """
    lines = []
    for index, (text, output, stop) in enumerate([
        ("plain", 40, None),
        # The terminal record of the same call, carrying a NEL inside a string.
        ("holds a \u0085 next-line", 2_663, "end_turn"),
    ]):
        lines.append(json.dumps({
            "timestamp": f"2026-08-26T02:00:0{index}.000Z",
            "sessionId": "s1",
            "requestId": "req-1",
            "message": {
                "id": "msg-1",
                "stop_reason": stop,
                "content": [{"type": "text", "text": text}],
                "usage": {"input_tokens": 1, "output_tokens": output,
                          "cache_read_input_tokens": 10},
            },
        }))
    path = tmp_path / "t.jsonl"
    # json.dumps escapes it; the transcripts on disk carry it raw.
    path.write_text(
        "\n".join(lines).replace("\\u0085", "\u0085") + "\n", encoding="utf-8"
    )

    (record,) = load_records([path])
    assert record.usage.output_tokens == 2_663
    assert record.incomplete is False, "the terminal record was dropped"
