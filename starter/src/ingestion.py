"""Read and normalize source data."""
import json
import re
import unicodedata
from pathlib import Path
from pypdf import PdfReader
from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize Unicode and whitespace without discarding useful structure."""
    if not text:
        return ""
    # Unicode NFKC normalization
    text = unicodedata.normalize("NFKC", text)
    # Standardize line endings to Unix style
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace non-breaking spaces and tabs
    text = text.replace("\u00a0", " ").replace("\t", " ")
    # Replace multiple consecutive spaces within a line with a single space
    text = re.sub(r"[ ]{2,}", " ", text)
    # Collapse 3 or more consecutive newlines into 2 (preserves paragraph separation)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _find_manifest(start_path: Path) -> dict | None:
    """Helper to locate and load manifest.json if present."""
    candidates = [
        start_path.parent / "manifest.json",
        start_path.parent.parent / "manifest.json",
        start_path.parent.parent.parent / "data" / "manifest.json",
        Path("data/manifest.json"),
        Path("../data/manifest.json"),
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            try:
                with open(c, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return None


def load_pdf(path: Path, document_id: str, source: str, only_useful: bool = True) -> list[DocumentPage]:
    """Extract each physical page; keep its page number and source.

    Detect and record pages with no text. Respects manifest useful-page classification.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    reader = PdfReader(path)
    total_physical_pages = len(reader.pages)

    # Locate manifest if available
    manifest = _find_manifest(path)
    content_pages_map = {}
    excluded_pages_map = {}
    if manifest and "content_pages" in manifest:
        content_pages_map = {item["physical_page"]: item for item in manifest.get("content_pages", [])}
        excluded_pages_map = {item["physical_page"]: item.get("reason", "") for item in manifest.get("excluded_pages", [])}

    pages: list[DocumentPage] = []

    for physical_page in range(1, total_physical_pages + 1):
        # 1-based physical page index
        page_obj = reader.pages[physical_page - 1]
        try:
            raw_text = page_obj.extract_text() or ""
        except Exception as e:
            raw_text = ""

        norm_text = normalize_text(raw_text)

        # Check manifest classification
        if content_pages_map:
            if physical_page not in content_pages_map:
                if only_useful:
                    # Skip excluded non-content pages (cover, TOC, blank, etc.)
                    continue
                else:
                    # Keep as non-useful page
                    meta = {
                        "is_useful": False,
                        "exclusion_reason": excluded_pages_map.get(physical_page, "Excluded in manifest"),
                        "char_count": len(norm_text)
                    }
                    pages.append(
                        DocumentPage(
                            document_id=document_id,
                            source=source,
                            page=physical_page,
                            text=norm_text,
                            metadata=meta
                        )
                    )
                    continue

            # This is a verified useful content page
            page_info = content_pages_map[physical_page]
            page_meta = {
                "section": page_info.get("section", "default"),
                "printed_page": page_info.get("printed_page", str(physical_page)),
                "char_count": len(norm_text),
                "is_useful": True
            }
        else:
            # Fallback when no manifest is available
            if only_useful and not norm_text.strip():
                # Skip blank pages
                continue
            page_meta = {
                "section": "default",
                "char_count": len(norm_text),
                "is_useful": bool(norm_text.strip())
            }

        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=physical_page,
                text=norm_text,
                metadata=page_meta
            )
        )

    return pages
