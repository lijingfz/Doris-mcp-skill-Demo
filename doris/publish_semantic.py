"""Publish the ecom semantic models to the Doris semantic store (P2 / T2.5; design §6.3, plan C).

Normally invoked through doris/publish-semantic.sh, which supplies the environment:
    python doris/publish_semantic.py [--models DIR] [--workspace ecom]           # dry-run: offline only
    APPLY=1 python doris/publish_semantic.py [--models DIR] [--workspace ecom]   # GATE: publish as admin

env    DORIS_HOST, DORIS_PORT (9030), DORIS_ADMIN_USER, DORIS_ADMIN_PASSWORD (APPLY=1 only); APPLY=1 publishes
Runs upstream's store layer in-process: no MCP server, no admin-role check and none of upstream
commit_staging's follow-ups (reload, GRANT SELECT_PRIV ... TO '%'). The gate mirrors upstream
validate_staging and adds the engine check it skips: the models must bootstrap, initialise the
MetricFlow engine, have no duplicate model/measure names and pass pre_validate_physical (DESCRIBE);
the merged active+staging set must equal the local files before staging_commit, and the active
set must equal them afterwards. Exit 0 ok (published or up to date), 1 failure, 2 usage/configuration.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, TextIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
MODELS_DIR = ROOT / "doris" / "semantic" / "ecom"

import pymysql  # noqa: E402

from store.bootstrap import bootstrap_from_yaml, collect_physical_tables, pre_validate_physical  # noqa: E402
from store.compiler import MetricFlowCompiler  # noqa: E402
from store.manifest import SemanticManifest  # noqa: E402
from store.store import DorisStore, set_doris_endpoint, set_request_credentials  # noqa: E402
from store.watcher import _check_staging_duplicates  # noqa: E402

MASK = "***"
_WORKSPACE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")  # upstream workspace/create rule


class PublishError(RuntimeError):
    """The models or the store failed a check; messages never contain secret values."""


def read_models(models_dir: Path) -> dict[str, str]:
    """{relative name: text} of every *.yml / *.yaml file under models_dir (empty if it does not exist)."""
    if not models_dir.is_dir():
        return {}
    return {p.relative_to(models_dir).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(models_dir.rglob("*")) if p.suffix in (".yml", ".yaml") and p.is_file()}


def offline_check(models_dir: Path) -> list[str]:
    """Upstream's validate gate plus the engine init it skips; returns the sorted metric names."""
    errors, _warnings = _check_staging_duplicates(models_dir)
    if errors:
        raise PublishError(errors[0])
    with tempfile.TemporaryDirectory(prefix="publish_ws_") as tmp:
        ws = Path(tmp)
        ok, error = bootstrap_from_yaml(models_dir, ws)
        if not ok:
            raise PublishError(f"bootstrap: {error}")
        compiler = MetricFlowCompiler(ws)
        if not compiler.is_engine_mode:
            raise PublishError(f"MetricFlow engine: {compiler.init_error}")
        manifest = SemanticManifest(ws / "target" / "semantic_manifest.json")
        return sorted(m["name"] for m in manifest.list_metrics())


def _differing(a: Mapping[str, str], b: Mapping[str, str]) -> list[str]:
    return sorted(n for n in a.keys() | b.keys() if a.get(n) != b.get(n))


def publish(store: Any, local: Mapping[str, str], out: TextIO) -> int:
    """Make the store's active models equal `local`; returns the published semantic_version."""
    with tempfile.TemporaryDirectory(prefix="publish_") as tmp:
        before = store.fetch(Path(tmp, "active"))
        remote = read_models(Path(tmp, "active"))
        pending = store.staging_list()
        added = sorted(local.keys() - remote.keys())
        removed = sorted(remote.keys() - local.keys())
        changed = sorted(n for n in local.keys() & remote.keys() if local[n] != remote[n])
        print(f"remote: semantic_version={before.semantic_version}, {len(remote)} files; "
              f"staging: {len(pending)} rows", file=out)
        if not (added or changed or removed or pending):
            print(f"up to date: workspace={store.workspace} semantic_version={before.semantic_version}", file=out)
            return before.semantic_version
        print(f"plan: add {added}, change {changed}, remove {removed}", file=out)

        store.staging_discard()
        for name in sorted(local):
            store.staging_upsert(name, local[name])
        for name in removed:
            store.staging_delete(name)
        store.staging_fetch(Path(tmp, "merged"))
        differing = _differing(read_models(Path(tmp, "merged")), local)
        if differing:
            store.staging_discard()
            raise PublishError(f"merged staging differs from the local models in {differing}; staging discarded")
        after = store.staging_commit()

        store.fetch(Path(tmp, "published"))
        differing = _differing(read_models(Path(tmp, "published")), local)
        if differing:
            raise PublishError(f"active models differ from the local models after commit in {differing}")
    if after.semantic_version <= before.semantic_version:
        raise PublishError(f"semantic_version did not advance ({before.semantic_version} -> "
                           f"{after.semantic_version})")
    print(f"published workspace={store.workspace} semantic_version={after.semantic_version} "
          f"({len(local)} files: +{len(added)} ~{len(changed)} -{len(removed)})", file=out)
    return after.semantic_version


