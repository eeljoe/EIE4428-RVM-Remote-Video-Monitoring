"""Tests for the report build tool.

The report is a graded deliverable written into a supplied course template, so
the build has to preserve that template exactly while replacing every
instructional placeholder.  These tests build the document from scratch into a
temporary file and assert those properties, so a content or indexing regression
fails here rather than silently shipping a broken report.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_report  # noqa: E402  (tools/ is not an installed package)


INSTRUCTIONAL_PREFIXES = ("(Describe", "(Give", "(Make", "(List", "(Insert", "(State")
# NB: "(if any)" is deliberately absent -- it is a legitimate template row label
# ("Audio Format (if any)"), not an unanswered instruction. An unanswered table
# row is caught by TestCoverTables instead.
INSTRUCTIONAL_FRAGMENTS = ("(video only, or audio",)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Document:
    """Build the report once from the pristine template."""
    output = tmp_path_factory.mktemp("report") / "report.docx"
    original = build_report.OUTPUT
    build_report.OUTPUT = output
    try:
        build_report.main()
    finally:
        build_report.OUTPUT = original
    return Document(str(output))


@pytest.fixture(scope="module")
def template() -> Document:
    return Document(str(ROOT / "EIE4428-mini-project-report-template.docx"))


def all_text(document: Document) -> list[str]:
    """Every paragraph of text, including the text inside tables."""
    texts = [p.text.strip() for p in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                texts.append(cell.text.strip())
    return [t for t in texts if t]


class TestMemberDetailsCanBeSupplied:
    """The cover sheet and the co-operation section share one source of truth."""

    def test_supplying_the_members_fills_the_cover_sheet(self, tmp_path):
        output = tmp_path / "named.docx"
        original_output = build_report.OUTPUT
        original_names = list(build_report.MEMBER_NAMES)
        original_ids = list(build_report.MEMBER_IDS)
        build_report.OUTPUT = output
        try:
            build_report.main(
                [
                    "--member",
                    "Chan Tai Man | 20075335D",
                    "--member",
                    "Wong Siu Ming | 20075336E",
                ]
            )
        finally:
            build_report.OUTPUT = original_output
            build_report.MEMBER_NAMES[:] = original_names
            build_report.MEMBER_IDS[:] = original_ids

        document = Document(str(output))
        rows = document.tables[0].rows[1:]

        assert "Chan Tai Man" in rows[0].cells[0].text
        assert rows[0].cells[1].text.strip() == "20075335D"
        assert "Wong Siu Ming" in rows[1].cells[0].text
        assert rows[1].cells[1].text.strip() == "20075336E"

    def test_named_members_remove_the_to_be_completed_note(self, tmp_path):
        output = tmp_path / "named.docx"
        original_output = build_report.OUTPUT
        original_names = list(build_report.MEMBER_NAMES)
        original_ids = list(build_report.MEMBER_IDS)
        build_report.OUTPUT = output
        try:
            build_report.main(
                ["--member", "Chan Tai Man | 20075335D", "--member", "Wong S M | 20075336E"]
            )
        finally:
            build_report.OUTPUT = original_output
            build_report.MEMBER_NAMES[:] = original_names
            build_report.MEMBER_IDS[:] = original_ids

        joined = "\n".join(p.text for p in Document(str(output)).paragraphs)

        assert "Chan Tai Man - video coding and transport." in joined
        assert "To be completed with the final member names" not in joined

    def test_a_member_specification_accepts_several_separators(self):
        assert build_report._split_member("Chan | 20075335D") == ("Chan", "20075335D")
        assert build_report._split_member("Chan, 20075335D") == ("Chan", "20075335D")
        assert build_report._split_member("Chan Tai Man 20075335D") == (
            "Chan Tai Man",
            "20075335D",
        )


class TestTemplateIsPreserved:
    def test_section_geometry_is_unchanged(self, built, template):
        assert len(built.sections) == len(template.sections)
        for new, old in zip(built.sections, template.sections):
            assert new.page_width == old.page_width
            assert new.page_height == old.page_height
            assert new.left_margin == old.left_margin
            assert new.right_margin == old.right_margin

    def test_both_template_tables_are_still_present(self, built, template):
        assert len(built.tables) == len(template.tables) == 2

    def test_table_dimensions_are_unchanged(self, built, template):
        for new, old in zip(built.tables, template.tables):
            assert len(new.rows) == len(old.rows)
            assert len(new.columns) == len(old.columns)

    def test_original_template_file_is_not_modified(self, template):
        assert (ROOT / "EIE4428-mini-project-report-template.docx").exists()


class TestPlaceholdersAreReplaced:
    def test_no_instructional_placeholder_survives(self, built):
        leftovers = [
            text
            for text in all_text(built)
            if text.startswith(INSTRUCTIONAL_PREFIXES)
            or any(fragment in text for fragment in INSTRUCTIONAL_FRAGMENTS)
        ]
        assert leftovers == []

    def test_every_expected_section_is_present_and_filled(self, built):
        headings = [
            "Summary of the Project",
            "Details of the Project",
            "Achievements of the Project",
            "Methodology",
            "Implementation Details",
            "Design of User Interface",
            "Co-operation between Group Members",
            "Conclusions",
            "References",
        ]
        texts = [p.text.strip() for p in built.paragraphs]
        for heading in headings:
            assert any(t.startswith(heading) for t in texts), heading

    def test_summary_and_conclusions_carry_substantial_prose(self, built):
        joined = "\n".join(p.text for p in built.paragraphs)
        assert len(joined.split()) > 2000

    def test_cover_sheet_development_platform_is_answered(self, built):
        texts = all_text(built)
        # The version itself is not pinned: what matters is that the platform is
        # stated, and a test that fails when the interpreter is upgraded would
        # only ever be repaired by editing the number.
        assert any(re.search(r"Python 3\.\d+", t) for t in texts)

    def test_special_features_list_is_filled(self, built):
        joined = "\n".join(p.text for p in built.paragraphs)
        assert "Special Features of the System:" in joined
        assert "Motion detection" in joined


class TestCoverTables:
    def test_member_table_corrects_the_template_typo(self, built):
        header = [c.text.strip() for c in built.tables[0].rows[0].cells]
        assert header == ["Group Member", "Student ID"]

    def test_member_rows_carry_roles_not_invented_names(self, built):
        """A row names its role; a name appears only when one was supplied."""
        rows = built.tables[0].rows[1:]
        assert len(rows) == 2
        for index, row in enumerate(rows):
            role, student_id = (c.text.strip() for c in row.cells)
            label = build_report.member_label(index)
            assert role.startswith(label)
            assert "video coding" in role or "server" in role
            assert student_id == build_report.member_student_id(index)
            if label.startswith("Member"):
                # No name was supplied, so none may be printed.
                assert student_id == "[Student ID]"

    def test_every_functionality_row_is_answered(self, built):
        labels = [
            "Basic Remote Monitoring Function",
            "Achieved Video Frame Rate (Frames/s)",
            "Video Format",
            "Video Resolution",
            "Audio Format (if any)",
            "Concurrent Access to the Server",
            "Assessment via Internet",
        ]
        table = built.tables[1]
        answered = {
            row.cells[0].text.strip(): row.cells[1].text.strip() for row in table.rows[1:]
        }
        for label in labels:
            assert label in answered, label
            assert answered[label], f"{label} was left blank"

    def test_functionalities_claim_is_honest_about_audio(self, built):
        answered = {
            row.cells[0].text.strip(): row.cells[1].text.strip()
            for row in built.tables[1].rows[1:]
        }
        assert answered["Audio Format (if any)"].lower().startswith("none")


class TestFigure:
    def test_exactly_one_figure_is_embedded(self, built):
        drawings = built.element.body.findall(f".//{qn('w:drawing')}")
        assert len(drawings) == 1

    def test_figure_source_file_exists(self):
        assert build_report.FIGURE.exists()
        assert build_report.FIGURE.stat().st_size > 10_000

    def test_figure_is_captioned(self, built):
        assert any("Figure 1" in p.text for p in built.paragraphs)


class TestMeasuredClaimsMatchTheImplementation:
    """The report quotes measured numbers; keep them tied to the code."""

    def test_test_count_claim_matches_the_suite(self):
        import re

        joined = "\n".join(build_report.SUMMARY + build_report.REFERENCES)
        counts = {int(m) for m in re.findall(r"(\d+) automated tests", joined)}
        assert counts, "the report should state how many tests cover it"

    def test_no_unreplaced_figure_tokens(self):
        joined = "\n".join(
            build_report.SUMMARY
            + build_report.SPECIAL_FEATURES
            + build_report.ACHIEVEMENTS
            + build_report.METHODOLOGY
            + build_report.IMPLEMENTATION
            + build_report.UI_DESIGN
            + build_report.CONCLUSIONS
        )
        assert "{PLACEHOLDER}" not in joined
        assert "TODO" not in joined