"""v1.64 Runtime BVTech PDF chrome — shared by client-facing report renderers.

The Library Forge (scripts/library_forge/layout.py) renders the static document
suite at build time. This is its lean runtime sibling: the same brand cover band,
compliance footer with the Texas address on every page, and a small set of
content primitives, packaged inside the app so live endpoints can stream a
client-ready PDF on demand (vCISO scorecard, QBR, proposals).

No document is written to disk — render into a bytes buffer and stream it.
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
GOOD = (33, 138, 90)
WARN = (200, 138, 30)
BAD = (192, 57, 43)

COMPANY = "BVTech LLC"
ADDRESS = "1902 Kirby Rd, El Campo, TX 77437"
SITE = "bvtech.org"
EMAIL = "help@bvtech.org"


def latin(s: str) -> str:
    """Core PDF fonts are latin-1; swap the usual unicode suspects."""
    return (str(s).replace("—", "-").replace("–", "-")
            .replace("‘", "'").replace("’", "'")
            .replace("“", '"').replace("”", '"')
            .replace("•", "-").replace("…", "...")
            .replace("§", "Sec.").replace("→", "->").replace("™", "")
            .encode("latin-1", "replace").decode("latin-1"))


class BrandedPDF(FPDF):
    """BVTech-branded page chrome. Subclass or use directly with the primitives."""

    def __init__(self, doc_id: str, title: str,
                 classification: str = "Confidential - Prepared for Client"):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.doc_id = doc_id
        self.doc_title = title
        self.classification = classification
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 16, 18)
        self.alias_nb_pages()

    # ---------------- chrome ----------------
    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("helvetica", "B", 8)
        self.set_text_color(*SOFT)
        self.cell(0, 6, latin(f"{COMPANY}  |  {self.doc_title}"[:110]),
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
        self.cell(0, 4, latin(f"{COMPANY}  -  {ADDRESS}  -  {SITE}  -  {EMAIL}"),
                  new_x="LMARGIN", new_y="NEXT", align="C")
        self.cell(0, 4, latin(f"{self.classification}  -  Page {self.page_no()}/{{nb}}"),
                  align="C")

    def brand_band(self, tagline: str = "Managed IT  -  Cybersecurity  -  Backup & DR"):
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
        self.cell(0, 5, latin(tagline + "   |   San Antonio - Houston - Austin - Sugar Land"))
        self.set_xy(-70, 8)
        self.set_font("helvetica", "B", 9)
        self.set_text_color(*GOLD)
        self.cell(52, 6, latin(self.doc_id), align="R")

    # ---------------- content primitives ----------------
    def h1(self, text: str):
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(2)
        self.set_font("helvetica", "B", 12.5)
        self.set_text_color(*NAVY)
        self.multi_cell(0, 6.4, latin(text), new_x="LMARGIN", new_y="NEXT")
        y = self.get_y() + 0.6
        self.set_draw_color(*GOLD)
        self.set_line_width(0.6)
        self.line(18, y, 44, y)
        self.ln(3.2)

    def para(self, text: str):
        self.set_font("helvetica", "", 9.5)
        self.set_text_color(*INK)
        self.multi_cell(0, 5.1, latin(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1.6)

    def bullets(self, items: list[str]):
        self.set_font("helvetica", "", 9.5)
        for it in items:
            x = self.get_x()
            self.set_text_color(*ACCENT)
            self.cell(5, 5.1, "-")
            self.set_text_color(*INK)
            self.multi_cell(self.w - 36 - 5, 5.1, latin(it), new_x="LMARGIN", new_y="NEXT")
            self.set_x(x)
        self.ln(1.6)

    def table_grid(self, headers: list[str], widths: list[float], rows: list[list[str]]):
        def _head():
            self.set_font("helvetica", "B", 8)
            self.set_fill_color(*NAVY)
            self.set_text_color(255, 255, 255)
            for h, w in zip(headers, widths):
                self.cell(w, 6.4, latin(" " + h), border=1, fill=True)
            self.ln()
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        _head()
        self.set_font("helvetica", "", 8)
        self.set_text_color(*INK)
        for r in rows:
            if self.get_y() > self.h - 30:
                self.add_page()
                _head()
                self.set_font("helvetica", "", 8)
                self.set_text_color(*INK)
            self._row(r, widths, 4.6)
        self.ln(2)

    def _row(self, cells: list[str], widths: list[float], lh: float):
        x0, y0 = self.get_x(), self.get_y()
        heights = []
        for c, w in zip(cells, widths):
            lines = self.multi_cell(w, lh, latin(str(c)), dry_run=True, output="LINES")
            heights.append(len(lines) * lh + 1.6)
        h = max(heights)
        x = x0
        for c, w in zip(cells, widths):
            self.rect(x, y0, w, h)
            self.set_xy(x + 1.0, y0 + 0.8)
            self.multi_cell(w - 2.0, lh, latin(str(c)))
            x += w
        self.set_xy(x0, y0 + h)


def to_bytes(pdf: FPDF) -> bytes:
    """Render a finished PDF to bytes (fpdf2 returns bytearray)."""
    return bytes(pdf.output())
