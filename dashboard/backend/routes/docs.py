"""Public documentation endpoint — serves markdown docs from docs/ folder.

docs/ mixes two audiences: product documentation for anyone running this
OSS project (getting-started, guides, agents, skills, routines,
integrations, reference, providers), and docs/operations/ — internal
incident and ops writeups (real VPS hostnames, SSH aliases, live share
tokens) that were never meant to leave this workspace. Pentest finding #1
(2026-09-16) confirmed docs/operations/ was reachable, unauthenticated,
through this same public endpoint. OPERATIONS_DIR_NAME is excluded from
the tree for anonymous callers and requires auth for its content — see
app.py's before_request for the matching route-level gate.
"""

import re
from pathlib import Path

from flask import Blueprint, Response, jsonify, send_from_directory, abort
from flask_login import current_user

from routes._helpers import WORKSPACE

bp = Blueprint("docs", __name__)

DOCS_DIR = WORKSPACE / "docs"
IMGS_DIR = DOCS_DIR / "imgs"
OPERATIONS_DIR_NAME = "operations"

# Ordering for top-level files in "Getting Started"
_TOP_LEVEL_ORDER = ["introduction.md", "getting-started.md", "architecture.md"]


def _title_from_md(path: Path) -> str:
    """Extract first H1 from a markdown file, or derive from filename."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            m = re.match(r"^#\s+(.+)", line)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    # Fallback: derive from filename
    return path.stem.replace("-", " ").replace("_", " ").title()


def _content_preview(path: Path, length: int = 200) -> str:
    """Return first `length` chars of a markdown file, stripped of headers and formatting."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    # Remove markdown headers
    text = re.sub(r"^#{1,6}\s+.*$", "", text, flags=re.MULTILINE)
    # Remove markdown formatting: bold, italic, code, links, images
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"[*_`~]+", "", text)
    # Remove horizontal rules
    text = re.sub(r"^---+\s*$", "", text, flags=re.MULTILINE)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:length]


def _slug(name: str) -> str:
    return name.replace(" ", "-").lower()


def _build_tree(include_operations: bool = False) -> list[dict]:
    """Scan docs/ and build a section tree.

    include_operations=False (the default, and always the case for
    anonymous callers) skips docs/operations/ entirely — even its
    section title and content_preview snippets would leak infra details.
    """
    if not DOCS_DIR.is_dir():
        return []

    sections: list[dict] = []

    # 1) Top-level .md files → "Getting Started" section
    top_files = [f for f in DOCS_DIR.iterdir() if f.is_file() and f.suffix == ".md"]
    # Sort by predefined order, then alphabetically
    order_map = {name: i for i, name in enumerate(_TOP_LEVEL_ORDER)}
    top_files.sort(key=lambda f: (order_map.get(f.name, 999), f.name))

    if top_files:
        children = []
        for f in top_files:
            title = _title_from_md(f)
            children.append({
                "title": title,
                "slug": f.stem,
                "path": f.name,
                "content_preview": _content_preview(f),
            })
        sections.append({
            "title": "Getting Started",
            "slug": "getting-started",
            "children": children,
        })

    # 2) Subdirectories → one section each, in logical order
    _SECTION_ORDER = ["guides", "dashboard", "agents", "skills", "routines", "integrations", "real-world", "reference"]
    subdirs = [
        d for d in DOCS_DIR.iterdir()
        if d.is_dir() and d.name != "imgs"
        and (include_operations or d.name != OPERATIONS_DIR_NAME)
    ]
    order_map_dirs = {name: i for i, name in enumerate(_SECTION_ORDER)}
    subdirs.sort(key=lambda d: (order_map_dirs.get(d.name, 999), d.name))
    for subdir in subdirs:
        md_files = sorted(subdir.rglob("*.md"), key=lambda f: f.name)
        if not md_files:
            continue
        children = []
        for f in md_files:
            rel = f.relative_to(DOCS_DIR)
            title = _title_from_md(f)
            children.append({
                "title": title,
                "slug": str(rel.with_suffix("")),
                "path": str(rel),
                "content_preview": _content_preview(f),
            })
        _SECTION_TITLES = {
            "guides": "Guides",
            "dashboard": "Dashboard",
            "agents": "Agents",
            "skills": "Skills",
            "routines": "Routines",
            "integrations": "Integrations",
            "real-world": "Real World",
            "reference": "Reference",
        }
        sections.append({
            "title": _SECTION_TITLES.get(subdir.name, subdir.name.replace("-", " ").title()),
            "slug": subdir.name,
            "children": children,
        })

    # 3) Root-level project files → "Project" section
    _ROOT_FILES = ["CHANGELOG.md", "ROADMAP.md", "CONTRIBUTING.md"]
    root_children = []
    for name in _ROOT_FILES:
        f = WORKSPACE / name
        if f.is_file():
            title = _title_from_md(f)
            root_children.append({
                "title": title,
                "slug": f"root/{f.stem.lower()}",
                "path": f"root/{f.name}",
                "content_preview": _content_preview(f),
            })
    if root_children:
        sections.append({
            "title": "Project",
            "slug": "project",
            "children": root_children,
        })

    return sections


