"""#47's secondary, measured rather than inferred: WHERE do the tokens sit?

The token ranking and the dollar ranking disagree in sign across the three arms.
The inferred explanation was cache CREATION priced against cache READ -- five
agents each creating their own cache where one creates once and reads many. That
is testable directly, because `Usage` keeps the four fields apart.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from agent_yield.ingest import load_records

MAIN = Path.home()/".claude"/"projects"/"-Users-ericw-IdeaProjects-agent-yield"
WT   = Path.home()/".claude"/"projects"/"-private-tmp-claude-501--Users-ericw-IdeaProjects-agent-yield-b87046ab-1d77-46eb-8014-870cc270d8c9-scratchpad-ay47"

ARMS = [
    ("baton-r1",  MAIN, "33333333-0000-4000-8000-000000001010"),
    ("baton-r2",  MAIN, "33333333-0000-4000-8000-000000001020"),
    ("baton1-r1", WT,   "33333333-0000-4000-8000-000000003010"),
    ("baton1-r2", WT,   "33333333-0000-4000-8000-000000003020"),
    ("reader-r1", MAIN, "33333333-0000-4000-8000-000000002010"),
    ("reader-r2", MAIN, "33333333-0000-4000-8000-000000002020"),
]

def files(base: Path, sid: str):
    out = []
    parent = base/f"{sid}.jsonl"
    if parent.exists(): out.append(parent)
    sub = base/sid/"subagents"
    if sub.is_dir():
        out += [p for p in sub.glob("agent-*.jsonl")]
    return out

print(f"{'arm':11}{'calls':>6}{'create':>11}{'read':>12}{'output':>9}{'total':>12}{'create%':>9}{'read/create':>12}")
rows = {}
for name, base, sid in ARMS:
    paths = files(base, sid)
    if not paths:
        print(f"{name:11}  -- transcripts gone --"); continue
    recs = load_records(paths)
    c = sum(r.usage.cache_creation_tokens for r in recs)
    rd = sum(r.usage.cache_read_tokens for r in recs)
    o = sum(r.usage.output_tokens for r in recs)
    i = sum(r.usage.input_tokens for r in recs)
    t = c+rd+o+i
    rows[name] = (len(recs), c, rd, o, t)
    print(f"{name:11}{len(recs):>6}{c:>11,}{rd:>12,}{o:>9,}{t:>12,}{100*c/t:>8.1f}%{rd/c:>12.1f}")

# Standard Anthropic multipliers, relative to a base input token:
#   cache write 1.25x, cache read 0.10x, output 5.0x (Opus: $15/$75 per M).
COST = {"baton-r1": 2.91, "baton-r2": 2.18, "baton1-r1": 1.78,
        "baton1-r2": 1.84, "reader-r1": 3.20, "reader-r2": 3.25}
print()
print(f"{'arm':11}{'raw total':>12}{'weighted':>11}{'$':>7}{'weighted/$':>12}")
import statistics
byarm = {}
for name,(n,c,rd,o,t) in rows.items():
    w = c*1.25 + rd*0.10 + o*5.0
    byarm.setdefault(name.split("-")[0], []).append((t, w, COST[name]))
    print(f"{name:11}{t:>12,}{w:>11,.0f}{COST[name]:>7.2f}{w/COST[name]:>12,.0f}")
print()
print(f"{'arm':11}{'raw mean':>12}{'weighted':>11}{'$ mean':>9}")
for arm, vals in byarm.items():
    print(f"{arm:11}{statistics.fmean(v[0] for v in vals):>12,.0f}"
          f"{statistics.fmean(v[1] for v in vals):>11,.0f}{statistics.fmean(v[2] for v in vals):>9.2f}")
b  = statistics.fmean(v[1] for v in byarm["baton"])
b1 = statistics.fmean(v[1] for v in byarm["baton1"])
r  = statistics.fmean(v[1] for v in byarm["reader"])
rb = statistics.fmean(v[0] for v in byarm["baton"])
rr = statistics.fmean(v[0] for v in byarm["reader"])
print()
print(f"#33 headline, raw tokens      reader/baton = {rr/rb:.2f}x")
print(f"#33 headline, weighted        reader/baton = {r/b:.2f}x")
print(f"#47 packing, raw tokens       baton1/baton = {statistics.fmean(v[0] for v in byarm['baton1'])/rb:.2f}x")
print(f"#47 packing, weighted         baton1/baton = {b1/b:.2f}x")
