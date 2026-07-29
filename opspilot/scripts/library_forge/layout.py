"""Library Forge — shared BVTech document layout (fpdf2).

One layout engine renders every document kind with consistent branding:
cover band with the BVTech wordmark, document-control table, styled
sections, checklist boxes, form fill-lines, legal clause numbering,
signature blocks, and a compliance footer with the company's Texas
address on every page.
"""
from __future__ import annotations

from fpdf import FPDF

NAVY = (11, 34, 64)
ACCENT = (0, 122, 204)
GOLD = (196, 146, 59)
INK = (34, 40, 49)
SOFT = (100, 110, 122)
LINE = (208, 214, 222)
PAPER_TINT = (243, 246, 250)

COMPANY = "BVTech LLC"
ADDRESS = "1902 Kirby Rd, El Campo, TX 77437"
SITE = "bvtech.org"
EMAIL = "help@bvtech.org"
OWNER = "Jordan Polasek, Managing Partner"
EFFECTIVE = "July 28, 2026"
VERSION = "1.0"


def _latin(s: str) -> str:
    """Core PDF fonts are latin-1; swap the usual suspects."""
    return (s.replace("—", "-").replace("–", "-")
             .replace("‘", "'").replace("’", "'")
             .replace("“", '"').replace("”", '"')
             .replace("•", "-").replace("…", "...")
             .replace("§", "Sec.").replace("→", "->")
             .encode("latin-1", "replace").decode("latin-1"))


