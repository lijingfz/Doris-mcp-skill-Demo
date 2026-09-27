"""Offline tests for doris/publish_semantic.py (no Doris connection).

    .venv/bin/python -m unittest discover -s doris/test -v

The store is a fake with upstream DorisStore's staging semantics (store/store.py: fetch,
staging_list/discard/upsert/delete/fetch/commit); the offline model checks run for real.
The live publish is the T2.5 GATE step.
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp-server" / "src"))
sys.path.insert(0, str(ROOT / "doris"))

import pymysql  # noqa: E402

import publish_semantic  # noqa: E402
from publish_semantic import PublishError, offline_check, read_models  # noqa: E402
from store.store import StoreState  # noqa: E402

MODELS = ROOT / "doris" / "semantic" / "ecom"
PASSWORD = "RootPw0123456789abcXYZ"
ENV = {"DORIS_HOST": "10.0.0.1", "DORIS_PORT": "9030", "DORIS_ADMIN_USER": "root",
       "DORIS_ADMIN_PASSWORD": PASSWORD, "APPLY": "1"}
LOCAL = read_models(MODELS)


def setUpModule():
    logging.disable(logging.WARNING)  # MetricFlow logs parse errors at ERROR; the tests assert on them


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeStore:
    """In-memory DorisStore: active files, staging rows (action, content), semantic_version."""

    def __init__(self, active=None, staging=None, version=1, workspace="ecom"):
        self.workspace = workspace
        self.active = dict(active or {})
        self.staging = dict(staging or {})
        self.version = version
        self.calls = []

    @staticmethod
    def _write(local_dir, files):
        local_dir.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (local_dir / name).write_text(content, encoding="utf-8")

    def _state(self):
        return StoreState(revision=str(self.version), semantic_version=self.version)

    def fetch(self, local_dir):
        self.calls.append("fetch")
        self._write(local_dir, self.active)
        return self._state()

    def staging_list(self):
        self.calls.append("staging_list")
        return [{"filename": n, "action": a} for n, (a, _) in sorted(self.staging.items())]

    def staging_discard(self):
        self.calls.append("staging_discard")
        self.staging.clear()

    def staging_upsert(self, name, content):
        self.calls.append(("upsert", name))
        self.staging[name] = ("upsert", content)

    def staging_delete(self, name):
        self.calls.append(("delete", name))
        if name in self.staging:
            del self.staging[name]
            return "removed"
        if name in self.active:
            self.staging[name] = ("delete", None)
            return "staged"
        return "not_found"

    def _merged(self):
        merged = dict(self.active)
        for name, (action, content) in self.staging.items():
            if action == "delete":
                merged.pop(name, None)
            else:
                merged[name] = content
        return merged

    def staging_fetch(self, local_dir):
        self.calls.append("staging_fetch")
        self._write(local_dir, self._merged())
        return StoreState(revision="merged")

    def staging_commit(self):
        self.calls.append("staging_commit")
        if self.staging:
            self.active = self._merged()
            self.staging.clear()
            self.version += 1
        return self._state()

    def writes(self):
        return [c for c in self.calls if c not in ("fetch", "staging_list", "staging_fetch")]


def run_main(argv=(), env=ENV, store=None, physical=None):
    out, err, seen = io.StringIO(), io.StringIO(), {"factory": [], "physical": []}

    def factory(workspace):
        seen["factory"].append(workspace)
        return store

    def check(models_dir):
        seen["physical"].append((models_dir, len(seen["factory"])))
        return physical or (True, "")

    rc = publish_semantic.main(list(argv), env=env, out=out, err=err, store_factory=factory, physical_check=check)
    return rc, out.getvalue(), err.getvalue(), seen


def models_copy(test):
    tmp = Path(tempfile.mkdtemp(prefix="publish_models_"))
    test.addCleanup(shutil.rmtree, tmp, True)
    shutil.copytree(MODELS, tmp / "m")
    return tmp / "m"


class ReadModels(unittest.TestCase):
    def test_reads_every_yaml_file_by_name(self):
        self.assertEqual(sorted(LOCAL), sorted(p.name for p in MODELS.glob("*.yaml")))
        self.assertEqual(LOCAL["project.yaml"], (MODELS / "project.yaml").read_text(encoding="utf-8"))

    def test_ignores_non_yaml_files(self):
        m = models_copy(self)
        (m / "notes.txt").write_text("x", encoding="utf-8")
        self.assertEqual(read_models(m), LOCAL)


class OfflineCheck(unittest.TestCase):
    def test_returns_the_metric_names(self):
        self.assertEqual(len(offline_check(MODELS)), 22)
        self.assertIn("gmv_yoy", offline_check(MODELS))

    def test_duplicate_model_name_is_rejected(self):
        m = models_copy(self)
        shutil.copy(m / "shops.yaml", m / "shops_copy.yaml")
        with self.assertRaisesRegex(PublishError, "shops"):
            offline_check(m)

    def test_duplicate_measure_is_rejected(self):
        # Bootstrap and the engine accept it; MetricFlow would silently keep only one `gmv`.
        m = models_copy(self)
        refunds = m / "refunds.yaml"
        refunds.write_text(refunds.read_text(encoding="utf-8").replace("- name: refund_amount", "- name: gmv"),
                           encoding="utf-8")
        with self.assertRaisesRegex(PublishError, "Duplicate measure 'gmv'"):
            offline_check(m)

    def test_engine_init_failure_is_rejected(self):
        # Bootstrap accepts a measure model without agg_time_dimension; upstream validate_staging would
        # pass it and every query_metric on the workspace would then fail.
        m = models_copy(self)
        refunds = m / "refunds.yaml"
        text = refunds.read_text(encoding="utf-8")
        refunds.write_text(text.replace("  defaults:\n    agg_time_dimension: apply_date\n", ""), encoding="utf-8")
        self.assertNotEqual(refunds.read_text(encoding="utf-8"), text)
        with self.assertRaisesRegex(PublishError, "MetricFlow engine"):
            offline_check(m)

    def test_unparseable_models_are_rejected(self):
        m = models_copy(self)
        (m / "metrics.yaml").write_text("metric:\n  name: [unclosed\n", encoding="utf-8")
        with self.assertRaises(PublishError):
            offline_check(m)


class DryRun(unittest.TestCase):
    def test_dry_run_checks_offline_and_never_connects(self):
        env = {k: v for k, v in ENV.items() if k not in ("APPLY", "DORIS_ADMIN_PASSWORD")}
        rc, out, err, seen = run_main(env=env, store=FakeStore())
        self.assertEqual(rc, 0, err)
        self.assertEqual(seen, {"factory": [], "physical": []})
        self.assertIn("offline checks ok: 10 files, 22 metrics, 9 physical tables", out)
        self.assertIn("DRY-RUN: would publish workspace=ecom as root", out)
        self.assertIn("metrics.yaml", out)
        self.assertIn("APPLY=1 to publish", out)
        self.assertNotIn("10.0.0.1", out + err)

    def test_broken_models_fail_before_anything_else(self):
        m = models_copy(self)
        shutil.copy(m / "shops.yaml", m / "shops_copy.yaml")
        store = FakeStore()
        rc, _, err, seen = run_main(["--models", str(m)], store=store)
        self.assertEqual(rc, 1)
        self.assertIn("FAILED", err)
        self.assertEqual((seen["factory"], seen["physical"], store.calls), ([], [], []))

    def test_missing_or_empty_models_dir_is_a_usage_error(self):
        empty = Path(tempfile.mkdtemp(prefix="publish_empty_"))
        self.addCleanup(shutil.rmtree, empty, True)
        for models in (empty, empty / "nope"):
            with self.subTest(models=models):
                rc, _, err, _ = run_main(["--models", str(models)], store=FakeStore())
                self.assertEqual(rc, 2)
                self.assertIn("no YAML files", err)

    def test_workspace_must_be_an_identifier(self):
        # The name becomes part of table names: system_mcp.active_store_<workspace>.
        rc, _, err, seen = run_main(["--workspace", "ecom; DROP TABLE x"], store=FakeStore())
        self.assertEqual(rc, 2)
        self.assertIn("workspace", err)
        self.assertEqual(seen["factory"], [])


class Apply(unittest.TestCase):
    def test_first_publish_uploads_every_file_and_bumps_the_version(self):
        store = FakeStore()
        rc, out, err, seen = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual(store.active, LOCAL)
        self.assertEqual(store.version, 2)
        self.assertEqual(seen["factory"], ["ecom"])
        self.assertIn("published workspace=ecom semantic_version=2", out)
        self.assertIn("+10 ~0 -0", out)

    def test_physical_check_runs_before_the_store_is_opened(self):
        # DorisStore('ecom') already writes (CREATE TABLE IF NOT EXISTS + metadata row).
        _, _, _, seen = run_main(store=FakeStore())
        self.assertEqual(seen["physical"], [(MODELS, 0)])

    def test_staging_is_discarded_before_upserts_and_committed_last(self):
        store = FakeStore(staging={"junk.yaml": ("upsert", "semantic_model: {}")})
        rc, _, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        writes = store.writes()
        self.assertEqual(writes[0], "staging_discard")
        self.assertEqual(writes[-1], "staging_commit")
        self.assertNotIn("junk.yaml", store.active)

    def test_changed_and_stale_remote_files_are_replaced_and_deleted(self):
        active = dict(LOCAL, **{"old.yaml": "semantic_model: {}", "shops.yaml": "stale"})
        store = FakeStore(active=active, version=5)
        rc, out, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual(store.active, LOCAL)
        self.assertIn(("delete", "old.yaml"), store.calls)
        self.assertIn("published workspace=ecom semantic_version=6", out)
        self.assertIn("+0 ~1 -1", out)

    def test_up_to_date_store_is_left_alone(self):
        store = FakeStore(active=LOCAL, version=7)
        rc, out, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual(store.writes(), [])
        self.assertIn("up to date: workspace=ecom semantic_version=7", out)

    def test_leftover_staging_is_not_up_to_date(self):
        # Someone's pending rows would be committed by the next Web UI commit: clear them via a full publish.
        store = FakeStore(active=LOCAL, staging={"junk.yaml": ("upsert", "semantic_model: {}")}, version=4)
        rc, out, err, _ = run_main(store=store)
        self.assertEqual(rc, 0, err)
        self.assertEqual((store.active, store.staging, store.version), (LOCAL, {}, 5))
        self.assertIn("published workspace=ecom semantic_version=5", out)

    def test_failed_physical_check_stops_before_any_write(self):
        store = FakeStore()
        rc, _, err, seen = run_main(store=store, physical=(False, "Table internal.ecom.dim_brand: 1142 denied"))
        self.assertEqual(rc, 1)
        self.assertIn("dim_brand", err)
        self.assertEqual((seen["factory"], store.calls), ([], []))

    def test_merged_staging_must_equal_the_local_models(self):
        class DroppingStore(FakeStore):  # like upstream push, which silently skips files
            def staging_upsert(self, name, content):
                if name != "metrics.yaml":
                    super().staging_upsert(name, content)

        store = DroppingStore()
        rc, _, err, _ = run_main(store=store)
        self.assertEqual(rc, 1)
        self.assertIn("metrics.yaml", err)
        self.assertNotIn("staging_commit", store.calls)
        self.assertEqual((store.staging, store.calls[-1]), ({}, "staging_discard"))

    def test_active_must_equal_the_local_models_after_commit(self):
        class LossyStore(FakeStore):
            def staging_commit(self):
                self.calls.append("staging_commit")
                self.staging.clear()
                self.version += 1
                return self._state()

        rc, _, err, _ = run_main(store=LossyStore())
        self.assertEqual(rc, 1)
        self.assertIn("after commit", err)

    def test_semantic_version_must_advance(self):
        # ensure_fresh on the MCP side only reloads when semantic_version changes.
        class StuckStore(FakeStore):
            def staging_commit(self):
                version = self.version
                state = super().staging_commit()
                self.version = version
                return StoreState(revision=str(version), semantic_version=version)

        rc, _, err, _ = run_main(store=StuckStore(version=3))
        self.assertEqual(rc, 1)
        self.assertIn("semantic_version did not advance", err)

    def test_missing_environment_is_a_usage_error(self):
        for key in ("DORIS_HOST", "DORIS_ADMIN_USER", "DORIS_ADMIN_PASSWORD"):
            with self.subTest(missing=key):
                env = {k: v for k, v in ENV.items() if k != key}
                rc, _, err, seen = run_main(env=env, store=FakeStore())
                self.assertEqual(rc, 2)
                self.assertIn(key, err)
                self.assertEqual(seen["physical"], [])

    def test_database_errors_are_masked(self):
        class DeniedStore(FakeStore):
            def staging_discard(self):
                raise pymysql.OperationalError(2003, f"Can't connect to MySQL server on '10.0.0.1' ({PASSWORD})")

        rc, out, err, _ = run_main(store=DeniedStore())
        self.assertEqual(rc, 1)
        self.assertNotIn(PASSWORD, out + err)
        self.assertNotIn("10.0.0.1", out + err)
        self.assertIn("***", err)


class Wiring(unittest.TestCase):
    def test_default_store_and_physical_check_use_the_admin_connection(self):
        store = FakeStore()
        with mock.patch.object(publish_semantic, "set_doris_endpoint") as endpoint, \
                mock.patch.object(publish_semantic, "set_request_credentials") as creds, \
                mock.patch.object(publish_semantic, "DorisStore", return_value=store) as doris_store, \
                mock.patch.object(publish_semantic, "pre_validate_physical", return_value=(True, "")) as physical:
            rc = publish_semantic.main([], env=ENV, out=io.StringIO(), err=io.StringIO())
        self.assertEqual(rc, 0)
        endpoint.assert_called_once_with("10.0.0.1", 9030)
        creds.assert_called_once_with("root", PASSWORD)
        doris_store.assert_called_once_with("ecom")
        physical.assert_called_once_with(MODELS, db_host="10.0.0.1", db_port=9030, db_user="root",
                                         db_password=PASSWORD)

    def test_never_runs_upstream_grant_or_commit_hooks(self):
        # upstream commit_staging GRANTs SELECT_PRIV on system_mcp.* and every model table TO '%'.
        source = Path(publish_semantic.__file__).read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"grant_select_on_physical_tables|grant_workspace_access|commit_staging\(",
                                    source))


if __name__ == "__main__":
    unittest.main()
