#!/usr/bin/env python3
"""Write quick/skills/: copies of apache/doris-skills for Quick, next to the hand-written doris-mcp-adapter (P5 / T5.1).

  git clone https://github.com/apache/doris-skills /tmp/doris-skills
  git -C /tmp/doris-skills checkout 0476f3b84adeee4df75bc7ed694980306f8c6ab8
  .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills           # (re)write quick/skills/
  .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check   # compare only, write nothing

The copies are upstream's files at LOCKED_COMMIT (read from git objects, not from the clone's working tree) with the
edits recorded in the constants below: the adapter hint in every SKILL.md, the description overrides and the link
fixes. UPSTREAM.md is generated from the same constants. Only the SKILLS folders and the generated top-level files
are written; quick/skills/doris-mcp-adapter/ and anything else there is never touched. Prints paths and counts,
never file contents.
Exit code: 0 when written / (--check) identical, 1 when --check finds a difference, 2 when the clone is not at
LOCKED_COMMIT, upstream no longer matches the constants, or the arguments are wrong.
"""

import argparse
import posixpath
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE_URL = "https://github.com/apache/doris-skills"
LOCKED_COMMIT = "0476f3b84adeee4df75bc7ed694980306f8c6ab8"
UPSTREAM_MD = "UPSTREAM.md"
DESCRIPTION_LIMIT = 1024  # characters of the parsed `description`: Quick's skill import limit
WRAP = 88  # line width of a folded description override (upstream's lines are about as long)

SKILLS = ("doris-architecture-advisor", "doris-best-practices", "doris-debug", "doris-profile-reader")
# Also copied: Apache-2.0 wants the licence with the copies, and the contract lists the doriscli commands and JSON
# fields the skills use, which is what doris-mcp-adapter maps to the MCP tools.
TOP_LEVEL_FILES = ("LICENSE.txt", "CLI-CONTRACT.md")
# Every other upstream top-level entry and skill, with the reason it is left out. An upstream entry that is neither
# imported nor listed here (a new skill, a NOTICE file) stops the build.
EXCLUDED = {
    "skills/doris-repo-review/": "reviews Apache Doris source-code pull requests in a local clone (git, gh); "
                                 "it never talks to a cluster",
    "README.md": "upstream's overview and install guide (npx skills, doriscli); UPSTREAM.md takes its place",
    "verify/": "upstream's regression tests against a live cluster through doriscli, not skill content",
    ".asf.yaml": "Apache infrastructure settings of the upstream repository",
    ".gitignore": "upstream's git settings",
}

# The first body line of every copied SKILL.md (top-level and nested), followed by one blank line.
HINT = ("> **Environment:** Amazon Quick with the Doris MCP tools (`doris___*`), not `doriscli`. "
        "Load the `doris-mcp-adapter` skill and map every command below through it.")

# Upstream descriptions over DESCRIPTION_LIMIT, condensed in upstream's words with every trigger kept.
DESCRIPTION_OVERRIDES = {
    "doris-architecture-advisor": (
        "Workload-aware architecture design for Apache Doris. MUST USE when designing data architectures, "
        "choosing data models, planning ingestion, sizing clusters, or turning business requirements into "
        "Apache Doris designs. Use for IoT/sensor/telemetry, real-time analytics, dashboards, log analysis, "
        "log search, CDC sync, time-series, device monitoring, point query, ad-hoc analytics, lakehouse "
        "federation, ETL/ELT, report analytics, clickstream, user behavior, observability, metrics, fleet "
        "tracking, or any OLAP table design from scratch. Also triggers on \"design a table for...\", "
        "\"how should I store...\", \"build an architecture for...\", \"we have X devices sending data every Y "
        "seconds\", \"recommend a cluster size\", \"what data model should I use\", \"we need to ingest X "
        "GB/day\", and on migrating from or replacing MySQL/PostgreSQL, Impala, Kudu, Elasticsearch/ES, "
        "Greenplum, Presto, HBase, Hive, Hadoop, Redis, or Lambda-style multi-engine platforms, even when Doris "
        "is not named."),
    "doris-best-practices": (
        "Apache Doris table design and cluster sizing best practices. MUST USE when writing, reviewing, or "
        "optimizing Doris CREATE TABLE statements, partition/bucket strategies, data models, or cluster "
        "configurations. ALSO MUST USE whenever the doris-architecture-advisor skill produces DDL — apply the "
        "Pre-Flight Checklist to every CREATE TABLE before output. Also triggers on any table design decision, "
        "e.g. for IoT, analytics, dashboard, CDC, time-series, log analysis, real-time warehouse, point query, "
        "or data platform workloads, and on replacing or migrating from Impala, Kudu, Elasticsearch/ES, "
        "Greenplum, Presto, HBase, Hive, Hadoop, Redis, or Lambda-style multi-engine platforms, even when Doris "
        "is not named. Also use when user provides a Doris connection string or asks to get started, and for "
        "slow query investigation, query profiling, runtime performance diagnosis, tablet skew analysis, and "
        "table health checks. Cluster lifecycle, billing, and networking are out of scope."),
}

