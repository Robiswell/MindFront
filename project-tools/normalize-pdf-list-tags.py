#!/usr/bin/env python3
"""Normalize tagged-PDF list items to the /LI -> [/Lbl] + /LBody shape."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import pypdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    IndirectObject,
    NameObject,
    NullObject,
    NumberObject,
)


ARTIFACT_TYPE = "pdf_list_tag_normalization_result"
_MISSING = object()


class NormalizationError(RuntimeError):
    """Raised when a PDF cannot be normalized without guessing."""


@dataclass
class _TreeScan:
    list_items: int = 0
    normalized_items: int = 0
    already_normalized_items: int = 0
    role_counts: Counter[str] = field(default_factory=Counter)
    pg_links: Counter[tuple[str, int]] = field(default_factory=Counter)
    added_body_pg_links: Counter[int] = field(default_factory=Counter)


def _require_pypdf_6() -> None:
    try:
        major = int(pypdf.__version__.split(".", 1)[0])
    except (AttributeError, ValueError) as exc:
        raise NormalizationError("Unable to determine the installed pypdf version.") from exc
    if major != 6:
        raise NormalizationError(
            f"This normalizer requires pypdf 6.x; found {pypdf.__version__}."
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _raw_get(
    dictionary: DictionaryObject,
    key: str,
    default: Any = _MISSING,
) -> Any:
    name = NameObject(key)
    if name not in dictionary:
        if default is _MISSING:
            raise NormalizationError(f"Required PDF key {key} is missing.")
        return default
    raw_get = getattr(dictionary, "raw_get", None)
    return raw_get(name) if raw_get is not None else dict.__getitem__(dictionary, name)


def _deref(value: Any) -> Any:
    seen: set[tuple[int, int]] = set()
    while isinstance(value, IndirectObject):
        key = (value.idnum, value.generation)
        if key in seen:
            raise NormalizationError("Indirect-object cycle encountered while reading the PDF.")
        seen.add(key)
        try:
            value = value.get_object()
        except Exception as exc:
            raise NormalizationError(
                f"Unable to resolve indirect object {key[0]} {key[1]}."
            ) from exc
    return value


def _indirect_reference(raw: Any, resolved: Any, context: str) -> IndirectObject:
    if isinstance(raw, IndirectObject):
        return raw
    reference = getattr(resolved, "indirect_reference", None)
    if isinstance(reference, IndirectObject):
        return reference
    raise NormalizationError(f"{context} must be an indirect structure element.")


def _reference_key(reference: IndirectObject) -> tuple[int, int]:
    return (reference.idnum, reference.generation)


def _same_reference(left: Any, right: Any) -> bool:
    left_ref = left if isinstance(left, IndirectObject) else getattr(_deref(left), "indirect_reference", None)
    right_ref = right if isinstance(right, IndirectObject) else getattr(_deref(right), "indirect_reference", None)
    if isinstance(left_ref, IndirectObject) and isinstance(right_ref, IndirectObject):
        return _reference_key(left_ref) == _reference_key(right_ref)
    return _deref(left) is _deref(right)


def _role(raw: Any) -> str | None:
    resolved = _deref(raw)
    if not isinstance(resolved, DictionaryObject):
        return None
    role = _raw_get(resolved, "/S", None)
    if role is None:
        return None
    role = _deref(role)
    if not isinstance(role, NameObject):
        raise NormalizationError("A structure element has a non-name /S role.")
    return str(role)


def _is_content_item(raw: Any) -> bool:
    resolved = _deref(raw)
    if isinstance(resolved, (NumberObject, int)):
        return True
    if not isinstance(resolved, DictionaryObject):
        return False
    item_type = _deref(_raw_get(resolved, "/Type", None))
    return item_type in (NameObject("/MCR"), NameObject("/OBJR")) or NameObject("/MCID") in resolved


def _kids(
    structure: DictionaryObject,
    *,
    context: str,
    required: bool = False,
) -> list[Any]:
    raw = _raw_get(structure, "/K", None)
    if raw is None or isinstance(_deref(raw), NullObject):
        if required:
            raise NormalizationError(f"{context} has no usable /K children.")
        return []
    resolved = _deref(raw)
    if isinstance(resolved, ArrayObject):
        if not resolved and required:
            raise NormalizationError(f"{context} has an empty /K array.")
        return list(resolved)
    return [raw]


def _require_parent(child_raw: Any, expected_parent: IndirectObject, context: str) -> None:
    child = _deref(child_raw)
    if not isinstance(child, DictionaryObject):
        raise NormalizationError(f"{context} is not a structure-element dictionary.")
    _indirect_reference(child_raw, child, context)
    parent = _raw_get(child, "/P", None)
    if parent is None or not _same_reference(parent, expected_parent):
        raise NormalizationError(f"{context} has a missing or inconsistent /P link.")


def _fingerprint(value: Any) -> Any:
    if isinstance(value, IndirectObject):
        return ["ref", value.idnum, value.generation]
    resolved = _deref(value)
    if isinstance(resolved, ArrayObject):
        return ["array", *(_fingerprint(item) for item in resolved)]
    if isinstance(resolved, DictionaryObject):
        return [
            "dict",
            *(
                [str(key), _fingerprint(raw)]
                for key, raw in sorted(resolved.items(), key=lambda item: str(item[0]))
                if str(key) != "/Length"
            ),
        ]
    if isinstance(resolved, bytes):
        return ["bytes", hashlib.sha256(resolved).hexdigest()]
    return [type(resolved).__name__, str(resolved)]


def _parent_tree_snapshot(structure_root: DictionaryObject) -> Any:
    parent_tree_raw = _raw_get(structure_root, "/ParentTree", None)
    parent_tree = _deref(parent_tree_raw)
    if not isinstance(parent_tree, DictionaryObject):
        raise NormalizationError("The tagged PDF has no valid /ParentTree.")

    active: set[tuple[int, int] | tuple[str, int]] = set()

    def child_signatures(raw: Any, seen: set[tuple[int, int]]) -> list[Any]:
        resolved = _deref(raw)
        children = list(resolved) if isinstance(resolved, ArrayObject) else [raw]
        signatures: list[Any] = []
        for child in children:
            signature = content_signature(child, seen)
            if (
                isinstance(signature, list)
                and len(signature) == 2
                and signature[0] == "transparent-lbody"
                and isinstance(signature[1], list)
            ):
                signatures.extend(signature[1])
            else:
                signatures.append(signature)
        return signatures

    def content_signature(raw: Any, seen: set[tuple[int, int]]) -> Any:
        if isinstance(raw, IndirectObject):
            identity = _reference_key(raw)
            if identity in seen:
                return ["cycle", *identity]
            seen = {*seen, identity}
        resolved = _deref(raw)
        if isinstance(resolved, ArrayObject):
            return ["array", *(content_signature(item, seen) for item in resolved)]
        if isinstance(resolved, (NumberObject, int)):
            return ["mcid", int(resolved)]
        if isinstance(resolved, NullObject):
            return ["null"]
        if isinstance(resolved, DictionaryObject):
            role = _role(resolved)
            if role is not None:
                kids = _raw_get(resolved, "/K", None)
                if role == "/LBody":
                    return [
                        "transparent-lbody",
                        [] if kids is None else child_signatures(kids, seen),
                    ]
                return [
                    "struct",
                    role,
                    None if kids is None else ["kids", *child_signatures(kids, seen)],
                ]
            item_type = _deref(_raw_get(resolved, "/Type", None))
            if item_type == NameObject("/MCR") or NameObject("/MCID") in resolved:
                mcid = _deref(_raw_get(resolved, "/MCID", None))
                return ["mcr", None if mcid is None else int(mcid)]
            if item_type == NameObject("/OBJR"):
                return ["objr"]
        return _fingerprint(resolved)

    def visit(node_raw: Any) -> Any:
        node = _deref(node_raw)
        if not isinstance(node, DictionaryObject):
            raise NormalizationError("A /ParentTree node is not a dictionary.")
        reference = (
            node_raw
            if isinstance(node_raw, IndirectObject)
            else getattr(node, "indirect_reference", None)
        )
        identity: tuple[int, int] | tuple[str, int]
        if isinstance(reference, IndirectObject):
            identity = _reference_key(reference)
        else:
            identity = ("direct", id(node))
        if identity in active:
            raise NormalizationError("A cycle exists in the /ParentTree.")
        active.add(identity)
        try:
            nums_raw = _raw_get(node, "/Nums", None)
            kids_raw = _raw_get(node, "/Kids", None)
            if nums_raw is not None and kids_raw is not None:
                raise NormalizationError("A /ParentTree node contains both /Nums and /Kids.")
            if nums_raw is not None:
                nums = _deref(nums_raw)
                if not isinstance(nums, ArrayObject) or len(nums) % 2:
                    raise NormalizationError("A /ParentTree /Nums array is malformed.")
                pairs = [
                    [
                        _fingerprint(nums[index]),
                        content_signature(nums[index + 1], set()),
                    ]
                    for index in range(0, len(nums), 2)
                ]
                payload: list[Any] = ["nums", *pairs]
            elif kids_raw is not None:
                kids = _deref(kids_raw)
                if not isinstance(kids, ArrayObject) or not kids:
                    raise NormalizationError("A /ParentTree /Kids array is malformed.")
                payload = ["kids", *(visit(kid) for kid in kids)]
            else:
                raise NormalizationError("A /ParentTree node has neither /Nums nor /Kids.")
            limits = _raw_get(node, "/Limits", None)
            if limits is not None:
                payload.append(["limits", _fingerprint(limits)])
            return payload
        finally:
            active.remove(identity)

    return visit(parent_tree_raw)


def _structure_root(reader_or_writer: Any) -> DictionaryObject:
    if isinstance(reader_or_writer, PdfReader):
        catalog = _deref(reader_or_writer.trailer["/Root"])
    else:
        catalog = reader_or_writer.root_object
    if not isinstance(catalog, DictionaryObject):
        raise NormalizationError("The PDF catalog is malformed.")
    root = _deref(_raw_get(catalog, "/StructTreeRoot", None))
    if not isinstance(root, DictionaryObject):
        raise NormalizationError("The PDF is not a tagged PDF with a /StructTreeRoot.")
    root_type = _deref(_raw_get(root, "/Type", None))
    if root_type not in (None, NameObject("/StructTreeRoot")):
        raise NormalizationError("The /StructTreeRoot has an invalid /Type.")
    return root


def _scan_structure(
    reader_or_writer: Any,
    *,
    mutate: bool,
) -> _TreeScan:
    structure_root = _structure_root(reader_or_writer)
    _parent_tree_snapshot(structure_root)
    result = _TreeScan()
    visited: set[tuple[int, int] | tuple[str, int]] = set()
    active: set[tuple[int, int] | tuple[str, int]] = set()
    page_indexes: dict[tuple[int, int], int] = {}
    for page_index, pdf_page in enumerate(reader_or_writer.pages):
        page_reference = getattr(pdf_page, "indirect_reference", None)
        if not isinstance(page_reference, IndirectObject):
            raise NormalizationError(f"Page {page_index} has no indirect reference.")
        page_indexes[_reference_key(page_reference)] = page_index

    def page_index_for(page_raw: Any, context: str) -> int:
        page = _deref(page_raw)
        page_reference = (
            page_raw
            if isinstance(page_raw, IndirectObject)
            else getattr(page, "indirect_reference", None)
        )
        if not isinstance(page_reference, IndirectObject):
            raise NormalizationError(f"{context} has a direct or invalid /Pg link.")
        page_index = page_indexes.get(_reference_key(page_reference))
        if page_index is None:
            raise NormalizationError(f"{context} points /Pg outside the document page tree.")
        return page_index

    def visit(raw: Any, path: str) -> None:
        element = _deref(raw)
        if not isinstance(element, DictionaryObject):
            if _is_content_item(raw):
                return
            raise NormalizationError(f"{path} contains an unsupported /K child.")
        role = _role(raw)
        if role is None:
            if _is_content_item(raw):
                return
            raise NormalizationError(f"{path} contains an untyped dictionary child.")
        reference = _indirect_reference(raw, element, path)
        identity: tuple[int, int] | tuple[str, int] = _reference_key(reference)
        if identity in active:
            raise NormalizationError(f"A structure-tree cycle reaches {path}.")
        if identity in visited:
            raise NormalizationError(f"A structure element is shared by multiple parents at {path}.")
        active.add(identity)
        visited.add(identity)
        result.role_counts[role] += 1

        page = _raw_get(element, "/Pg", None)
        element_page_index: int | None = None
        if page is not None:
            element_page_index = page_index_for(page, path)
            result.pg_links[(role, element_page_index)] += 1

        original_children = _kids(
            element,
            context=f"{path} ({role})",
            required=role == "/LI",
        )
        if role == "/LI":
            result.list_items += 1
            labels = [child for child in original_children if _role(child) == "/Lbl"]
            bodies = [child for child in original_children if _role(child) == "/LBody"]
            if len(labels) > 1:
                raise NormalizationError(f"{path} contains more than one /Lbl.")
            if labels and original_children[0] is not labels[0]:
                raise NormalizationError(f"{path} contains a /Lbl that is not its first child.")
            if len(bodies) > 1:
                raise NormalizationError(f"{path} contains more than one /LBody.")

            if labels:
                _require_parent(labels[0], reference, f"{path} /Lbl")

            if bodies:
                non_label_children = [
                    child for child in original_children if _role(child) != "/Lbl"
                ]
                if len(non_label_children) != 1 or non_label_children[0] is not bodies[0]:
                    raise NormalizationError(
                        f"{path} mixes an existing /LBody with other body children."
                    )
                _require_parent(bodies[0], reference, f"{path} /LBody")
                result.already_normalized_items += 1
            else:
                body_children = [
                    child for child in original_children if _role(child) != "/Lbl"
                ]
                if not body_children:
                    raise NormalizationError(f"{path} has no children to place in /LBody.")
                for child_index, child in enumerate(body_children):
                    if _is_content_item(child):
                        raise NormalizationError(
                            f"{path} child {child_index} is direct marked content; "
                            "normalizing it would require ambiguous /ParentTree remapping."
                        )
                    child_role = _role(child)
                    if child_role is None:
                        raise NormalizationError(
                            f"{path} child {child_index} is not a structure element."
                        )
                    _require_parent(
                        child,
                        reference,
                        f"{path} child {child_index} ({child_role})",
                    )

                result.normalized_items += 1
                if element_page_index is not None:
                    result.added_body_pg_links[element_page_index] += 1
                if mutate:
                    if not isinstance(reader_or_writer, PdfWriter):
                        raise NormalizationError("Internal error: mutation requires PdfWriter.")
                    body = DictionaryObject()
                    body[NameObject("/Type")] = NameObject("/StructElem")
                    body[NameObject("/S")] = NameObject("/LBody")
                    body[NameObject("/P")] = reference
                    if page is not None:
                        body[NameObject("/Pg")] = page
                    body[NameObject("/K")] = ArrayObject(body_children)
                    body_reference = reader_or_writer._add_object(body)
                    for child in body_children:
                        child_object = _deref(child)
                        child_object[NameObject("/P")] = body_reference
                    replacement = ArrayObject()
                    if labels:
                        replacement.append(labels[0])
                    replacement.append(body_reference)
                    element[NameObject("/K")] = replacement

        for child_index, child in enumerate(original_children):
            if _role(child) is not None:
                visit(child, f"{path}/K[{child_index}]")
            elif not _is_content_item(child):
                raise NormalizationError(f"{path}/K[{child_index}] is malformed.")
        active.remove(identity)

    for index, child in enumerate(
        _kids(structure_root, context="/StructTreeRoot", required=False)
    ):
        if _role(child) is not None:
            visit(child, f"/StructTreeRoot/K[{index}]")
        elif not _is_content_item(child):
            raise NormalizationError(
                f"/StructTreeRoot/K[{index}] is not a structure element."
            )
    return result


def _page_content_hashes(reader: PdfReader) -> list[str]:
    hashes: list[str] = []
    for page in reader.pages:
        contents = page.get_contents()
        data = b"" if contents is None else contents.get_data()
        hashes.append(hashlib.sha256(data).hexdigest())
    return hashes


def _metadata_snapshot(reader: PdfReader) -> Any:
    info = reader.metadata
    info_snapshot = (
        []
        if info is None
        else sorted((str(key), type(value).__name__, str(value)) for key, value in info.items())
    )
    catalog = _deref(reader.trailer["/Root"])
    metadata_raw = _raw_get(catalog, "/Metadata", None)
    if metadata_raw is None:
        xmp_hash = None
    else:
        metadata_stream = _deref(metadata_raw)
        if not hasattr(metadata_stream, "get_data"):
            raise NormalizationError("The catalog /Metadata entry is not a stream.")
        xmp_hash = hashlib.sha256(metadata_stream.get_data()).hexdigest()
    return {"documentInfo": info_snapshot, "xmpSha256": xmp_hash}


def _preservation_snapshot(reader: PdfReader) -> dict[str, Any]:
    structure_root = _structure_root(reader)
    scan = _scan_structure(reader, mutate=False)
    return {
        "pageCount": len(reader.pages),
        "pageContentSha256": _page_content_hashes(reader),
        "metadata": _metadata_snapshot(reader),
        "parentTree": _parent_tree_snapshot(structure_root),
        "roleCounts": dict(scan.role_counts),
        "pgLinks": dict(scan.pg_links),
    }


def _close_pdf(instance: Any) -> None:
    close = getattr(instance, "close", None)
    if callable(close):
        close()
        return
    stream = getattr(instance, "stream", None)
    if stream is not None and hasattr(stream, "close"):
        stream.close()


def normalize_pdf(input_path: str | Path, output_path: str | Path | None = None) -> dict[str, Any]:
    """Normalize list tags and return a machine-readable result dictionary."""

    _require_pypdf_6()
    source = Path(input_path).expanduser().resolve()
    target = source if output_path is None else Path(output_path).expanduser().resolve()
    if not source.is_file():
        raise NormalizationError(f"Input PDF does not exist: {source}")
    if target.parent != source.parent and not target.parent.is_dir():
        raise NormalizationError(f"Output directory does not exist: {target.parent}")

    before_hash = _sha256(source)
    reader = PdfReader(str(source), strict=True)
    try:
        pre_scan = _scan_structure(reader, mutate=False)
        pre_state = _preservation_snapshot(reader)
        if pre_scan.normalized_items == 0:
            return {
                "artifactType": ARTIFACT_TYPE,
                "status": "unchanged",
                "input": str(source),
                "output": str(target),
                "written": False,
                "pdfRewritten": False,
                "listItemsScanned": pre_scan.list_items,
                "listItemsNormalized": 0,
                "alreadyNormalizedItems": pre_scan.already_normalized_items,
                "lBodyCreated": 0,
                "pageCount": len(reader.pages),
                "inputSha256": before_hash,
                "outputSha256": before_hash if target == source else None,
            }

        writer = PdfWriter()
        writer.clone_document_from_reader(reader)
        mutated_scan = _scan_structure(writer, mutate=True)
        if mutated_scan.normalized_items != pre_scan.normalized_items:
            raise NormalizationError("The cloned structure tree differs from the validated input.")

        temporary_handle = tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        )
        temporary = Path(temporary_handle.name)
        temporary_handle.close()
        try:
            writer.write(str(temporary))
            _close_pdf(writer)

            output_reader = PdfReader(str(temporary), strict=True)
            try:
                post_scan = _scan_structure(output_reader, mutate=False)
                post_state = _preservation_snapshot(output_reader)
                if post_scan.list_items != pre_scan.list_items:
                    raise NormalizationError("List-item count changed during normalization.")
                if post_scan.normalized_items != 0:
                    raise NormalizationError("The output still contains unnormalized /LI elements.")
                expected_roles = Counter(pre_state["roleCounts"])
                expected_roles["/LBody"] += pre_scan.normalized_items
                if Counter(post_state["roleCounts"]) != expected_roles:
                    raise NormalizationError("Unexpected structure elements changed during normalization.")
                expected_pg_links = Counter(pre_state["pgLinks"])
                for page_index, count in pre_scan.added_body_pg_links.items():
                    expected_pg_links[("/LBody", page_index)] += count
                if Counter(post_state["pgLinks"]) != expected_pg_links:
                    raise NormalizationError("An existing structure-element /Pg link changed.")
                for key in ("pageCount", "pageContentSha256", "metadata", "parentTree"):
                    if post_state[key] != pre_state[key]:
                        raise NormalizationError(f"PDF preservation check failed for {key}.")
            finally:
                _close_pdf(output_reader)
                _close_pdf(reader)

            after_hash = _sha256(temporary)
            os.replace(temporary, target)
            return {
                "artifactType": ARTIFACT_TYPE,
                "status": "normalized",
                "input": str(source),
                "output": str(target),
                "written": True,
                "pdfRewritten": True,
                "listItemsScanned": pre_scan.list_items,
                "listItemsNormalized": pre_scan.normalized_items,
                "alreadyNormalizedItems": pre_scan.already_normalized_items,
                "lBodyCreated": pre_scan.normalized_items,
                "pageCount": pre_state["pageCount"],
                "inputSha256": before_hash,
                "outputSha256": after_hash,
                "preservationChecks": {
                    "pageCount": True,
                    "pageContent": True,
                    "metadata": True,
                    "parentTree": True,
                    "existingPgLinks": True,
                    "structureRoles": True,
                },
            }
        except Exception:
            _close_pdf(writer)
            temporary.unlink(missing_ok=True)
            raise
    finally:
        _close_pdf(reader)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normalize tagged-PDF /LI children into optional /Lbl plus one /LBody."
    )
    parser.add_argument("--input", required=True, help="Tagged source PDF.")
    parser.add_argument(
        "--output",
        help="Output PDF. Defaults to atomic in-place replacement when changes are needed.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = normalize_pdf(args.input, args.output)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        failure = {
            "artifactType": ARTIFACT_TYPE,
            "status": "failed",
            "input": str(Path(args.input).expanduser().resolve()),
            "output": (
                str(Path(args.output).expanduser().resolve())
                if args.output
                else str(Path(args.input).expanduser().resolve())
            ),
            "written": False,
            "errorType": type(exc).__name__,
            "error": str(exc),
        }
        print(json.dumps(failure, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
