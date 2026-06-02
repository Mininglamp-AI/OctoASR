#!/usr/bin/env python3
# coding=utf-8
"""Regenerate the changelog block in README.md from git tags.

New `v*` tags are PREPENDED to the changelog block: for each tag not already
listed, the annotated-tag message's first line is used as the description
(falling back to the tagged commit's subject for lightweight tags). Existing
hand-written lines are preserved verbatim. Only the content between the
CHANGELOG:START / CHANGELOG:END markers is touched.

Usage:
    python scripts/gen_changelog.py            # update README.md in place
    python scripts/gen_changelog.py --check    # exit 1 if README is out of date
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"

START = "<!-- CHANGELOG:START (do not edit this block by hand; auto-generated from git tags) -->"
END = "<!-- CHANGELOG:END -->"


def _version_key(tag: str) -> tuple:
    nums = re.findall(r"\d+", tag)
    return tuple(int(n) for n in nums)


def list_tags() -> list[str]:
    out = subprocess.check_output(
        ["git", "tag", "--list", "v*"], cwd=REPO_ROOT, text=True
    )
    tags = [t.strip() for t in out.splitlines() if t.strip()]
    return sorted(tags, key=_version_key, reverse=True)


def tag_date(tag: str) -> str:
    # Date of the commit the tag points to (works for both tag types).
    return subprocess.check_output(
        ["git", "log", "-1", "--format=%cd", "--date=short", tag],
        cwd=REPO_ROOT, text=True,
    ).strip()


def tag_description(tag: str) -> str:
    # Annotated-tag message body (empty string for lightweight tags).
    body = subprocess.check_output(
        ["git", "for-each-ref", f"refs/tags/{tag}", "--format=%(contents)"],
        cwd=REPO_ROOT, text=True,
    ).strip()
    if body:
        return body.splitlines()[0].strip()
    # Fall back to the tagged commit's subject line.
    return subprocess.check_output(
        ["git", "log", "-1", "--format=%s", tag],
        cwd=REPO_ROOT, text=True,
    ).strip()


def _format_line(tag: str) -> str:
    # Date + description, with the version kept in a hidden HTML comment so the
    # script can de-duplicate without showing the tag in the rendered README.
    return f"- **{tag_date(tag)}** — {tag_description(tag)} <!--{tag}-->"


def build_block() -> str:
    return "\n".join(_format_line(tag) for tag in list_tags())


# Match the version stored in the trailing hidden comment, e.g. "<!--v0.1.7-->".
_LINE_TAG_RE = re.compile(r"<!--\s*(v\d+(?:\.\d+)*)\s*-->")


def existing_block(readme_text: str) -> str:
    m = re.search(
        re.escape(START) + r"\n(.*?)\n" + re.escape(END), readme_text, re.DOTALL
    )
    return m.group(1) if m else ""


def listed_tags(block: str) -> set[str]:
    found = set()
    for line in block.splitlines():
        m = _LINE_TAG_RE.search(line)
        if m:
            found.add(m.group(1))
    return found


def merge_block(existing: str) -> str:
    """Prepend any tags not already present; keep existing lines verbatim."""
    have = listed_tags(existing)
    new_tags = [t for t in list_tags() if t not in have]  # newest-first
    new_lines = [_format_line(t) for t in new_tags]
    existing_lines = [ln for ln in existing.splitlines() if ln.strip()]
    return "\n".join(new_lines + existing_lines)


def render(readme_text: str, block: str) -> str:
    pattern = re.compile(
        re.escape(START) + r".*?" + re.escape(END), re.DOTALL
    )
    replacement = f"{START}\n{block}\n{END}"
    if not pattern.search(readme_text):
        raise SystemExit(
            f"Markers not found in {README}. Expected:\n  {START}\n  {END}"
        )
    return pattern.sub(replacement, readme_text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check", action="store_true",
        help="Exit 1 if README is out of date instead of rewriting it.",
    )
    args = parser.parse_args()

    current = README.read_text(encoding="utf-8")
    block = merge_block(existing_block(current))
    updated = render(current, block)

    if args.check:
        if current != updated:
            print("README changelog is out of date. Run: python scripts/gen_changelog.py")
            return 1
        print("README changelog is up to date.")
        return 0

    if current != updated:
        README.write_text(updated, encoding="utf-8")
        print("README changelog updated.")
    else:
        print("README changelog already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
