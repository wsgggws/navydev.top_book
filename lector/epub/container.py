"""``META-INF/container.xml`` → the path of the package document."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from lector.epub.errors import EpubStructureError


def local_name(tag: str) -> str:
    """Strip the XML namespace from ``tag``."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def find_all(element: ET.Element, name: str) -> list[ET.Element]:
    """Direct children of ``element`` whose local name is ``name``."""
    return [child for child in element if local_name(child.tag) == name]


def find_first(element: ET.Element, name: str) -> ET.Element | None:
    """First direct child of ``element`` whose local name is ``name``."""
    for child in find_all(element, name):
        return child
    return None


def read_container_path(container_xml: bytes) -> str:
    """Return the OPF path declared by ``META-INF/container.xml``.

    EPUB3 allows several root files; the first ``application/oebps-package+xml``
    one wins.
    """
    try:
        root = ET.fromstring(container_xml)
    except ET.ParseError as exc:
        raise EpubStructureError(
            "EPUB 结构不完整：container.xml 无法解析", {"reason": str(exc)}
        ) from exc
    # ``rootfile`` sits inside ``rootfiles``; scan the whole tree.
    rootfiles = [node for node in root.iter() if local_name(node.tag) == "rootfile"]
    if not rootfiles:
        raise EpubStructureError(
            "EPUB 结构不完整：缺少 OPF 文件", {"missing": "META-INF/container.xml"}
        )
    for node in rootfiles:
        media_type = node.get("media-type", "")
        full_path = node.get("full-path")
        if not full_path:
            continue
        if media_type in ("", "application/oebps-package+xml"):
            return full_path
    fallback = rootfiles[0].get("full-path")
    if not fallback:
        raise EpubStructureError("EPUB 结构不完整：缺少 OPF 文件")
    return fallback
