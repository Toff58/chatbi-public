import html
import io
import zipfile
from numbers import Number
from typing import Any

import pandas as pd


def build_excel_bytes(df: pd.DataFrame) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types())
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("xl/workbook.xml", _xlsx_workbook())
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels())
        archive.writestr("xl/worksheets/sheet1.xml", _xlsx_sheet(df))
    return output.getvalue()

def _xlsx_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

def _xlsx_root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

def _xlsx_workbook() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="结果" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""

def _xlsx_workbook_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""

def _xlsx_sheet(df: pd.DataFrame) -> str:
    rows = [_xlsx_row(1, list(df.columns))]
    for row_number, (_, row) in enumerate(df.iterrows(), start=2):
        rows.append(_xlsx_row(row_number, [row[column] for column in df.columns]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData>"
        "</worksheet>"
    )

def _xlsx_row(row_number: int, values: list[Any]) -> str:
    cells = []
    for column_index, value in enumerate(values, start=1):
        cell_ref = f"{_excel_column_name(column_index)}{row_number}"
        cells.append(_xlsx_cell(cell_ref, value))
    return f'<row r="{row_number}">{"".join(cells)}</row>'

def _xlsx_cell(cell_ref: str, value: Any) -> str:
    if pd.isna(value):
        return f'<c r="{cell_ref}"/>'
    if isinstance(value, Number) and not isinstance(value, bool):
        return f'<c r="{cell_ref}" t="n"><v>{value}</v></c>'
    escaped = html.escape(str(value), quote=False)
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped}</t></is></c>'

def _excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name
