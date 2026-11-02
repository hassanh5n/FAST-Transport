"""Claude Code PreToolUse hook: suggest graphify once per session, before the first Grep.

Replaces graphify's own `hook-guard`, which tells the agent it MUST query the graph
before every Grep, Read and Glob. The graph pays off for broad and cross-stack
questions, not for looking up a symbol by name, so this only suggests it, once.
Never blocks a tool call; any error prints nothing.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "graphify-out"

HINT = (
    "graphify-out/graph.json exists. For broad or cross-stack questions (how does X work, "
    "what does this page call in the backend), `graphify query \"<question>\"`, "
    "`graphify explain \"<path>::<symbol>\"` or `graphify path \"<A>\" \"<B>\"` usually finds "
    "the right files faster than grep. For a known symbol or string, grep directly."
)


def main() -> None:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        if not (OUT / "graph.json").is_file():
            return
        session = re.sub(r"[^A-Za-z0-9_-]", "", str(event.get("session_id") or ""))[:64]
        if session:
            marker = OUT / f".hint_shown_{session}"
            if marker.exists():
                return
            marker.touch()
        sys.stdout.write(json.dumps({
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": HINT}
        }))
    except Exception:
        pass


if __name__ == "__main__":
    main()