# (file, old text): (new text, occurrences in upstream's file). Exact-text edits where the intended target is obvious.
LINK_FIXES = {
    # The router's name for shared/references/03-cir-case-index.md, the only 03-* file there ("45 cases").
    ("doris-debug/SKILL.md", "03-case-index.md"): ("03-cir-case-index.md", 3),
}
# (file, link target): reason. Relative links that resolve to nothing, kept as upstream wrote them.
_EXAMPLE_ANSWER = ("example answer inside a code block; the path is relative to the skills folder, where the "
                   "file exists")
BROKEN_LINKS_ALLOWED = {
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/rule-name.md"):
        "placeholder in the answer-format template",
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/schema-bucket-target-size.md"):
        _EXAMPLE_ANSWER,
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/schema-model-choose-for-workload.md"):
        _EXAMPLE_ANSWER,
    ("doris-architecture-advisor/SKILL.md", "doris-best-practices/references/schema-props-compression.md"):
        _EXAMPLE_ANSWER,
}

_FOLDED_DESCRIPTION = re.compile(r"^description: >\n((?: +\S.*\n)+)", re.M)
_LINK = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)")


class BuildError(Exception):
    """The clone or upstream does not match the constants; the message says what to change."""


def _git(source: Path, *args: str, stdin: bytes | None = None) -> bytes:
    run = subprocess.run(["git", "-C", str(source), *args], input=stdin, capture_output=True)
    if run.returncode:
        raise BuildError(f"git {args[0]} failed in {source}: {run.stderr.decode(errors='replace').strip()}")
    return run.stdout


def _check_commit(source: Path, commit: str) -> None:
    head = _git(source, "rev-parse", "HEAD").decode().strip()
    if head != commit:
        raise BuildError(f"{source} is at {head}, the builder is locked to {commit}; run\n"
                         f"  git -C {source} fetch\n  git -C {source} checkout {commit}")


def is_copy(rel: str) -> bool:
    """Whether an output path is an upstream copy: inside a SKILLS folder, or one of TOP_LEVEL_FILES."""
    return rel.split("/", 1)[0] in SKILLS or rel in TOP_LEVEL_FILES


def _select(paths: list[str]) -> dict[str, str]:
    """{upstream path: output path} of the imported files; every upstream entry must be imported or EXCLUDED."""
    entries = {"/".join(p.split("/")[:2]) if p.startswith("skills/") else p.split("/")[0] for p in paths}
    known = {f"skills/{s}" for s in SKILLS} | set(TOP_LEVEL_FILES) | {e.rstrip("/") for e in EXCLUDED}
    problems = [f"upstream has {e}: import it (SKILLS, TOP_LEVEL_FILES) or list it in EXCLUDED"
                for e in sorted(entries - known)]
    problems += [f"upstream no longer has {e}: update SKILLS, TOP_LEVEL_FILES or EXCLUDED"
                 for e in sorted(known - entries)]
    if problems:
        raise BuildError("; ".join(problems))
    return {p: p.removeprefix("skills/") for p in paths
            if p in TOP_LEVEL_FILES or (p.startswith("skills/") and p.split("/")[1] in SKILLS)}


