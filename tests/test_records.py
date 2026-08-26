import datetime as dt
import json

from agent_yield.records import CallRecord, parse_line
from agent_yield.usage import Usage

# Field-for-field the shape of a real main-session transcript line, 2026-08-25.
MAIN_LINE = json.dumps({
    "parentUuid": "fcf14bca",
    "isSidechain": False,
    "type": "assistant",
    "requestId": "req_011CePM2BZLuuNrHSYzzX6Ck",
    "timestamp": "2026-08-25T10:56:36.286Z",
    "sessionId": "588b0593",
    "cwd": "C:\\Users\\ewehm\\repos\\agent-yield",
    "message": {
        "model": "claude-opus-5",
        "id": "msg_011CePM2CMU3jxtNi68Djy5L",
        "role": "assistant",
        "usage": {
            "input_tokens": 2,
            "cache_creation_input_tokens": 15711,
            "cache_read_input_tokens": 31316,
            "output_tokens": 121,
        },
    },
})

# The shape of a real subagent `.output` line.
SUBAGENT_LINE = json.dumps({
    "isSidechain": True,
    "agentId": "a21d33bb9cc0571cc",
    "type": "assistant",
    "requestId": "req_sub_1",
    "timestamp": "2026-08-25T11:02:00.000Z",
    "sessionId": "588b0593",
    "message": {
        "model": "claude-opus-5",
        "id": "msg_sub_1",
        "usage": {
            "input_tokens": 2,
            "output_tokens": 6,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 30025,
        },
    },
})


def test_parses_a_main_session_line():
    record = parse_line(MAIN_LINE)
    assert record.usage == Usage(2, 121, 15_711, 31_316)
    assert record.is_subagent is False
    assert record.session_id == "588b0593"
    assert record.model == "claude-opus-5"


def test_timestamp_is_timezone_aware_utc():
    record = parse_line(MAIN_LINE)
    assert record.timestamp.utcoffset() == dt.timedelta(0)
    assert record.day == dt.date(2026, 8, 25)


def test_subagent_line_is_marked_as_subagent():
    record = parse_line(SUBAGENT_LINE)
    assert record.is_subagent is True
    assert record.agent_id == "a21d33bb9cc0571cc"


def test_dedup_key_pairs_message_and_request():
    assert parse_line(MAIN_LINE).dedup_key == (
        "msg_011CePM2CMU3jxtNi68Djy5L",
        "req_011CePM2BZLuuNrHSYzzX6Ck",
    )


def test_dedup_key_is_none_when_either_id_is_missing():
    line = json.dumps({
        "type": "assistant",
        "timestamp": "2026-08-25T11:00:00.000Z",
        "message": {"usage": {"output_tokens": 5}},
    })
    assert parse_line(line).dedup_key is None


def test_non_usage_lines_are_skipped():
    assert parse_line('{"type":"mode","mode":"normal"}') is None
    assert parse_line("") is None
    assert parse_line("not json at all") is None


def test_context_is_everything_the_model_had_to_read():
    """One definition of "context", because two would drift.

    `session.py` computed input + cache-read + cache-creation to decide a
    call's cost band; `report.py` needs the same quantity to say what share of
    a day's main calls sat in each band. Two copies of a definition is how a
    share stops matching the band it claims to count.
    """
    record = CallRecord(
        timestamp=dt.datetime(2026, 8, 24, tzinfo=dt.timezone.utc),
        usage=Usage(input_tokens=3, cache_read_tokens=100,
                    cache_creation_tokens=7, output_tokens=999),
    )
    assert record.context == 110
