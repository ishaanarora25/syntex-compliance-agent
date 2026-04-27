"""
Render the fixture JSONs into realistic-looking PDFs, one per document.

The backend originally ships with four hardcoded fixture scenarios (A, B, C, D).
Each fixture describes a set of formation / operating / trust documents as
page-by-page text. This script materialises those same scenarios as PDFs that
an analyst can drag-and-drop into the copilot to exercise the upload path
end-to-end.

Usage:
    python testing/scripts/generate_pdfs.py

Output:
    testing/scenario_a/*.pdf
    testing/scenario_b/*.pdf
    testing/scenario_c/*.pdf
    testing/scenario_d/*.pdf
    testing/manifest.json
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = REPO_ROOT / "backend" / "fixtures"
OUTPUT_DIR = REPO_ROOT / "testing"

SCENARIO_DIR_NAMES: Dict[str, str] = {
    "A": "scenario_a",
    "B": "scenario_b",
    "stress_c": "scenario_c",
    "stress_d": "scenario_d",
}


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            name="DocTitle",
            parent=base["Heading1"],
            fontName="Times-Bold",
            fontSize=14,
            leading=17,
            alignment=1,  # centered
            spaceAfter=12,
        ),
        "page_header": ParagraphStyle(
            name="PageHeader",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=9,
            textColor="#555555",
            alignment=2,  # right
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            name="Body",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=11,
            leading=15,
            spaceAfter=9,
            alignment=0,
        ),
        "heading": ParagraphStyle(
            name="BodyHeading",
            parent=base["Heading3"],
            fontName="Times-Bold",
            fontSize=11.5,
            leading=14,
            spaceBefore=6,
            spaceAfter=3,
        ),
        "footer": ParagraphStyle(
            name="Footer",
            parent=base["Normal"],
            fontName="Times-Italic",
            fontSize=8,
            textColor="#888888",
            alignment=1,
        ),
    }


_HEADING_PREFIXES = (
    "ARTICLE", "SECTION", "PART",
    "FIRST:", "SECOND:", "THIRD:", "FOURTH:", "FIFTH:",
    "CERTIFICATE", "OPERATING AGREEMENT", "LIMITED PARTNERSHIP",
    "THE ", "ADVERSE MEDIA", "HENDERSON", "MITCHELL", "CHEN",
    "SOURCE ", "HEADLINE:", "FULL TEXT:", "BSA RISK",
    "HANDELSREGISTERAUSZUG", "GESELLSCHAFTER", "GESCHÄFTSFÜHRER",
)


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    # All-caps short lines
    if stripped == stripped.upper() and len(stripped) < 110 and len(stripped.split()) < 12:
        return True
    if any(stripped.startswith(pref) for pref in _HEADING_PREFIXES):
        return True
    return False


def _escape(raw: str) -> str:
    """ReportLab Paragraph parses XML — escape & < >."""
    return (
        raw.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_page(text: str, styles: Dict[str, ParagraphStyle]) -> List[Any]:
    flowables: List[Any] = []

    paragraphs = re.split(r"\n\s*\n", text.strip())
    for idx, para in enumerate(paragraphs):
        lines = para.split("\n")
        for line in lines:
            if not line.strip():
                continue
            escaped = _escape(line).replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
            if _looks_like_heading(line) and idx == 0 and flowables == []:
                # Title-ish first line of the page
                flowables.append(Paragraph(escaped, styles["heading"]))
            elif _looks_like_heading(line):
                flowables.append(Paragraph(escaped, styles["heading"]))
            else:
                flowables.append(Paragraph(escaped, styles["body"]))
        flowables.append(Spacer(1, 0.08 * inch))
    return flowables


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _build_pdf(
    *,
    fixture_label: str,
    doc: Dict[str, Any],
    output_path: Path,
) -> None:
    styles = _styles()
    doc_builder = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.9 * inch,
        bottomMargin=0.9 * inch,
        title=doc["label"],
        author="Syntex Compliance Agent — Test Fixture",
    )

    flowables: List[Any] = []

    # Front matter
    flowables.append(Paragraph(_escape(doc["label"].upper()), styles["title"]))
    flowables.append(
        Paragraph(
            _escape(f"Document type: {doc['doc_type'].replace('_', ' ').title()}"),
            styles["page_header"],
        )
    )
    flowables.append(
        Paragraph(
            _escape(f"Test fixture — {fixture_label}"),
            styles["page_header"],
        )
    )
    flowables.append(Spacer(1, 0.15 * inch))

    total_pages = len(doc["pages"])
    for idx, page in enumerate(doc["pages"]):
        if idx > 0:
            flowables.append(PageBreak())
        flowables.append(
            Paragraph(
                _escape(f"Page {page['page']} of {total_pages}"),
                styles["page_header"],
            )
        )
        flowables.extend(_render_page(page["text"], styles))
        flowables.append(Spacer(1, 0.25 * inch))
        flowables.append(
            Paragraph(
                "— TEST FIXTURE — SYNTHETIC DOCUMENT — NOT A LEGAL INSTRUMENT —",
                styles["footer"],
            )
        )

    doc_builder.build(flowables)


def _fixture_short(fixture_id: str) -> str:
    return fixture_id.replace("fixture_", "").upper()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {"scenarios": []}

    for fixture_path in sorted(FIXTURES_DIR.glob("fixture_*.json")):
        fixture = json.loads(fixture_path.read_text())
        scenario_key = fixture.get("scenario", fixture["fixture_id"])
        scenario_dir_name = SCENARIO_DIR_NAMES.get(
            scenario_key, _slugify(scenario_key)
        )
        scenario_dir = OUTPUT_DIR / scenario_dir_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        scenario_entry: Dict[str, Any] = {
            "scenario": scenario_key,
            "label": fixture["label"],
            "description": fixture["description"],
            "dir": scenario_dir.relative_to(OUTPUT_DIR).as_posix(),
            "documents": [],
        }

        for doc in fixture["documents"]:
            out_name = f"{_slugify(doc['doc_id'])}.pdf"
            out_path = scenario_dir / out_name
            _build_pdf(
                fixture_label=f"{_fixture_short(fixture['fixture_id'])} — {fixture['label']}",
                doc=doc,
                output_path=out_path,
            )
            print(f"  wrote {out_path.relative_to(OUTPUT_DIR)}")
            scenario_entry["documents"].append(
                {
                    "doc_id": doc["doc_id"],
                    "label": doc["label"],
                    "doc_type": doc["doc_type"],
                    "file": out_path.name,
                    "pages": len(doc["pages"]),
                }
            )

        manifest["scenarios"].append(scenario_entry)
        print(f"Scenario {scenario_key}: {len(fixture['documents'])} PDFs -> {scenario_dir}")

    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written to {OUTPUT_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
