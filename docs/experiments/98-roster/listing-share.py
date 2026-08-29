"""What each enabled plugin contributes to the resident listings.

The roster experiment needs a denominator and three earlier attempts gave three
answers (63.7%, 42.7%, 59%). All three read plugin versions from cache
directory names, which does not work: several plugins carry more than one
cached version and some are named by git sha rather than semver, so "newest"
is not recoverable by sorting. The enabled `superpowers` is 6.2.0 from
superpowers-marketplace; sorting picked 6.3.0, the DISABLED copy.

Two things fix it, and both are readable rather than inferred:

    installPath   ~/.claude/plugins/installed_plugins.json is the harness's own
                  resolution. It says which directory is installed. Do not
                  guess from directory names.

    the filter    A skill carrying `disable-model-invocation: true` is
                  reachable by `/name` but is not in the listing the model
                  reads, so it costs no resident tokens. 20 of the 60 entries
                  on this machine are in that class.

Vendor directories are excluded: `mattpocock-skills` ships node_modules, and
counting it read 35 skills where 15 are listed.

Run it twice. The same number twice is the bar this file exists to meet; a
share that moves between runs is measuring the filesystem, not the roster.
"""
from __future__ import annotations

import json
import pathlib
import re

HOME = pathlib.Path.home()
SKIP = {"node_modules", ".git", "tests", "test", "examples", "fixtures"}
# Measured for session 76a3725b by `agent-yield status --baseline-calls 10`.
OPENING_TOKENS = 56_623
CHARS_PER_TOKEN = 4


def listed_description_chars(path: pathlib.Path) -> int | None:
    """Length of the description a listing would carry, or None if not listed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    front = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not front:
        return None
    matter = front.group(1)
    if re.search(r"^disable-model-invocation:\s*true\s*$", matter, re.M | re.I):
        return None
    described = re.search(
        r"^description:\s*(.*?)(?=\n[a-zA-Z_-]+:|\Z)", matter, re.S | re.M
    )
    if not described:
        return None
    return len(" ".join(described.group(1).split()))


def candidates(root: pathlib.Path, subdir: str, pattern: str) -> list[pathlib.Path]:
    base = root / subdir
    if not base.exists():
        return []
    return sorted(
        p for p in base.rglob(pattern) if not SKIP & {q.name for q in p.parents}
    )


def rows() -> list[dict]:
    installed = json.loads(
        (HOME / ".claude/plugins/installed_plugins.json").read_text(encoding="utf-8")
    )["plugins"]
    settings = json.loads(
        (HOME / ".claude/settings.json").read_text(encoding="utf-8")
    )
    enabled = {k for k, on in settings["enabledPlugins"].items() if on}

    out = []
    for key in sorted(enabled):
        entries = installed.get(key)
        if not entries:
            out.append({"plugin": key, "version": "NOT INSTALLED",
                        "listed": 0, "hidden": 0, "chars": 0})
            continue
        root = pathlib.Path(entries[0]["installPath"])
        found = (candidates(root, "skills", "SKILL.md")
                 + candidates(root, "commands", "*.md")
                 + candidates(root, "agents", "*.md"))
        sizes = [listed_description_chars(p) for p in found]
        listed = [s for s in sizes if s is not None]
        out.append({
            "plugin": key.split("@")[0],
            "version": entries[0]["version"],
            "listed": len(listed),
            "hidden": len(sizes) - len(listed),
            "chars": sum(listed),
        })
    return sorted(out, key=lambda r: -r["chars"])


def main() -> None:
    table = rows()
    total = sum(r["chars"] for r in table) or 1
    print(f"{'plugin':20s} {'version':14s} {'listed':>6s} {'hidden':>6s} "
          f"{'chars':>7s} {'share':>6s}")
    for r in table:
        print(f"{r['plugin']:20s} {r['version']:14s} {r['listed']:6d} "
              f"{r['hidden']:6d} {r['chars']:7,d} {r['chars']/total*100:5.1f}%")
    print(f"{'TOTAL':20s} {'':14s} {sum(r['listed'] for r in table):6d} "
          f"{sum(r['hidden'] for r in table):6d} {total:7,d}")

    tokens = total / CHARS_PER_TOKEN
    print(f"\nlisting text {total:,} chars, about {tokens:,.0f} tokens at "
          f"{CHARS_PER_TOKEN} chars/token")
    print(f"against a {OPENING_TOKENS:,}-token opening: "
          f"{tokens / OPENING_TOKENS * 100:.1f}%")
    print("\nchars/token is CHOSEN, not measured. The share moves with it, so "
          "any bar written\nfrom this number states the divisor alongside it.")


if __name__ == "__main__":
    main()
