from __future__ import annotations

from html.parser import HTMLParser

from taiwan_stock_analysis.models import FinancialTable


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []
            self._in_cell = True

    def handle_data(self, data: str) -> None:
        if self._in_cell and self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None and self._current_row is not None:
            text = "".join(self._current_cell).strip()
            self._current_row.append(text)
            self._current_cell = None
            self._in_cell = False
        elif tag == "tr" and self._current_row is not None and self._current_table is not None:
            if self._current_row:
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._current_table is not None:
            self.tables.append(self._current_table)
            self._current_table = None


def parse_number(raw: str) -> float | None:
    normalized = raw.strip().replace(",", "")
    if not normalized or normalized in {"-", "--", "N/A"}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def parse_financial_table(html: str, table_index: int = 6) -> tuple[FinancialTable, list[str]]:
    parser = _TableParser()
    parser.feed(html)

    if len(parser.tables) <= table_index:
        return {}, []

    rows = parser.tables[table_index]
    years: list[str] = []
    data: FinancialTable = {}

    for row in rows:
        if not years:
            years = [cell for cell in row[1:] if len(cell) == 4 and cell.isdigit()]
            if years:
                continue

        if len(row) < 2 or not row[0] or not years:
            continue

        field_name = row[0]
        values: dict[str, float | None] = {}
        value_columns = row[1:]
        for index, year in enumerate(years):
            value_index = index * 2
            if value_index < len(value_columns):
                values[year] = parse_number(value_columns[value_index])
        if values:
            data[field_name] = values

    return data, years
