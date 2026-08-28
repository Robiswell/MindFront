from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDERER = REPO_ROOT / "project-tools" / "render-html-to-pdf-playwright.js"
WRAPPER = REPO_ROOT / "project-tools" / "render-mindfront-report-pdf.ps1"
NORMALIZER = REPO_ROOT / "project-tools" / "normalize-pdf-list-tags.py"
NODE = (
    Path.home()
    / ".cache"
    / "codex-runtimes"
    / "codex-primary-runtime"
    / "dependencies"
    / "node"
    / "bin"
    / "node.exe"
)
NODE_MODULES = NODE.parents[1] / "node_modules"
POWERSHELL = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _sha256_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _browser() -> Path | None:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    return next((candidate for candidate in candidates if candidate.is_file()), None)


class RenderTrustBoundaryTests(unittest.TestCase):
    maxDiff = None

    def _node_environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment["NODE_PATH"] = os.pathsep.join(
            [
                str(NODE_MODULES),
                str(NODE_MODULES / ".pnpm" / "node_modules"),
            ]
        )
        environment["MINDFRONT_PYTHON"] = sys.executable
        return environment

    def _call_renderer_function(self, function_name: str, html_path: Path) -> subprocess.CompletedProcess[str]:
        script = (
            "const renderer=require(process.argv[1]);"
            "try{const result=renderer[process.argv[2]](process.argv[3]);"
            "process.stdout.write(JSON.stringify(result));}"
            "catch(error){process.stderr.write(String(error.message||error));process.exit(19);}"
        )
        return subprocess.run(
            [str(NODE), "-e", script, str(RENDERER), function_name, str(html_path)],
            cwd=REPO_ROOT,
            env=self._node_environment(),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    @unittest.skipUnless(NODE.is_file(), "Bundled Node.js is unavailable.")
    def test_base_element_is_rejected_before_rendering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.html"
            source.write_text(
                '<!doctype html><base href="file:///C:/Windows/"><p>Blocked</p>',
                encoding="utf-8",
            )

            completed = self._call_renderer_function("assertStaticLocalDocument", source)

            self.assertEqual(completed.returncode, 19)
            self.assertIn("base elements", completed.stderr)

    @unittest.skipUnless(NODE.is_file(), "Bundled Node.js is unavailable.")
    def test_parent_directory_asset_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report"
            report.mkdir()
            outside = root / "outside.svg"
            outside.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
            source = report / "source.html"
            source.write_text(
                '<!doctype html><img src="../outside.svg" alt="escape">',
                encoding="utf-8",
            )

            completed = self._call_renderer_function("collectSnapshotDependencies", source)

            self.assertEqual(completed.returncode, 19)
            self.assertIn("outside the render snapshot", completed.stderr)

    @unittest.skipUnless(NODE.is_file(), "Bundled Node.js is unavailable.")
    def test_nested_css_asset_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report"
            assets = report / "assets"
            assets.mkdir(parents=True)
            (root / "outside.png").write_bytes(b"not-a-real-image")
            (assets / "style.css").write_text(
                "body { background: url('../../outside.png'); }",
                encoding="utf-8",
            )
            source = report / "source.html"
            source.write_text(
                '<!doctype html><link rel="stylesheet" href="assets/style.css"><p>Blocked</p>',
                encoding="utf-8",
            )

            completed = self._call_renderer_function("collectSnapshotDependencies", source)

            self.assertEqual(completed.returncode, 19)
            self.assertIn("outside the render snapshot", completed.stderr)

    @unittest.skipUnless(NODE.is_file(), "Bundled Node.js is unavailable.")
    def test_snapshot_inventory_binds_only_resolved_local_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            (assets / "logo.svg").write_text(
                "<svg xmlns='http://www.w3.org/2000/svg' width='20' height='20'></svg>",
                encoding="utf-8",
            )
            (root / "unreferenced.txt").write_text("not in snapshot", encoding="utf-8")
            source = root / "source.html"
            source.write_text(
                '<!doctype html><img src="assets/logo.svg" alt="logo"><p>Allowed</p>',
                encoding="utf-8",
            )

            completed = self._call_renderer_function("collectSnapshotDependencies", source)

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            paths = [entry["relativePath"] for entry in payload["files"]]
            self.assertEqual(paths, ["assets/logo.svg", "source.html"])
            self.assertNotIn("unreferenced.txt", paths)

    @unittest.skipUnless(
        NODE.is_file() and _browser() is not None,
        "The trusted local browser runtime is unavailable.",
    )
    def test_runtime_blocks_unquoted_asset_escape_missed_by_static_attribute_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report"
            report.mkdir()
            (root / "outside.svg").write_text(
                "<svg xmlns='http://www.w3.org/2000/svg'/>",
                encoding="utf-8",
            )
            source = report / "source.html"
            output = report / "blocked.pdf"
            source.write_text(
                "<!doctype html><html><body><img src=../outside.svg></body></html>",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [str(NODE), str(RENDERER), str(source), str(output), str(_browser())],
                cwd=REPO_ROOT,
                env=self._node_environment(),
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("Out-of-snapshot request blocked", completed.stderr)
            self.assertFalse(output.exists())
            self.assertFalse(Path(f"{output}.render-manifest.json").exists())

    @unittest.skipUnless(
        NODE.is_file() and POWERSHELL.is_file() and _browser() is not None,
        "The trusted local render toolchain is unavailable.",
    )
    def test_wrapper_replaces_forged_sidecar_and_copied_pdf_with_fresh_bound_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            assets = root / "assets"
            assets.mkdir()
            source = root / "source.html"
            logo = assets / "logo.svg"
            brief = root / "message-brief.json"
            output = root / "report.pdf"
            manifest_path = Path(f"{output}.render-manifest.json")
            raw_pdf_path = Path(f"{output}.raw.pdf")

            logo.write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="20">'
                    '<rect width="80" height="20" fill="#17185f"/></svg>'
                ),
                encoding="utf-8",
            )
            source.write_text(
                (
                    "<!doctype html><html><head><meta charset='utf-8'>"
                    "<style>@page{size:Letter;margin:.5in}body{font-family:Arial}</style>"
                    "</head><body><img src='assets/logo.svg' alt='logo'>"
                    "<h1>Trust boundary control</h1><p>Fresh render required.</p>"
                    "<ul><li>Bind the raw render.</li><li>Bind the normalized result.</li></ul>"
                    "</body></html>"
                ),
                encoding="utf-8",
            )
            brief.write_text(
                json.dumps(
                    {
                        "artifactType": "message_brief",
                        "recipient": "Executive reviewer",
                    }
                ),
                encoding="utf-8",
            )

            copied_pdf = b"%PDF-1.4\n% unrelated copied artifact\n%%EOF\n"
            output.write_bytes(copied_pdf)
            manifest_path.write_text(
                json.dumps(
                    {
                        "artifactType": "html_to_pdf_render_manifest",
                        "sourceHtmlSha256": _sha256(source),
                        "outputPdfSha256": _sha256(output),
                        "rendererScriptSha256": _sha256(RENDERER),
                        "listTagNormalization": {
                            "scriptSha256": _sha256(NORMALIZER),
                            "summary": {"status": "passed"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    str(POWERSHELL),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(WRAPPER),
                    "-InputHtml",
                    str(source),
                    "-InputBrief",
                    str(brief),
                    "-OutputPdf",
                    str(output),
                    "-BrowserPath",
                    str(_browser()),
                ],
                cwd=REPO_ROOT,
                env=self._node_environment(),
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertNotEqual(output.read_bytes(), copied_pdf)
            self.assertTrue(output.read_bytes().startswith(b"%PDF-"))
            self.assertTrue(raw_pdf_path.is_file())
            self.assertGreater(raw_pdf_path.stat().st_size, 0)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(manifest["schemaVersion"], 2)
            self.assertEqual(Path(manifest["sourceHtmlPath"]), source)
            self.assertEqual(manifest["sourceHtmlSha256"], _sha256(source))
            self.assertEqual(Path(manifest["sourceBriefPath"]), brief)
            self.assertEqual(manifest["sourceBriefSha256"], _sha256(brief))
            self.assertEqual(Path(manifest["outputPdfPath"]), output)
            self.assertEqual(manifest["outputPdfSha256"], _sha256(output))
            self.assertEqual(Path(manifest["rawPdf"]["path"]), raw_pdf_path)
            self.assertEqual(manifest["rawPdf"]["sha256"], _sha256(raw_pdf_path))

            snapshot = manifest["renderSnapshot"]
            snapshot_lines = "".join(
                f"{entry['relativePath']}\0{entry['bytes']}\0{entry['sha256']}\n"
                for entry in snapshot["files"]
            )
            self.assertEqual(snapshot["snapshotSha256"], _sha256_text(snapshot_lines))
            self.assertEqual(
                [entry["relativePath"] for entry in snapshot["files"]],
                ["assets/logo.svg", "source.html"],
            )

            normalization = manifest["listTagNormalization"]
            result_json = json.dumps(
                normalization["result"],
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            self.assertEqual(normalization["resultSha256"], _sha256_text(result_json))
            self.assertEqual(normalization["summary"]["status"], "passed")
            self.assertEqual(normalization["result"]["status"], "normalized")
            self.assertNotEqual(_sha256(raw_pdf_path), _sha256(output))
            self.assertEqual(normalization["invocation"]["inputPdfSha256"], _sha256(raw_pdf_path))
            self.assertEqual(normalization["invocation"]["outputPdfSha256"], _sha256(output))
            self.assertEqual(
                normalization["invocation"]["argumentVector"],
                [
                    str(NORMALIZER),
                    "--input",
                    str(raw_pdf_path),
                    "--output",
                    str(output),
                ],
            )

            expected_bindings = {
                "sourceHtmlSha256": _sha256(source),
                "sourceBriefSha256": _sha256(brief),
                "snapshotSha256": snapshot["snapshotSha256"],
                "rendererScriptSha256": _sha256(RENDERER),
                "rawPdfSha256": _sha256(raw_pdf_path),
                "normalizerScriptSha256": _sha256(NORMALIZER),
                "normalizerResultSha256": normalization["resultSha256"],
                "finalPdfSha256": _sha256(output),
            }
            self.assertEqual(manifest["trustChain"]["bindings"], expected_bindings)
            chain_order = [
                "sourceHtmlSha256",
                "sourceBriefSha256",
                "snapshotSha256",
                "rendererScriptSha256",
                "rawPdfSha256",
                "normalizerScriptSha256",
                "normalizerResultSha256",
                "finalPdfSha256",
            ]
            chain_text = "".join(f"{key}={expected_bindings[key]}\n" for key in chain_order)
            self.assertEqual(manifest["trustChain"]["chainSha256"], _sha256_text(chain_text))

            result_path = Path(completed.stdout.strip().splitlines()[-1])
            flow_result = json.loads(result_path.read_text(encoding="utf-8-sig"))
            self.assertEqual(flow_result["renderTrustChainStatus"], "passed")
            self.assertTrue(os.path.samefile(flow_result["sourceBriefPath"], brief))
            self.assertEqual(flow_result["sourceBriefSha256"], _sha256(brief))
            self.assertTrue(os.path.samefile(flow_result["rawPdfEvidencePath"], raw_pdf_path))


if __name__ == "__main__":
    unittest.main()