class BVTDoc(FPDF):
    def __init__(self, doc_id: str, title: str, classification: str,
                 counsel_note: bool = False):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.doc_id = doc_id
        self.doc_title = title
        self.classification = classification
        self.counsel_note = counsel_note
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 16, 18)
        self.alias_nb_pages()
        self._clause_n = 0

    # ---------------- chrome ----------------
    def header(self):
        if self.page_no() == 1:
            return                      # page 1 draws its own cover band
        self.set_font("helvetica", "B", 8)
        self.set_text_color(*SOFT)
        self.cell(0, 6, _latin(f"{COMPANY}  |  {self.doc_id}  -  {self.doc_title}"[:110]),
                  new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(18, self.get_y() + 1, self.w - 18, self.get_y() + 1)
        self.ln(4)

    def footer(self):
        self.set_y(-16)
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(18, self.get_y() - 1, self.w - 18, self.get_y() - 1)
        self.set_font("helvetica", "", 7)
        self.set_text_color(*SOFT)
        self.cell(0, 4, _latin(f"{COMPANY}  -  {ADDRESS}  -  {SITE}  -  {EMAIL}"),
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.cell(0, 4, _latin(f"{self.classification}  -  Page {self.page_no()}/{{nb}}"),
                  align="C")

    def cover(self, category_label: str, summary: str):
        self.add_page()
        # brand band
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 34, style="F")
        self.set_xy(18, 8)
        self.set_font("helvetica", "B", 22)
        self.set_text_color(255, 255, 255)
        self.cell(30, 10, "BV")
        self.set_text_color(*GOLD)
        self.set_x(31)
        self.cell(30, 10, "Tech")
        self.set_font("helvetica", "", 8.5)
        self.set_text_color(225, 232, 240)
        self.set_xy(18, 19)
        self.cell(0, 5, _latin("Managed IT  -  Cybersecurity  -  Backup & DR   |   "
                               "San Antonio - Houston - Austin - Sugar Land"))
        self.set_xy(-70, 8)
        self.set_font("helvetica", "B", 9)
        self.set_text_color(*GOLD)
        self.cell(52, 6, _latin(self.doc_id), align="R")
        # title
        self.set_xy(18, 44)
        self.set_font("helvetica", "", 9)
        self.set_text_color(*ACCENT)
        self.cell(0, 5, _latin(category_label.upper()), new_x="LMARGIN", new_y="NEXT")
        self.set_font("helvetica", "B", 19)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 8.5, _latin(self.doc_title), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_font("helvetica", "", 10)
        self.set_text_color(*SOFT)
        self.multi_cell(0, 5.4, _latin(summary), new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self._control_table()
        self.ln(6)

    def _control_table(self):
        rows = [("Document ID", self.doc_id), ("Version", VERSION),
                ("Effective date", EFFECTIVE), ("Document owner", OWNER),
                ("Classification", self.classification),
                ("Review cycle", "Annual, or upon material change")]
        if self.counsel_note:
            rows.append(("Counsel review",
                         "Recommended by licensed Texas counsel before first execution"))
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        for k, v in rows:
            self.set_fill_color(*PAPER_TINT)
            self.set_font("helvetica", "B", 8.5)
            self.set_text_color(*NAVY)
            self.cell(44, 6.4, _latin("  " + k), border=1, fill=True)
            self.set_font("helvetica", "", 8.5)
            self.set_text_color(*INK)
            self.cell(0, 6.4, _latin("  " + v), border=1, new_x="LMARGIN", new_y="NEXT")

    # ---------------- content primitives ----------------
    def h1(self, text: str):
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(2)
        self.set_font("helvetica", "B", 12.5)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 6.4, _latin(text), new_x="LMARGIN", new_y="NEXT")
        y = self.get_y() + 0.6
        self.set_draw_color(*GOLD)
        self.set_line_width(0.6)
        self.line(18, y, 44, y)
        self.ln(3.2)

    def para(self, text: str):
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.1, _latin(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1.6)

    def bullets(self, items: list[str]):
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*INK)
        for it in items:
            x = self.get_x()
            self.set_text_color(*ACCENT)
            self.cell(5, 5.1, "-")
            self.set_text_color(*INK)
            self.multi_cell(self.w - 36 - 5, 5.1, _latin(it), new_x="LMARGIN", new_y="NEXT")
            self.set_x(x)
        self.ln(1.6)

    def checks(self, items: list[str]):
        """Checklist rows with a drawn checkbox."""
        self.set_font("helvetica", "", 9.5)
        for it in items:
            if self.get_y() > self.h - 30:
                self.add_page()
            y = self.get_y()
            self.set_draw_color(*NAVY)
            self.set_line_width(0.35)
            self.rect(19, y + 0.8, 3.6, 3.6)
            self.set_xy(25.5, y)
            self.set_text_color(*INK)
            self.multi_cell(self.w - 36 - 7.5, 5.4, _latin(it), new_x="LMARGIN", new_y="NEXT")
            self.set_x(18)
        self.ln(1.6)

    def clause(self, heading: str, text: str):
        """Numbered legal clause (agreements)."""
        self._clause_n += 1
        if self.get_y() > self.h - 40:
            self.add_page()
        self.set_font("helvetica", "B", 10)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 5.6, _latin(f"{self._clause_n}. {heading}"), new_x="LMARGIN", new_y="NEXT")
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.1, _latin(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def fill_line(self, label: str, width: float = 90):
        if self.get_y() > self.h - 30:
            self.add_page()
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*INK)
        self.cell(52, 7, _latin(label))
        y = self.get_y() + 5.6
        x = self.get_x() + 2
        self.set_draw_color(*SOFT)
        self.set_line_width(0.25)
        self.line(x, y, min(x + width, self.w - 18), y)
        self.ln(7.5)

    def signature_block(self, party_a: str = COMPANY, party_b: str = "Client"):
        if self.get_y() > self.h - 75:
            self.add_page()
        self.ln(4)
        self.h1("Execution")
        self.para("IN WITNESS WHEREOF, the parties have executed this document "
                  "by their duly authorized representatives as of the dates below. "
                  "Electronic signatures are valid and enforceable under the Texas "
                  "Uniform Electronic Transactions Act (Tex. Bus. & Com. Code ch. 322) "
                  "and the federal E-SIGN Act.")
        for party in (party_a, party_b):
            self.set_font("helvetica", "B", 10)
            self.set_text_color(*NAVY)
            self.cell(0, 6, _latin(party), new_x="LMARGIN", new_y="NEXT")
            self.fill_line("Signature:")
            self.fill_line("Printed name:")
            self.fill_line("Title:")
            self.fill_line("Date:", width=50)
            self.ln(2)

    def table_grid(self, headers: list[str], widths: list[float], rows: list[list[str]]):
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.set_font("helvetica", "B", 8)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        for h, w in zip(headers, widths):
            self.cell(w, 6.4, _latin(" " + h), border=1, fill=True)
        self.ln()
        self.set_font("helvetica", "", 8)
        self.set_text_color(*INK)
        for r in rows:
            if self.get_y() > self.h - 30:
                self.add_page()
                self.set_font("helvetica", "B", 8)
                self.set_fill_color(*NAVY)
                self.set_text_color(255, 255, 255)
                for h, w in zip(headers, widths):
                    self.cell(w, 6.4, _latin(" " + h), border=1, fill=True)
                self.ln()
                self.set_font("helvetica", "", 8)
                self.set_text_color(*INK)
            hmax = 5.4
            self.multi_cell_row(r, widths, hmax)
        self.ln(2)

    def multi_cell_row(self, cells: list[str], widths: list[float], lh: float):
        x0, y0 = self.get_x(), self.get_y()
        heights = []
        for c, w in zip(cells, widths):
            lines = self.multi_cell(w, lh, _latin(str(c)), dry_run=True, output="LINES")
            heights.append(len(lines) * lh + 1.2)
        h = max(heights)
        x = x0
        for c, w in zip(cells, widths):
            self.rect(x, y0, w, h)
            self.set_xy(x + 0.8, y0 + 0.6)
            self.multi_cell(w - 1.6, lh, _latin(str(c)))
            x += w
        self.set_xy(x0, y0 + h)


def render(doc: dict, out_dir) -> str:
    """Render one doc spec -> PDF file. Returns the filename."""
    kind = doc.get("kind", "policy")
    pdf = BVTDoc(doc["id"], doc["title"], doc.get("classification",
                 "Internal - BVTech LLC Confidential"),
                 counsel_note=doc.get("counsel", False))
    pdf.cover(doc["category_label"], doc["summary"])
    for sec in doc["sections"]:
        kindsec = sec.get("kind", "para")
        if sec.get("h"):
            pdf.h1(sec["h"])
        body = sec.get("body")
        if kindsec == "para":
            for p in (body if isinstance(body, list) else [body]):
                pdf.para(p)
        elif kindsec == "bullets":
            pdf.bullets(body)
        elif kindsec == "checks":
            pdf.checks(body)
        elif kindsec == "clauses":
            for h, t in body:
                pdf.clause(h, t)
        elif kindsec == "fills":
            for label in body:
                pdf.fill_line(label)
        elif kindsec == "table":
            pdf.table_grid(sec["headers"], sec["widths"], body)
    if kind == "agreement":
        pdf.signature_block(party_b=doc.get("party_b", "Client"))
    fname = f"{doc['id']}_{doc['slug']}.pdf"
    pdf.output(str(out_dir / fname))
    return fname
