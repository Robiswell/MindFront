from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    BooleanObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
NORMALIZER_PATH = REPO_ROOT / "project-tools" / "normalize-pdf-list-tags.py"
SPEC = importlib.util.spec_from_file_location("pdf_list_tag_normalizer", NORMALIZER_PATH)
assert SPEC and SPEC.loader
normalizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = normalizer
SPEC.loader.exec_module(normalizer)


class PdfListTagNormalizerTests(unittest.TestCase):
    def test_normalizes_list_and_preserves_document_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.pdf"
            output = root / "normalized.pdf"
            self._write_fixture(source)
            before = PdfReader(source, strict=True)
            before_content = self._content_hashes(before)
            before_metadata = dict(before.metadata or {})

            result = normalizer.normalize_pdf(source, output)

            after = PdfReader(output, strict=True)
            li = self._find_role(after, "/LI")
            li_ref = li.indirect_reference
            children = self._raw_children(li)
            self.assertEqual([self._role(child) for child in children], ["/Lbl", "/LBody"])
            body = children[1].get_object()
            body_ref = body.indirect_reference
            body_children = self._raw_children(body)
            self.assertEqual([self._role(child) for child in body_children], ["/P"])
            paragraph = body_children[0].get_object()
            label = children[0].get_object()

            self.assertEqual(self._ref_key(label.raw_get("/P")), self._ref_key(li_ref))
            self.assertEqual(self._ref_key(body.raw_get("/P")), self._ref_key(li_ref))
            self.assertEqual(self._ref_key(paragraph.raw_get("/P")), self._ref_key(body_ref))
            self.assertEqual(self._ref_key(body.raw_get("/Pg")), self._ref_key(li.raw_get("/Pg")))
            self.assertEqual(len(after.pages), len(before.pages))
            self.assertEqual(self._content_hashes(after), before_content)
            self.assertEqual(dict(after.metadata or {}), before_metadata)

            struct_root = after.trailer["/Root"]["/StructTreeRoot"]
            parent_tree = struct_root["/ParentTree"]
            nums = parent_tree["/Nums"]
            self.assertEqual(int(nums[0]), 0)
            self.assertEqual(self._role(nums[1][0]), "/P")
            self.assertEqual(result["status"], "normalized")
            self.assertEqual(result["listItemsNormalized"], 1)
            self.assertTrue(all(result["preservationChecks"].values()))

    def test_second_run_is_idempotent_and_does_not_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.pdf"
            normalized = root / "normalized.pdf"
            self._write_fixture(source)
            normalizer.normalize_pdf(source, normalized)
            original_bytes = normalized.read_bytes()
            fixed_timestamp = 946684800
            os.utime(normalized, (fixed_timestamp, fixed_timestamp))
            original_mtime = normalized.stat().st_mtime_ns

            result = normalizer.normalize_pdf(normalized)

            self.assertEqual(result["status"], "unchanged")
            self.assertFalse(result["written"])
            self.assertFalse(result["pdfRewritten"])
            self.assertEqual(normalized.read_bytes(), original_bytes)
            self.assertEqual(normalized.stat().st_mtime_ns, original_mtime)

    def test_parent_tree_mapping_to_list_item_allows_only_expected_lbody_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.pdf"
            output = root / "normalized.pdf"
            self._write_fixture(source, parent_tree_points_to_list_item=True)

            result = normalizer.normalize_pdf(source, output)

            reader = PdfReader(output, strict=True)
            try:
                parent_tree = reader.trailer["/Root"]["/StructTreeRoot"]["/ParentTree"]
                mapped = parent_tree["/Nums"][1][0].get_object()
                self.assertEqual(str(mapped["/S"]), "/LI")
                self.assertEqual(result["status"], "normalized")
                self.assertTrue(result["preservationChecks"]["parentTree"])
            finally:
                reader.close()

    def test_malformed_list_fails_without_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "malformed.pdf"
            output = root / "must-not-exist.pdf"
            self._write_fixture(source, duplicate_label=True)
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            with self.assertRaises(normalizer.NormalizationError):
                normalizer.normalize_pdf(source, output)

            self.assertFalse(output.exists())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_hash)

    def test_cli_emits_machine_readable_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.pdf"
            output = Path(temporary) / "normalized.pdf"
            self._write_fixture(source)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = normalizer.main(
                    ["--input", str(source), "--output", str(output)]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["artifactType"], normalizer.ARTIFACT_TYPE)
            self.assertEqual(payload["status"], "normalized")
            self.assertTrue(payload["written"])

    @staticmethod
    def _write_fixture(
        path: Path,
        *,
        duplicate_label: bool = False,
        parent_tree_points_to_list_item: bool = False,
    ) -> None:
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        page_ref = page.indirect_reference
        assert page_ref is not None

        content = DecodedStreamObject()
        content.set_data(b"/P <</MCID 0>> BDC\nq\n1 0 0 1 0 0 cm\nQ\nEMC\n")
        page[NameObject("/Contents")] = writer._add_object(content)
        page[NameObject("/StructParents")] = NumberObject(0)

        struct_root = DictionaryObject()
        struct_root[NameObject("/Type")] = NameObject("/StructTreeRoot")
        struct_root_ref = writer._add_object(struct_root)

        list_element = DictionaryObject()
        list_element[NameObject("/Type")] = NameObject("/StructElem")
        list_element[NameObject("/S")] = NameObject("/L")
        list_element[NameObject("/P")] = struct_root_ref
        list_ref = writer._add_object(list_element)

        list_item = DictionaryObject()
        list_item[NameObject("/Type")] = NameObject("/StructElem")
        list_item[NameObject("/S")] = NameObject("/LI")
        list_item[NameObject("/P")] = list_ref
        list_item[NameObject("/Pg")] = page_ref
        list_item_ref = writer._add_object(list_item)

        label = DictionaryObject()
        label[NameObject("/Type")] = NameObject("/StructElem")
        label[NameObject("/S")] = NameObject("/Lbl")
        label[NameObject("/P")] = list_item_ref
        label_ref = writer._add_object(label)

        paragraph = DictionaryObject()
        paragraph[NameObject("/Type")] = NameObject("/StructElem")
        paragraph[NameObject("/S")] = NameObject("/P")
        paragraph[NameObject("/P")] = list_item_ref
        paragraph[NameObject("/Pg")] = page_ref
        paragraph[NameObject("/K")] = NumberObject(0)
        paragraph_ref = writer._add_object(paragraph)

        children = ArrayObject([label_ref])
        if duplicate_label:
            second_label = DictionaryObject()
            second_label[NameObject("/Type")] = NameObject("/StructElem")
            second_label[NameObject("/S")] = NameObject("/Lbl")
            second_label[NameObject("/P")] = list_item_ref
            children.append(writer._add_object(second_label))
        children.append(paragraph_ref)
        list_item[NameObject("/K")] = children
        list_element[NameObject("/K")] = list_item_ref
        struct_root[NameObject("/K")] = list_ref

        parent_tree = DictionaryObject()
        parent_tree[NameObject("/Nums")] = ArrayObject(
            [
                NumberObject(0),
                ArrayObject(
                    [list_item_ref if parent_tree_points_to_list_item else paragraph_ref]
                ),
            ]
        )
        struct_root[NameObject("/ParentTree")] = writer._add_object(parent_tree)
        struct_root[NameObject("/ParentTreeNextKey")] = NumberObject(1)

        writer.root_object[NameObject("/StructTreeRoot")] = struct_root_ref
        writer.root_object[NameObject("/MarkInfo")] = DictionaryObject(
            {NameObject("/Marked"): BooleanObject(True)}
        )
        writer.root_object[NameObject("/Lang")] = TextStringObject("en-US")
        writer.add_metadata({"/Title": "Tagged fixture", "/Author": "Codex"})
        writer.write(path)
        writer.close()

    @classmethod
    def _find_role(cls, reader: PdfReader, wanted: str) -> DictionaryObject:
        root = reader.trailer["/Root"]["/StructTreeRoot"]

        def visit(raw: object) -> DictionaryObject | None:
            resolved = raw.get_object() if hasattr(raw, "get_object") else raw
            if not isinstance(resolved, DictionaryObject):
                return None
            if str(resolved.get("/S")) == wanted:
                return resolved
            for child in cls._raw_children(resolved):
                found = visit(child)
                if found is not None:
                    return found
            return None

        for child in cls._raw_children(root):
            found = visit(child)
            if found is not None:
                return found
        raise AssertionError(f"Role {wanted} was not found.")

    @staticmethod
    def _raw_children(structure: DictionaryObject) -> list[object]:
        if "/K" not in structure:
            return []
        raw = structure.raw_get("/K")
        resolved = raw.get_object() if hasattr(raw, "get_object") else raw
        return list(resolved) if isinstance(resolved, ArrayObject) else [raw]

    @staticmethod
    def _role(raw: object) -> str | None:
        resolved = raw.get_object() if hasattr(raw, "get_object") else raw
        return str(resolved.get("/S")) if isinstance(resolved, DictionaryObject) and "/S" in resolved else None

    @staticmethod
    def _ref_key(reference: object) -> tuple[int, int]:
        return (reference.idnum, reference.generation)

    @staticmethod
    def _content_hashes(reader: PdfReader) -> list[str]:
        hashes: list[str] = []
        for page in reader.pages:
            contents = page.get_contents()
            data = b"" if contents is None else contents.get_data()
            hashes.append(hashlib.sha256(data).hexdigest())
        return hashes


if __name__ == "__main__":
    unittest.main()
