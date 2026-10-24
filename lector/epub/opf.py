"""The package document: metadata, manifest and spine."""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from urllib.parse import unquote

from lector.epub.container import find_all, find_first, local_name


@dataclass
class ManifestItem:
    """One entry of the manifest."""

    item_id: str
    href: str
    media_type: str
    properties: str = ""

    @property
    def is_navigation(self) -> bool:
        return "nav" in self.properties.split()


@dataclass
class OpfPackage:
    """Everything the parser needs from the OPF."""

    path: str
    title: str = ""
    creator: str = ""
    language: str = ""
    identifier: str = ""
    publisher: str = ""
    manifest: dict[str, ManifestItem] = field(default_factory=dict)
    spine: list[str] = field(default_factory=list)
    spine_toc: str | None = None
    cover_id: str | None = None

    @property
    def base_dir(self) -> str:
        """Directory the manifest hrefs are relative to."""
        return posixpath.dirname(self.path)

    def item_by_href(self, href: str) -> ManifestItem | None:
        """Find a manifest item by its href, ignoring any fragment."""
        target = unquote(href.split("#", 1)[0])
        for item in self.manifest.values():
            if unquote(item.href) == target:
                return item
        return None

    def chapter_index_of(self, item_id: str) -> int | None:
        """Index of a manifest item inside the spine."""
        try:
            return self.spine.index(item_id)
        except ValueError:
            return None

    def resolve(self, href: str) -> tuple[str, str | None]:
        """Resolve a href relative to the OPF directory.

        Returns the ZIP-internal path and the fragment, if any.
        """
        raw_path, _, fragment = href.partition("#")
        cleaned = unquote(raw_path)
        if cleaned.startswith("/"):
            resolved = cleaned.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(self.base_dir, cleaned))
        return resolved, (unquote(fragment) if fragment else None)


def parse_opf(data: bytes, path: str) -> OpfPackage:
    """Parse a package document into an :class:`OpfPackage`."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubStructureError(
            "EPUB 结构不完整：OPF 无法解析", {"path": path, "reason": str(exc)}
        ) from exc

    package = OpfPackage(path=path)
    metadata = find_first(root, "metadata")
    if metadata is not None:
        package.title = _metadata_text(metadata, "title")
        package.creator = _metadata_text(metadata, "creator")
        package.language = _metadata_text(metadata, "language")
        package.identifier = _metadata_text(metadata, "identifier")
        package.publisher = _metadata_text(metadata, "publisher")
        for meta in find_all(metadata, "meta"):
            if meta.get("name") == "cover" and meta.get("content"):
                package.cover_id = meta.get("content")

    manifest_el = find_first(root, "manifest")
    if manifest_el is not None:
        for node in find_all(manifest_el, "item"):
            item_id = node.get("id")
            href = node.get("href")
            if not item_id or not href:
                continue
            item = ManifestItem(
                item_id=item_id,
                href=href,
                media_type=node.get("media-type", ""),
                properties=node.get("properties", ""),
            )
            package.manifest[item_id] = item
            if "cover-image" in item.properties.split():
                package.cover_id = item_id

    spine_el = find_first(root, "spine")
    if spine_el is not None:
        package.spine_toc = spine_el.get("toc")
        for node in find_all(spine_el, "itemref"):
            idref = node.get("idref")
            if not idref or idref not in package.manifest:
                continue
            # "linear=no" marks supplementary content that is not part of the
            # reading order, so it gets no chapter id.
            if node.get("linear", "yes").strip().lower() == "no":
                continue
            package.spine.append(idref)

    if not package.spine:
        raise EpubStructureError("EPUB 结构不完整：spine 为空", {"path": path})
    return package


def _metadata_text(metadata: ET.Element, name: str) -> str:
    """First non-empty ``dc:<name>`` value in the metadata block."""
    for child in metadata:
        if local_name(child.tag) != name:
            continue
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""