@bp.route("/api/docs")
def doc_tree():
    """Return the documentation tree structure."""
    return jsonify({"sections": _build_tree(include_operations=current_user.is_authenticated)})


@bp.route("/api/docs/imgs/<path:filename>")
def doc_image(filename: str):
    """Serve images from docs/imgs/."""
    if not IMGS_DIR.is_dir():
        abort(404)
    # Security: prevent path traversal
    safe = Path(filename).name
    img_path = IMGS_DIR / safe
    if not img_path.is_file():
        abort(404)
    return send_from_directory(str(IMGS_DIR), safe)


@bp.route("/api/docs/llms-full.txt")
def llms_full():
    """Serve pre-generated llms-full.txt for LLM consumption.

    Pentest item #7 (2026-09-16) flagged this as a bundle reference that
    404s — it doesn't: App.tsx calls exactly this path
    (`${apiBase}/api/docs/llms-full.txt`) and the route above matches it.
    Decision: kept the route as-is, public like the rest of /api/docs/*
    (see app.py's before_request). What did need fixing is upstream —
    `make docs-build` (Makefile) used to concatenate ALL of docs/**/*.md,
    including docs/operations/ (internal ops notes), into this public
    file. Fixed there; this route doesn't need its own operations/ guard
    because the file it serves no longer contains that content.
    """
    txt_path = DOCS_DIR / "llms-full.txt"
    if txt_path.is_file():
        return send_from_directory(str(DOCS_DIR), "llms-full.txt", mimetype="text/plain; charset=utf-8")
    return Response("File not found. Run: make docs-build", status=404, mimetype="text/plain")


@bp.route("/api/docs/<path:filepath>")
def doc_content(filepath: str):
    """Return raw markdown content of a doc file."""
    # Support root/ prefix for project-level files (CHANGELOG, ROADMAP, etc.)
    _ALLOWED_ROOT = {"CHANGELOG.md", "ROADMAP.md", "CONTRIBUTING.md"}
    if filepath.startswith("root/"):
        filename = filepath[5:]  # strip "root/"
        if filename not in _ALLOWED_ROOT:
            abort(403)
        target = (WORKSPACE / filename).resolve()
        if not target.is_file():
            abort(404)
        content = target.read_text(encoding="utf-8", errors="replace")
        return content, 200, {"Content-Type": "text/plain; charset=utf-8"}

    # Security: resolve and ensure it stays within docs/
    target = (DOCS_DIR / filepath).resolve()
    if not str(target).startswith(str(DOCS_DIR.resolve())):
        abort(403)
    if not target.is_file() or target.suffix != ".md":
        abort(404)

    # Defense in depth: app.py's before_request already blocks anonymous
    # /api/docs/operations/* before it reaches here, but this view
    # shouldn't rely solely on that — an internal caller or future route
    # change must not accidentally reopen it.
    if not current_user.is_authenticated and filepath.split("/", 1)[0] == OPERATIONS_DIR_NAME:
        abort(401)

    content = target.read_text(encoding="utf-8", errors="replace")

    # Rewrite image paths: ../imgs/X → /api/docs/imgs/X and imgs/X → /api/docs/imgs/X
    content = re.sub(r"!\[([^\]]*)\]\(\.\./imgs/([^)]+)\)", r"![\1](/api/docs/imgs/\2)", content)
    content = re.sub(r"!\[([^\]]*)\]\(imgs/([^)]+)\)", r"![\1](/api/docs/imgs/\2)", content)

    return content, 200, {"Content-Type": "text/plain; charset=utf-8"}
