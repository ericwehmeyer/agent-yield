import json

from agent_yield.cli import main


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
