import unittest

from taiwan_stock_analysis.traceability import (
    build_artifact_registry,
    build_run_metadata,
    merge_traceability,
    read_run_metadata,
)


class TraceabilityTests(unittest.TestCase):
    def test_build_run_metadata_preserves_explicit_identity_and_context(self):
        metadata = build_run_metadata(
            "workflow",
            "workflow run",
            {"watchlist": "watchlist.csv"},
            "dist",
            generated_at="2026-05-13T12:00:00Z",
            run_id="workflow-20260513T120000Z",
        )

        self.assertEqual(metadata["run_id"], "workflow-20260513T120000Z")
        self.assertEqual(metadata["generated_at"], "2026-05-13T12:00:00Z")
        self.assertEqual(metadata["kind"], "workflow")
        self.assertEqual(metadata["command"], "workflow run")
        self.assertEqual(metadata["inputs"], {"watchlist": "watchlist.csv"})
        self.assertEqual(metadata["output_root"], "dist")

    def test_read_run_metadata_returns_valid_metadata_and_ignores_invalid_payloads(self):
        metadata = build_run_metadata(
            "workflow",
            "workflow run",
            {},
            "dist",
            generated_at="2026-05-13T12:00:00Z",
            run_id="workflow-20260513T120000Z",
        )

        self.assertEqual(read_run_metadata({"run_metadata": metadata}), metadata)
        self.assertEqual(read_run_metadata({"run_metadata": "workflow"}), {})
        self.assertEqual(read_run_metadata({"run_metadata": {"run_id": "workflow-20260513T120000Z"}}), {})
        self.assertEqual(read_run_metadata({}), {})

    def test_build_artifact_registry_keeps_shape_consistent(self):
        registry = build_artifact_registry(
            "dist/workflow_summary.json",
            dependencies={"watchlist": "watchlist.csv"},
            outputs={"dashboard": "dist/dashboard.html"},
        )

        self.assertEqual(registry["self"], "dist/workflow_summary.json")
        self.assertEqual(registry["dependencies"], {"watchlist": "watchlist.csv"})
        self.assertEqual(registry["outputs"], {"dashboard": "dist/dashboard.html"})

    def test_merge_traceability_returns_payload_with_metadata_sections(self):
        metadata = build_run_metadata(
            "workflow",
            "workflow run",
            {},
            "dist",
            generated_at="2026-05-13T12:00:00Z",
            run_id="workflow-20260513T120000Z",
        )
        registry = build_artifact_registry("dist/workflow_summary.json")

        merged = merge_traceability({"status": "ok"}, run_metadata=metadata, artifact_registry=registry)

        self.assertEqual(merged["status"], "ok")
        self.assertEqual(merged["run_metadata"], metadata)
        self.assertEqual(merged["artifact_registry"], registry)


if __name__ == "__main__":
    unittest.main()