def _read(source: Path, commit: str, paths: list[str]) -> dict[str, bytes]:
    """The content of `paths` at `commit`, from one `git cat-file --batch`."""
    data = _git(source, "cat-file", "--batch", stdin="".join(f"{commit}:{p}\n" for p in paths).encode())
    files, at = {}, 0
    for path in paths:
        eol = data.index(b"\n", at)
        size = int(data[at:eol].split()[2])
        files[path] = data[eol + 1:eol + 1 + size]
        at = eol + 2 + size  # the content is followed by a newline
    return files


def split_frontmatter(text: str, where: str) -> tuple[str, str]:
    """(frontmatter, body) of a SKILL.md: the file starts with a line `---`, the frontmatter ends at the next one."""
    end = text.find("\n---\n", 3)
    if not text.startswith("---\n") or end < 0:
        raise BuildError(f"{where}: no YAML frontmatter (a '---' line, the YAML, a '---' line)")
    return text[4:end + 1], text[end + 5:]


def _meta(frontmatter: str, where: str) -> dict:
    try:
        meta = yaml.safe_load(frontmatter)
    except yaml.YAMLError:
        raise BuildError(f"{where}: the frontmatter is not valid YAML") from None
    if not isinstance(meta, dict) or not isinstance(meta.get("description"), str) or not meta["description"].strip():
        raise BuildError(f"{where}: the frontmatter has no description")
    return meta


def _override_description(frontmatter: str, text: str, where: str) -> str:
    """Replace the value of a folded `description: >` block, keeping its indentation and every other byte."""
    block = _FOLDED_DESCRIPTION.search(frontmatter)
    if block is None:
        raise BuildError(f"{where}: the description is not a folded block ('description: >'); update the builder")
    indent = block.group(1)[:len(block.group(1)) - len(block.group(1).lstrip(" "))]
    lines = textwrap.wrap(text, WRAP, initial_indent=indent, subsequent_indent=indent,
                          break_long_words=False, break_on_hyphens=False)
    return frontmatter[:block.start(1)] + "".join(f"{line}\n" for line in lines) + frontmatter[block.end(1):]


def _edit_skill_md(rel: str, text: str) -> tuple[str, tuple[int, int] | None]:
    """The copied SKILL.md and, if its description was overridden, (upstream length, new length).

    Result: `---` line, frontmatter (description overridden if listed), `---` line, HINT, one blank line, the body
    without its leading blank lines."""
    frontmatter, body = split_frontmatter(text, rel)
    skill = rel.split("/", 1)[0]
    lengths = None
    if rel == f"{skill}/SKILL.md" and skill in DESCRIPTION_OVERRIDES:
        before = len(_meta(frontmatter, rel)["description"])
        if before <= DESCRIPTION_LIMIT:
            raise BuildError(f"{rel}: upstream's description is {before} characters now, within the limit; "
                             "drop its DESCRIPTION_OVERRIDES entry")
        override = DESCRIPTION_OVERRIDES[skill]
        frontmatter = _override_description(frontmatter, override, rel)
        if _meta(frontmatter, rel)["description"].split() != override.split():
            raise BuildError(f"{rel}: the description override does not read back as written")
        lengths = (before, len(_meta(frontmatter, rel)["description"]))
    length = len(_meta(frontmatter, rel)["description"])
    if length > DESCRIPTION_LIMIT:
        raise BuildError(f"{rel}: the description is {length} characters, Quick allows {DESCRIPTION_LIMIT}; "
                         "add or shorten its DESCRIPTION_OVERRIDES entry")
    body = body.lstrip("\n")
    return f"---\n{frontmatter}---\n{HINT}\n\n{body}", lengths


def _apply_link_fixes(files: dict[str, bytes]) -> None:
    for (rel, old), (new, count) in sorted(LINK_FIXES.items()):
        text = files[rel].decode("utf-8") if rel in files else ""
        found = text.count(old)
        if found != count:
            raise BuildError(f"LINK_FIXES: {old!r} occurs {found} times in {rel}, expected {count}; upstream changed")
        files[rel] = text.replace(old, new).encode("utf-8")


