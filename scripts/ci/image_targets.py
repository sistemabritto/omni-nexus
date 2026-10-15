"""Resolve the OmniNexus image contract without credentials or Docker access."""
import fnmatch
import json
import os
from pathlib import Path

NAMESPACE = "excarplex"
IMAGES = {
    "dashboard": {"image": "evo-nexus-dashboard", "dockerfile": "Dockerfile.swarm.dashboard"},
    "runtime": {"image": "evo-nexus-runtime", "dockerfile": "Dockerfile.swarm"},
    "media-worker": {"image": "evo-nexus-media-worker", "dockerfile": "Dockerfile.media-worker"},
}
TARGETS = {
    "all": ("runtime", "dashboard", "media-worker"),
    "core": ("runtime", "dashboard"),
    "dashboard": ("dashboard",),
    "media-worker": ("media-worker",),
    "media": ("dashboard", "media-worker"),
}


def select_images(event_name, ref, target="all"):
    if event_name == "push":
        if ref != "refs/heads/main" and not any(
            fnmatch.fnmatchcase(ref, pattern) for pattern in ("refs/tags/v*", "refs/tags/rc*")
        ):
            raise ValueError("Unsupported publication ref")
        target = "all"
    elif event_name == "workflow_dispatch":
        if not ref.startswith(("refs/heads/", "refs/tags/")):
            raise ValueError("Unsupported manual ref")
    else:
        raise ValueError("Unsupported publication event")
    if target not in TARGETS:
        raise ValueError("Unsupported image target")
    return [dict(IMAGES[name]) for name in TARGETS[target]]


def main():
    sha = os.environ["SOURCE_SHA"]
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("A complete immutable source SHA is required")
    matrix = {"include": select_images(os.environ["EVENT_NAME"], os.environ["SOURCE_REF"],
                                      os.environ.get("IMAGE_TARGET", "all"))}
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write("matrix=" + json.dumps(matrix, separators=(",", ":")) + "\n")
        output.write("revision=" + sha + "\n")


if __name__ == "__main__":
    main()
