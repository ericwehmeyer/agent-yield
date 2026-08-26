import json

from agent_yield import cli
from agent_yield.cli import main
from agent_yield.modes import load_modes


def test_predict_prints_a_band(capsys):
    assert main(["predict", "--context", "136449", "--calls", "70"]) == 0
    out = capsys.readouterr().out
    assert "M tokens" in out
    assert "$" not in out


def test_ingest_reports_how_many_calls_it_holds(tmp_path, capsys):
    src = tmp_path / "s.jsonl"
    src.write_text(json.dumps({
        "type": "assistant", "timestamp": "2026-08-24T12:00:00.000Z",
        "requestId": "r1", "sessionId": "s1",
        "message": {"id": "m1", "usage": {"cache_read_input_tokens": 10}},
    }), encoding="utf-8")
    dest = tmp_path / "calls.jsonl"
    assert main(["ingest", "--root", str(src), "--dest", str(dest)]) == 0
    assert "1 calls" in capsys.readouterr().out


def test_report_on_an_empty_ingest_says_so_rather_than_printing_zeroes(
    tmp_path, capsys
):
    assert main(["report", "--calls", str(tmp_path / "nothing.jsonl"),
                 "--repo", str(tmp_path)]) == 0
    assert "no calls" in capsys.readouterr().out.lower()


def test_unknown_subcommand_is_an_error():
    assert main(["nonsense"]) != 0


ID_A = "80aebcb6-1e4d-47cd-8ca0-9074da7fc468"
ID_B = "11111111-2222-3333-4444-555555555555"


def _ingested(tmp_path, sessions=((ID_A, 10), (ID_B, 5000))):
    """A real calls.jsonl, made the way the operator makes one."""
    lines = []
    for index, (session_id, tokens) in enumerate(sessions):
        lines.append(json.dumps({
            "type": "assistant", "timestamp": "2026-08-24T12:00:00.000Z",
            "requestId": f"r{index}", "sessionId": session_id,
            "message": {"id": f"m{index}",
                        "usage": {"cache_read_input_tokens": tokens}},
        }))
    src = tmp_path / "transcript.jsonl"
    src.write_text("\n".join(lines), encoding="utf-8")
    dest = tmp_path / "calls.jsonl"
    assert main(["ingest", "--root", str(src), "--dest", str(dest)]) == 0
    return dest


def test_tag_records_a_mode_load_modes_can_read_back(tmp_path, capsys):
    assert main(["tag", ID_A, "build", "--repo", str(tmp_path)]) == 0
    written = tmp_path / "session-modes.toml"
    assert written.exists()
    assert load_modes(written) == {ID_A: "build"}
    assert "$" not in capsys.readouterr().out


def test_tagging_the_same_session_twice_updates_rather_than_duplicates(tmp_path):
    assert main(["tag", ID_A, "build", "--repo", str(tmp_path)]) == 0
    assert main(["tag", ID_B, "ops", "--repo", str(tmp_path)]) == 0
    assert main(["tag", ID_A, "design", "--repo", str(tmp_path)]) == 0
    written = tmp_path / "session-modes.toml"
    assert written.read_text(encoding="utf-8").count("[[session]]") == 2
    assert load_modes(written) == {ID_A: "design", ID_B: "ops"}


def test_an_invalid_mode_is_refused_and_nothing_is_written(tmp_path, capsys):
    written = tmp_path / "session-modes.toml"
    assert main(["tag", ID_A, "vibes", "--repo", str(tmp_path)]) != 0
    out = capsys.readouterr().out
    assert "'vibes'" in out
    for mode in ("audit", "build", "design", "ops", "review"):
        assert mode in out
    assert not written.exists()


def test_an_invalid_mode_leaves_an_existing_file_alone(tmp_path):
    assert main(["tag", ID_A, "build", "--repo", str(tmp_path)]) == 0
    written = tmp_path / "session-modes.toml"
    before = written.read_text(encoding="utf-8")
    assert main(["tag", ID_A, "vibes", "--repo", str(tmp_path)]) != 0
    assert written.read_text(encoding="utf-8") == before


def test_tag_list_shows_untagged_sessions_biggest_total_first(tmp_path, capsys):
    calls = _ingested(tmp_path)
    assert main(["tag", "--list", "--repo", str(tmp_path),
                 "--calls", str(calls)]) == 0
    out = capsys.readouterr().out
    assert "5,000 tokens" in out
    assert "10 tokens" in out
    assert out.index(ID_B) < out.index(ID_A)
    assert "$" not in out


