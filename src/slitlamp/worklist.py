import csv
from datetime import date, datetime, time
from pathlib import Path

from .models import WorklistRow


def read_table(path: Path) -> tuple[list[str], list[dict]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            sample = stream.read(8192)
            stream.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            except csv.Error:
                dialect = csv.excel
            reader = csv.DictReader(stream, dialect=dialect)
            return list(reader.fieldnames or []), list(reader)
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Choose a CSV or .xlsx workbook. Save legacy .xls files as .xlsx first.")
    from openpyxl import load_workbook

    book = load_workbook(path, read_only=True, data_only=True)
    try:
        iterator = iter(book.active)
        headings = [str(c.value or "").strip() for c in next(iterator)]
        rows = []
        for cells in iterator:
            values = []
            for cell in cells:
                value = cell.value
                # Preserve an Excel MRN intentionally displayed with zero padding.
                if (
                    isinstance(value, (int, float))
                    and cell.number_format
                    and set(cell.number_format) == {"0"}
                ):
                    value = str(int(value)).zfill(len(cell.number_format))
                values.append(value)
            if any(v is not None for v in values):
                rows.append(dict(zip(headings, values)))
        return headings, rows
    finally:
        book.close()


def parse_date(value, order: str) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value or "").strip()
    formats = ["%Y-%m-%d", "%Y%m%d"]
    formats += {"DMY": ["%d/%m/%Y", "%d-%m-%Y"], "MDY": ["%m/%d/%Y", "%m-%d-%Y"], "ISO": []}[order]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Invalid date '{text}' for the selected {order} format.")


def map_rows(rows: list[dict], mapping: dict, order: str, clinic_day: str) -> list[WorklistRow]:
    result = []
    for number, source in enumerate(rows, 2):

        def value(key):
            return source.get(mapping.get(key, ""), "") or ""

        try:
            appointment = value("appointment")
            if isinstance(appointment, (time, datetime)):
                appointment = appointment.strftime("%H:%M")
            result.append(
                WorklistRow(
                    name=str(value("name")).strip(),
                    mrn=str(value("mrn")).strip(),
                    dob=parse_date(value("dob"), order),
                    day=parse_date(value("day"), order) if value("day") else clinic_day,
                    appointment=str(appointment),
                    order_id=str(value("order_id")),
                    issuer=str(value("issuer") or "CLINIC"),
                )
            )
        except ValueError as exc:
            raise ValueError(f"Row {number}: {exc}") from exc
    return result