def broken_links(files: dict[str, bytes]) -> set[tuple[str, str]]:
    """(file, target) of every relative Markdown link in the copied .md files that points at nothing in `files`.

    http(s)://, mailto: and #anchor links are skipped and a target's #anchor is dropped; the target is resolved
    against the linking file's folder and may be a file or a folder (a sibling copied skill counts)."""
    folders = {"/".join(p.split("/")[:i]) for p in files for i in range(1, p.count("/") + 1)}
    broken = set()
    for rel, data in files.items():
        if not (rel.endswith(".md") and is_copy(rel)):
            continue
        for target in _LINK.findall(data.decode("utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target.split("#", 1)[0]))
            if path not in files and path not in folders:
                broken.add((rel, target))
    return broken


def _check_links(files: dict[str, bytes]) -> None:
    broken, allowed = broken_links(files), set(BROKEN_LINKS_ALLOWED)
    problems = [f"broken link {target} in {rel}: fix it (LINK_FIXES) or list it in BROKEN_LINKS_ALLOWED"
                for rel, target in sorted(broken - allowed)]
    problems += [f"BROKEN_LINKS_ALLOWED: {target} in {rel} is not broken any more; drop the entry"
                 for rel, target in sorted(allowed - broken)]
    if problems:
        raise BuildError("; ".join(problems))


def _version(meta: dict) -> str:
    metadata = meta["metadata"] if isinstance(meta.get("metadata"), dict) else {}
    return str(meta.get("version") or metadata.get("version") or "-")


def _upstream_md(commit: str, date: str, files: dict[str, bytes], overridden: dict[str, tuple[int, int]],
                 notice: bool) -> str:
    rows = []
    for skill in SKILLS:
        inside = [p for p in files if p.startswith(f"{skill}/")]
        meta = _meta(split_frontmatter(files[f"{skill}/SKILL.md"].decode("utf-8"), skill)[0], skill)
        rows.append(f"| `{skill}/` | {len(inside)} | {sum(len(files[p]) for p in inside)} | {_version(meta)} |")
    skill_mds = sum(1 for p in files if posixpath.basename(p) == "SKILL.md")
    lines = [
        "# quick/skills: copies of apache/doris-skills", "",
        "Generated by `scripts/build_skills.py`: change its constants and rebuild, do not edit the copies by hand. "
        "`doris-mcp-adapter/` is hand-written and not generated.", "",
        f"- Source: {SOURCE_URL}", f"- Commit: `{commit}` (committed {date})", "",
        "## Rebuild and check", "",
        f"    git clone {SOURCE_URL} /tmp/doris-skills && git -C /tmp/doris-skills checkout {commit}",
        "    .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills           # rewrite the copies",
        "    .venv/bin/python scripts/build_skills.py --source /tmp/doris-skills --check   # compare only", "",
        "## Imported", "",
        "| Folder | Files | Bytes | Upstream version |", "|---|---:|---:|---|", *rows, "",
        "Also copied: " + ", ".join(f"`{name}`" for name in TOP_LEVEL_FILES) + ".", "",
        "## Changes to upstream", "",
        f"- Every `SKILL.md` ({skill_mds}, top-level and nested) starts its body with this line and one blank line "
        "(the body's own leading blank lines are dropped):", "", f"  {HINT}", "",
        f"- Descriptions over Quick's {DESCRIPTION_LIMIT}-character limit, rewritten shorter with the same triggers "
        "(the other frontmatter lines are upstream's):",
        *(f"  - `{rel}`: {old} -> {new} characters" for rel, (old, new) in sorted(overridden.items())),
        "- Link fixes:",
        *(f"  - `{rel}`: `{old}` -> `{new}` ({count}x)" for (rel, old), (new, count) in sorted(LINK_FIXES.items())),
        "- Broken links kept as upstream wrote them:",
        *(f"  - `{rel}`: `{target}`: {why}" for (rel, target), why in sorted(BROKEN_LINKS_ALLOWED.items())),
        "- Only file contents are copied: executable bits are not kept.", "",
        "## Not imported", "",
        *(f"- `{entry}`: {why}" for entry, why in EXCLUDED.items()), "",
        "## Licence", "",
        "Apache License 2.0: `LICENSE.txt` is upstream's. The copies are upstream's files, unmodified except for the "
        "changes listed above." + ("" if notice else " Upstream has no NOTICE file at this commit."),
    ]
    return "\n".join(lines) + "\n"


def render(source: Path, commit: str = LOCKED_COMMIT) -> dict[str, bytes]:
    """{output path: content} of the generated tree (the copies and UPSTREAM.md); writes nothing."""
    _check_commit(source, commit)
    upstream = [p for p in _git(source, "ls-tree", "-r", "-z", "--name-only", commit).decode().split("\0") if p]
    selected = _select(upstream)
    content = _read(source, commit, sorted(selected))
    files = {rel: content[path] for path, rel in selected.items()}
    for skill in SKILLS:
        if f"{skill}/SKILL.md" not in files:
            raise BuildError(f"{skill}/SKILL.md is missing upstream: Quick needs a SKILL.md at the skill's root")
    _apply_link_fixes(files)
    overridden = {}
    for rel in sorted(files):
        if posixpath.basename(rel) == "SKILL.md":
            text, lengths = _edit_skill_md(rel, files[rel].decode("utf-8"))
            files[rel] = text.encode("utf-8")
            if lengths:
                overridden[rel] = lengths
    _check_links(files)
    date = _git(source, "log", "-1", "--format=%cs", commit).decode().strip()
    notice = any(p.upper().startswith("NOTICE") for p in upstream if "/" not in p)
    files[UPSTREAM_MD] = _upstream_md(commit, date, files, overridden, notice).encode("utf-8")
    return dict(sorted(files.items()))


def build(source: Path, out: Path, commit: str = LOCKED_COMMIT) -> list[str]:
    """Render, then write the tree into `out`: stale files inside the SKILLS folders go, nothing else is touched."""
    files = render(source, commit)
    for skill in SKILLS:
        for path in sorted((out / skill).rglob("*"), reverse=True):  # a folder's entries before the folder
            if path.is_dir():
                if not any(path.iterdir()):
                    path.rmdir()
            elif path.relative_to(out).as_posix() not in files:
                path.unlink()
    for rel, data in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
    return sorted(files)


def compare(files: dict[str, bytes], out: Path) -> list[str]:
    """`missing PATH` / `extra PATH` / `differs PATH` lines between a render and `out`, generated paths only."""
    present = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    present = {p for p in present if is_copy(p) or p == UPSTREAM_MD}
    found = [(p, "missing") for p in files if p not in present] + [(p, "extra") for p in present if p not in files]
    found += [(p, "differs") for p in present & set(files) if (out / p).read_bytes() != files[p]]
    return [f"{kind} {path}" for path, kind in sorted(found)]


def _shown(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, required=True, help=f"a clone of {SOURCE_URL} at LOCKED_COMMIT")
    parser.add_argument("--out", type=Path, default=ROOT / "quick" / "skills", help="default: quick/skills")
    parser.add_argument("--check", action="store_true", help="compare --out with a fresh render, write nothing")
    args = parser.parse_args(argv)
    name, commit = _shown(args.out), LOCKED_COMMIT
    try:
        if not args.check:
            written = build(args.source, args.out, commit)
            print(f"wrote {len(written)} files to {name} ({commit[:12]})", file=out)
            return 0
        files = render(args.source, commit)
    except BuildError as e:
        print(f"FAIL: {e}", file=out)
        return 2
    differences = compare(files, args.out)
    for line in differences:
        print(line, file=out)
    if differences:
        print(f"{name} does not match {commit[:12]}: {len(differences)} differences", file=out)
        return 1
    print(f"{name} matches {commit[:12]} ({len(files)} files)", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