def _doris_store(workspace: str, *, host: str, port: int, user: str, password: str) -> DorisStore:
    set_doris_endpoint(host, port)
    set_request_credentials(user, password)  # store connections run as the admin, updated_by = admin
    return DorisStore(workspace)  # CREATE DATABASE/TABLE IF NOT EXISTS + metadata row


def _mask(text: str, secrets: Sequence[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, MASK)
    return text


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None,
         out: TextIO = sys.stdout, err: TextIO = sys.stderr,
         store_factory: Callable[[str], Any] | None = None,
         physical_check: Callable[[Path], tuple[bool, str]] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish semantic models to the Doris semantic store.")
    parser.add_argument("--models", type=Path, default=MODELS_DIR, help="local semantic YAML directory")
    parser.add_argument("--workspace", default="ecom", help="semantic workspace")
    args = parser.parse_args(argv)
    env = os.environ if env is None else env

    if not _WORKSPACE_RE.match(args.workspace):
        print(f"ERROR: workspace must match {_WORKSPACE_RE.pattern}", file=err)
        return 2
    local = read_models(args.models)
    if not local:
        print(f"ERROR: no YAML files in {args.models}", file=err)
        return 2

    logging.disable(logging.WARNING)  # MetricFlow and the store are chatty below ERROR
    try:
        metrics = offline_check(args.models)
        tables = collect_physical_tables(args.models)
    except PublishError as e:
        print(f"FAILED: offline checks: {e}", file=err)
        return 1
    print(f"offline checks ok: {len(local)} files, {len(metrics)} metrics, {len(tables)} physical tables "
          "(bootstrap, MetricFlow engine, duplicate names)", file=out)

    admin = env.get("DORIS_ADMIN_USER") or "<admin>"
    if env.get("APPLY") != "1":
        ws = args.workspace
        print(f"DRY-RUN: would publish workspace={ws} as {admin}:", file=out)
        for name, text in local.items():
            data = text.encode("utf-8")
            print(f"  file: {name} ({len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:12]})", file=out)
        print(f"  1. pre_validate_physical: DESCRIBE the {len(tables)} physical tables, check column exprs", file=out)
        print(f"  2. DorisStore('{ws}'): CREATE DATABASE/TABLE IF NOT EXISTS "
              f"system_mcp.{{workspace_metadata,active_store_{ws},staging_store_{ws}}}", file=out)
        print(f"  3. compare active_store_{ws} with the local files; stop if equal and staging is empty", file=out)
        print(f"  4. staging: discard, upsert {len(local)} files, delete remote files not in {args.models}", file=out)
        print("  5. merged staging == local -> staging_commit (semantic_version + 1) -> active == local", file=out)
        print("DRY-RUN: no GRANT is executed; APPLY=1 to publish", file=out)
        return 0

    missing = [k for k in ("DORIS_HOST", "DORIS_ADMIN_USER", "DORIS_ADMIN_PASSWORD") if not env.get(k)]
    if missing:
        print(f"ERROR: missing environment: {', '.join(missing)}", file=err)
        return 2
    host, port = env["DORIS_HOST"], int(env.get("DORIS_PORT") or 9030)
    password = env["DORIS_ADMIN_PASSWORD"]
    connection = {"host": host, "port": port, "user": admin, "password": password}
    factory = store_factory or functools.partial(_doris_store, **connection)
    physical = physical_check or functools.partial(
        pre_validate_physical, db_host=host, db_port=port, db_user=admin, db_password=password)
    try:
        ok, error = physical(args.models)
        if not ok:
            raise PublishError(f"physical check: {error}")
        print(f"physical check ok: {len(tables)} tables and their column exprs exist", file=out)
        publish(factory(args.workspace), local, out)
    except (RuntimeError, OSError, pymysql.MySQLError) as e:
        print(f"FAILED: {_mask(str(e), [password, host])}", file=err)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