def test_tag_list_separates_tagged_from_untagged(tmp_path, capsys):
    calls = _ingested(tmp_path)
    assert main(["tag", ID_B, "build", "--repo", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["tag", "--list", "--repo", str(tmp_path),
                 "--calls", str(calls)]) == 0
    out = capsys.readouterr().out
    tagged, untagged = out.split("untagged")
    assert ID_B in tagged and "build" in tagged
    assert ID_A in untagged and ID_B not in untagged


def test_tag_list_without_an_ingest_says_so(tmp_path, capsys):
    assert main(["tag", "--list", "--repo", str(tmp_path),
                 "--calls", str(tmp_path / "nothing.jsonl")]) == 0
    assert "no calls" in capsys.readouterr().out.lower()


class _FakeIntervention:
    date = "2026-08-20"
    name = "narrower briefs"
    expect = "fewer tokens per commit"


class _FakeResult:
    def __init__(self, metric):
        self.intervention = _FakeIntervention()
        self.metric = metric
        self.before = None
        self.after = None
        self.change = None


def _report_with_one_intervention(tmp_path, monkeypatch, seen):
    monkeypatch.setattr(cli, "daily_outcomes", lambda *a, **k: [])
    monkeypatch.setattr(cli, "load_interventions", lambda _p: [_FakeIntervention()])

    def fake_compare(rows, interventions, metric="tokens_per_merge", **kwargs):
        seen["metric"] = metric
        return [_FakeResult(metric)]

    monkeypatch.setattr(cli, "compare_interventions", fake_compare)
    return _ingested(tmp_path)


def test_report_metric_flag_reaches_compare_interventions(
    tmp_path, monkeypatch, capsys
):
    seen = {}
    calls = _report_with_one_intervention(tmp_path, monkeypatch, seen)
    assert main(["report", "--calls", str(calls), "--repo", str(tmp_path),
                 "--metric", "tokens_per_commit"]) == 0
    assert seen["metric"] == "tokens_per_commit"
    out = capsys.readouterr().out
    assert "tokens_per_commit" in out
    assert "$" not in out


def test_report_defaults_to_tokens_per_merge(tmp_path, monkeypatch, capsys):
    seen = {}
    calls = _report_with_one_intervention(tmp_path, monkeypatch, seen)
    assert main(["report", "--calls", str(calls), "--repo", str(tmp_path)]) == 0
    assert seen["metric"] == "tokens_per_merge"
    capsys.readouterr()


def test_an_all_empty_metric_names_the_flag_rather_than_printing_dashes(
    tmp_path, monkeypatch, capsys
):
    seen = {}
    calls = _report_with_one_intervention(tmp_path, monkeypatch, seen)
    assert main(["report", "--calls", str(calls), "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "--metric" in out
    assert "'tokens_per_merge'" in out
    assert "tokens_per_commit" in out
    assert "$" not in out


def _transcript_root(tmp_path, calls: int = 20):
    """A transcript root holding one session, the way discovery finds one."""
    root = tmp_path / "transcripts"
    root.mkdir()
    lines = []
    for index in range(calls):
        lines.append(json.dumps({
            "type": "assistant",
            "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
            "requestId": f"req-{index}", "sessionId": "s1",
            "message": {"id": f"msg-{index}",
                        "usage": {"cache_read_input_tokens": 1_000 * (index + 1)}},
        }))
    (root / "s1.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_handoff_writes_a_readable_file(tmp_path, capsys):
    out = tmp_path / ".agent-yield" / "handoff.md"
    assert main(["handoff", "--out", str(out), "--repo", str(tmp_path),
                 "--transcripts", str(_transcript_root(tmp_path))]) == 0
    assert "handoff written" in capsys.readouterr().out
    text = out.read_text(encoding="utf-8")
    assert "## Session cost so far" in text
    assert "| calls | 20 |" in text
    assert "$" not in text


def test_handoff_notes_are_appended_and_survive_a_second_run(tmp_path, capsys):
    out = tmp_path / "handoff.md"
    root = _transcript_root(tmp_path)
    assert main(["handoff", "--out", str(out), "--repo", str(tmp_path),
                 "--transcripts", str(root), "--note", "thresholds half done"]) == 0
    assert main(["handoff", "--out", str(out), "--repo", str(tmp_path),
                 "--transcripts", str(root), "--note", "hook unmeasured"]) == 0
    text = out.read_text(encoding="utf-8")
    assert "thresholds half done" in text
    assert "hook unmeasured" in text


def test_handoff_read_prints_the_file(tmp_path, capsys):
    out = tmp_path / "handoff.md"
    assert main(["handoff", "--out", str(out), "--repo", str(tmp_path),
                 "--transcripts", str(_transcript_root(tmp_path))]) == 0
    capsys.readouterr()
    assert main(["handoff", "--out", str(out), "--read"]) == 0
    assert "## Working tree" in capsys.readouterr().out


def test_handoff_read_with_no_handoff_says_so(tmp_path, capsys):
    assert main(["handoff", "--out", str(tmp_path / "none.md"), "--read"]) == 0
    assert "no handoff" in capsys.readouterr().out


def test_handoff_without_a_transcript_still_writes_and_says_cost_is_unmeasured(
    tmp_path, capsys
):
    out = tmp_path / "handoff.md"
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["handoff", "--out", str(out), "--repo", str(tmp_path),
                 "--transcripts", str(empty)]) == 0
    assert "no session transcript found" in capsys.readouterr().out
    assert "no cost measurement" in out.read_text(encoding="utf-8")


def _steep_root(tmp_path, cache_read: int, calls: int = 20):
    root = tmp_path / "steep"
    root.mkdir()
    lines = []
    for index in range(calls):
        lines.append(json.dumps({
            "type": "assistant",
            "timestamp": f"2026-08-26T02:{index // 60:02d}:{index % 60:02d}.000Z",
            "requestId": f"req-{index}", "sessionId": "deep",
            "message": {"id": f"msg-{index}",
                        "usage": {"cache_read_input_tokens": cache_read}},
        }))
    (root / "deep.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def test_status_prints_the_four_fields_apart_and_the_cost_band(tmp_path, capsys):
    assert main(["status", "--transcripts", str(_transcript_root(tmp_path))]) == 0
    out = capsys.readouterr().out
    for field in ("input", "output", "cache write", "cache read"):
        assert field in out
    assert "cost band" in out
    assert "$" not in out


def test_status_exits_1_in_the_steep_band(tmp_path, capsys):
    root = _steep_root(tmp_path, cache_read=500_000)
    assert main(["status", "--transcripts", str(root)]) == 1
    out = capsys.readouterr().out
    assert "steep" in out
    assert "handoff" in out
    # Steep advice argues against compaction rather than recommending it.
    assert "Do not compact" in out
    assert "start fresh" in out


def test_status_is_quiet_and_exits_0_in_the_cheap_band(tmp_path, capsys):
    root = _steep_root(tmp_path, cache_read=20_000)
    assert main(["status", "--transcripts", str(root)]) == 0
    assert "Exit 1" not in capsys.readouterr().out


def test_status_exits_1_past_the_hard_growth_factor(tmp_path, capsys):
    root = tmp_path / "grown"
    root.mkdir()
    lines = []
    for index in range(20):
        # Opens at 10K, ends at 100K: 10x growth, still cheap in level terms.
        read = 10_000 if index < 10 else 100_000
        lines.append(json.dumps({
            "type": "assistant",
            "timestamp": f"2026-08-26T02:{index:02d}:00.000Z",
            "requestId": f"req-{index}", "sessionId": "grown",
            "message": {"id": f"msg-{index}",
                        "usage": {"cache_read_input_tokens": read}},
        }))
    (root / "grown.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["status", "--transcripts", str(root)]) == 1
    out = capsys.readouterr().out
    assert "grown 10.0x" in out
    assert "cost band       cheap" in out


def test_status_with_no_transcript_says_so_and_exits_0(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["status", "--transcripts", str(empty)]) == 0
    assert "no session transcript found" in capsys.readouterr().out


def test_status_reports_where_the_bands_were_crossed(tmp_path, capsys):
    root = _steep_root(tmp_path, cache_read=250_000)
    assert main(["status", "--transcripts", str(root)]) == 0
    assert "crossed knee    at call 1" in capsys.readouterr().out


def test_boundary_subcommand_fails_open_on_junk(monkeypatch):
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert main(["boundary", "--enforce"]) == 0


def test_statusline_subcommand_prints_one_line_and_exits_0(monkeypatch, capsys):
    import io
    import sys
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert main(["statusline"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert "$" not in out


def test_arming_a_refusal_is_an_explicit_command(tmp_path, monkeypatch, capsys):
    from agent_yield import boundary as boundary_module
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(boundary_module, "REFUSAL_ARMED_PATH", tmp_path / "armed")
    assert main(["boundary", "--arm-refusal"]) == 0
    assert (tmp_path / "armed").exists()
    assert "one exit-2 refusal" in capsys.readouterr().out
