"""Link frontend API calls to the Django views they hit, inside the graphify graph.

graphify extracts the React and Django code separately, so nothing connects a
page's `api.get("/api/buses/")` to `BusViewSet`. This script reads every `/api/...`
string literal in frontend/src, resolves it against backend/config/urls.py and
apps/transport/urls.py (explicit paths first, then router viewsets and their
@actions, the same order Django uses), and adds one `calls_api` edge per call from
the calling frontend function to the view class or method.

The edges are tagged `_origin: "semantic"`, so the AST-only rebuilds run by
`graphify update .` and the git hooks keep them as long as both end nodes still
exist. Rerun this script after adding or renaming endpoints. Running it again
replaces the previous links, so it is safe to repeat.

Usage (from the repo root):
    python scripts/graphify_api_links.py              # link, then recluster
    python scripts/graphify_api_links.py --dry-run    # print the mapping only
    python scripts/graphify_api_links.py --no-recluster
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / "graphify-out" / "graph.json"
FRONTEND = ROOT / "frontend" / "src"
BACKEND = ROOT / "backend"
APP = BACKEND / "apps" / "transport"
URLCONFS = [BACKEND / "config" / "urls.py", APP / "urls.py"]

RELATION = "calls_api"
MARKER = "_api_link"

# "/api/..." inside "...", '...' or `...`, with the HTTP method when it is a direct api.<verb>( call.
API_LITERAL = re.compile(r"""(?:api\.(get|post|put|patch|delete|getSWR)\(\s*)?(["'`])(/api/[^"'`]*)\2""")
TEMPLATE_VAR = re.compile(r"\$\{[^}]*\}")


# ── backend: what each URL resolves to ───────────────────────────────────────

def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        # LoggedTokenObtainPairView.as_view() -> LoggedTokenObtainPairView
        if node.attr == "as_view" and isinstance(node.value, ast.Name):
            return node.value.id
        return node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    return None


def _django_route_regex(route: str) -> re.Pattern:
    pattern = re.sub(r"<(?:\w+:)?\w+>", "[^/]+", route)
    return re.compile("^" + pattern + "$")


def parse_urlconfs():
    """Return (explicit, router): explicit = [(regex, view_name)], router = [(prefix, viewset)]."""
    explicit, router = [], []
    for conf in URLCONFS:
        prefix = "api/" if conf.parent.name == "transport" else ""
        tree = ast.parse(conf.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = _call_name(node.func)
            args = node.args
            if fn == "path" and len(args) >= 2 and isinstance(args[0], ast.Constant):
                view = _call_name(args[1])
                if view and view != "include":
                    explicit.append((_django_route_regex(prefix + args[0].value), view))
            elif fn == "register" and len(args) >= 2 and isinstance(args[0], ast.Constant):
                router.append((prefix + args[0].value.strip("/"), _call_name(args[1])))
    return explicit, router


def index_backend_definitions():
    """name -> (file, kind, actions) for top-level defs/classes; actions = {url_path: (method, detail)}."""
    defs = {}
    for py in sorted(APP.rglob("*.py")):
        if "migrations" in py.parts or py.name.startswith("test"):
            continue
        rel = py.relative_to(ROOT).as_posix()
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defs.setdefault(node.name, (rel, "function", {}))
            elif isinstance(node, ast.ClassDef):
                actions = {}
                for item in node.body:
                    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    for deco in item.decorator_list:
                        if isinstance(deco, ast.Call) and _call_name(deco.func) == "action":
                            kw = {k.arg: k.value for k in deco.keywords}
                            url_path = kw.get("url_path")
                            url_path = url_path.value if isinstance(url_path, ast.Constant) else item.name
                            detail = kw.get("detail")
                            detail = bool(detail.value) if isinstance(detail, ast.Constant) else False
                            actions[url_path] = (item.name, detail)
                defs.setdefault(node.name, (rel, "class", actions))
    return defs


def resolve(url: str, explicit, router, defs):
    """Map a normalised URL path (no leading slash) to (view_name, method_name_or_None)."""
    for regex, view in explicit:
        if regex.match(url):
            return view, None
    # Longest prefix first, so "admin-management/roles" beats a shorter prefix.
    for prefix, viewset in sorted(router, key=lambda r: -len(r[0])):
        if url != prefix + "/" and not url.startswith(prefix + "/"):
            continue
        rest = [p for p in url[len(prefix):].split("/") if p]
        actions = defs.get(viewset, (None, None, {}))[2]
        if not rest:
            return viewset, None
        if len(rest) == 1:
            hit = actions.get(rest[0])
            if hit and not hit[1]:
                return viewset, hit[0]
            return viewset, None  # detail route: /prefix/<pk>/
        if len(rest) == 2:
            hit = actions.get(rest[1])
            if hit and hit[1]:
                return viewset, hit[0]
    return None, None


# ── frontend: who makes each call ────────────────────────────────────────────

def frontend_calls():
    for path in sorted(FRONTEND.rglob("*")):
        if path.suffix not in {".js", ".jsx", ".mjs", ".ts", ".tsx"} or ".check." in path.name:
            continue
        text = path.read_text(encoding="utf-8")
        for m in API_LITERAL.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            # A nested template (`${a ? `?q=${a}` : ""}`) ends the literal early; drop the open tail.
            url = TEMPLATE_VAR.sub("x", m.group(3)).split("${")[0].split("?")[0]
            url = url[len("/api/"):]
            if url and not url.endswith("/"):
                url += "/"
            yield path.relative_to(ROOT).as_posix(), line, (m.group(1) or "").upper(), m.group(3), "api/" + url


def _line(node) -> int:
    loc = node.get("source_location") or "L0"
    return int(loc[1:]) if loc[1:].isdigit() else 0


def caller_node(nodes_by_file, source_file, line):
    """The frontend node on the call line, else the nearest one above it, else the file node."""
    nodes = nodes_by_file.get(source_file, [])
    exact = [n for n in nodes if _line(n) == line and _line(n) > 1]
    if exact:
        return exact[0]
    above = [n for n in nodes if 1 < _line(n) <= line]
    if above:
        return max(above, key=_line)
    return next((n for n in nodes if _line(n) == 1), None)


def target_node(nodes_by_file, defs, view, method):
    rel, kind, _ = defs.get(view, (None, None, None))
    if rel is None:
        return None
    nodes = nodes_by_file.get(rel, [])
    label = view if kind == "class" else view + "()"
    owner = next((n for n in nodes if n["label"] == label), None)
    if owner is None or method is None:
        return owner
    return next(
        (n for n in nodes if n["label"] == f".{method}()" and n["id"].startswith(owner["id"] + "_")),
        owner,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print the mapping, do not write")
    ap.add_argument("--no-recluster", action="store_true", help="skip `graphify cluster-only`")
    args = ap.parse_args()

    if not GRAPH.exists():
        print("graphify-out/graph.json not found; run `graphify update .` first", file=sys.stderr)
        return 1
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))
    nodes_by_file: dict[str, list] = {}
    for n in graph["nodes"]:
        nodes_by_file.setdefault(n.get("source_file", ""), []).append(n)

    explicit, router = parse_urlconfs()
    defs = index_backend_definitions()

    edges, unresolved, seen = [], [], set()
    for src_file, line, verb, raw_url, url in frontend_calls():
        view, method = resolve(url, explicit, router, defs)
        caller = caller_node(nodes_by_file, src_file, line)
        target = target_node(nodes_by_file, defs, view, method) if view else None
        if caller is None or target is None:
            unresolved.append(f"{src_file}:{line}  {raw_url}" + (f"  (view {view} not in graph)" if view else ""))
            continue
        if args.dry_run:
            print(f"{caller['label']:<32} {verb or '?':<6} {raw_url:<55} -> {target['label']}")
        key = (caller["id"], target["id"])
        if key in seen:
            continue
        seen.add(key)
        edges.append({
            "source": caller["id"],
            "target": target["id"],
            "relation": RELATION,
            "_origin": "semantic",
            MARKER: True,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "context": f"{verb or 'HTTP'} {raw_url}",
            "source_file": src_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    for u in unresolved:
        print("unresolved:", u)
    print(f"{len(edges)} frontend->backend links, {len(unresolved)} unresolved")
    if args.dry_run:
        return 0

    graph["links"] = [e for e in graph["links"] if not e.get(MARKER)] + edges
    GRAPH.write_text(json.dumps(graph, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if not args.no_recluster:
        subprocess.run(["graphify", "cluster-only", str(ROOT), "--no-label"], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
