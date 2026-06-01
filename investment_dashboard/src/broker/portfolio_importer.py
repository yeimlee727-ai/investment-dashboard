from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import math
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pandas as pd

COLUMN_ALIASES = {
    "symbol": {"symbol", "ticker", "종목코드", "코드"},
    "name": {"name", "종목명", "종목"},
    "market": {"market", "시장", "시장구분"},
    "quantity": {"quantity", "qty", "수량", "보유수량"},
    "avg_price": {"avg_price", "average_price", "평균단가", "매입단가"},
    "current_price": {"current_price", "현재가"},
    "currency": {"currency", "통화"},
    "memo": {"memo", "메모"},
    "sector": {"sector", "섹터"},
    "account": {"account", "계좌"},
    "source": {"source", "출처"},
}

REQUIRED_COLUMNS = {"symbol", "market", "quantity", "avg_price"}

SAMPLE_PORTFOLIO_CSV = """symbol,name,market,quantity,avg_price,currency,memo
360750,TIGER 미국S&P500,KR,31,26244,KRW,reference 국내 ETF
390390,KODEX 미국반도체,KR,16,48531,KRW,reference 국내 ETF
453870,TIGER 인도니프티50,KR,61,12883,KRW,reference 국내 ETF
"""


@dataclass
class PortfolioImportValidation:
    preview: pd.DataFrame
    valid_rows: list[dict[str, object]]
    errors: pd.DataFrame
    warnings: pd.DataFrame

    @property
    def valid_count(self) -> int:
        return len(self.valid_rows)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def can_import(self) -> bool:
        return self.valid_count > 0


def read_portfolio_upload(file_name: str, content: bytes) -> pd.DataFrame:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".csv":
        return _read_csv(content)
    if suffix == ".xlsx":
        return _read_xlsx_first_sheet(content)
    if suffix == ".xls":
        raise ValueError(
            ".xls 파일은 현재 환경에서 지원하지 않습니다. .xlsx 또는 .csv로 저장해 업로드하세요."
        )
    raise ValueError(
        "지원하지 않는 파일 형식입니다. .csv 또는 .xlsx 파일을 업로드하세요."
    )


def validate_portfolio_frame(
    frame: pd.DataFrame,
    existing_keys: set[tuple[str, str]] | None = None,
) -> PortfolioImportValidation:
    existing_keys = existing_keys or set()
    if frame.empty:
        return PortfolioImportValidation(
            preview=pd.DataFrame(),
            valid_rows=[],
            errors=pd.DataFrame([_issue(None, "", "파일에 데이터가 없습니다.")]),
            warnings=pd.DataFrame(),
        )

    mapped = map_upload_columns(frame)
    missing = sorted(REQUIRED_COLUMNS - set(mapped.columns))
    if missing:
        return PortfolioImportValidation(
            preview=mapped,
            valid_rows=[],
            errors=pd.DataFrame(
                [_issue(None, "", f"필수 컬럼 누락: {', '.join(missing)}")]
            ),
            warnings=pd.DataFrame(),
        )

    rows: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    for index, raw in mapped.iterrows():
        row_number = int(index) + 2
        symbol = _normalize_symbol(raw.get("symbol"))
        market = normalize_market(raw.get("market"))
        quantity = _finite_number(raw.get("quantity"))
        avg_price = _finite_number(raw.get("avg_price"))
        current_price = _finite_number(raw.get("current_price"))
        row_issues: list[str] = []

        if not symbol:
            row_issues.append("종목코드가 비어 있습니다.")
        if market is None:
            row_issues.append("시장구분을 KR 또는 US로 해석할 수 없습니다.")
        if quantity is None or quantity <= 0:
            row_issues.append("수량은 0보다 큰 숫자여야 합니다.")
        if avg_price is None or avg_price <= 0:
            row_issues.append("평균단가는 0보다 큰 숫자여야 합니다.")
        if "current_price" in mapped.columns and raw.get("current_price") not in {
            None,
            "",
        }:
            if current_price is None or current_price <= 0:
                row_issues.append("현재가는 비어 있거나 0보다 큰 숫자여야 합니다.")

        key = (market or "", symbol)
        if symbol and market:
            if key in seen:
                row_issues.append(
                    "파일 안에 동일한 market+symbol 행이 중복되어 있습니다."
                )
            seen.add(key)

        if row_issues:
            for message in row_issues:
                errors.append(_issue(row_number, symbol, message))
            continue

        assert market is not None
        assert quantity is not None
        assert avg_price is not None
        currency = normalize_currency(raw.get("currency"), market)
        clean_row = {
            "symbol": symbol,
            "market": market,
            "quantity": int(quantity),
            "avg_price": float(avg_price),
            "currency": currency,
            "name": _clean_text(raw.get("name")),
            "memo": _clean_text(raw.get("memo")),
            "sector": _clean_text(raw.get("sector")),
            "current_price": current_price,
            "account": _clean_text(raw.get("account")),
            "source": _clean_text(raw.get("source")),
        }
        rows.append(clean_row)
        warnings.extend(_row_warnings(row_number, clean_row, existing_keys))

    preview = pd.DataFrame(rows)
    return PortfolioImportValidation(
        preview=preview,
        valid_rows=rows,
        errors=pd.DataFrame(errors),
        warnings=pd.DataFrame(warnings),
    )


def map_upload_columns(frame: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    used_targets = set()
    for column in frame.columns:
        normalized = _normalize_column_name(column)
        for target, aliases in COLUMN_ALIASES.items():
            if target in used_targets:
                continue
            if normalized in {_normalize_column_name(alias) for alias in aliases}:
                rename_map[column] = target
                used_targets.add(target)
                break
    return frame.rename(columns=rename_map)


def normalize_market(value: object) -> str | None:
    text = _clean_text(value).upper()
    if text in {"KR", "KRX", "KOSPI", "KOSDAQ", "국내", "한국"}:
        return "KR"
    if text in {"US", "USA", "NASDAQ", "NYSE", "AMEX", "미국", "해외"}:
        return "US"
    return None


def normalize_currency(value: object, market: str) -> str:
    text = _clean_text(value).upper()
    if text in {"KRW", "원", "원화"}:
        return "KRW"
    if text in {"USD", "달러", "$"}:
        return "USD"
    return "KRW" if market == "KR" else "USD"


def _read_csv(content: bytes) -> pd.DataFrame:
    for encoding in ["utf-8-sig", "utf-8", "cp949"]:
        try:
            return pd.read_csv(BytesIO(content), encoding=encoding, dtype=str)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(BytesIO(content), dtype=str)


def _read_xlsx_first_sheet(content: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(BytesIO(content)) as workbook:
        shared = _read_shared_strings(workbook)
        sheet_path = _first_sheet_path(workbook)
        xml = workbook.read(sheet_path)
    root = ET.fromstring(xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows = []
    max_col = 0
    for row in root.findall(".//x:sheetData/x:row", namespace):
        values: dict[int, object] = {}
        for cell in row.findall("x:c", namespace):
            index = _column_index(cell.attrib.get("r", "A1"))
            values[index] = _cell_value(cell, shared, namespace)
            max_col = max(max_col, index)
        rows.append([values.get(i, "") for i in range(max_col + 1)])
    if not rows:
        return pd.DataFrame()
    header = [str(value).strip() for value in rows[0]]
    return pd.DataFrame(rows[1:], columns=header)


def _read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings = []
    for item in root.findall("x:si", namespace):
        strings.append(
            "".join(node.text or "" for node in item.findall(".//x:t", namespace))
        )
    return strings


def _first_sheet_path(workbook: zipfile.ZipFile) -> str:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rels_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    main_ns = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    first_sheet = workbook_root.find(".//x:sheets/x:sheet", main_ns)
    if first_sheet is None:
        raise ValueError("xlsx 파일에서 시트를 찾을 수 없습니다.")
    rel_id = first_sheet.attrib[
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    ]
    for rel in rels_root.findall("r:Relationship", rel_ns):
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError("xlsx 파일의 첫 시트 경로를 찾을 수 없습니다.")


def _cell_value(
    cell: ET.Element,
    shared: list[str],
    namespace: dict[str, str],
) -> object:
    cell_type = cell.attrib.get("t")
    value = cell.find("x:v", namespace)
    if value is None or value.text is None:
        inline = cell.find(".//x:t", namespace)
        return inline.text if inline is not None and inline.text is not None else ""
    if cell_type == "s":
        index = int(value.text)
        return shared[index] if 0 <= index < len(shared) else ""
    if cell_type in {"str", "inlineStr"}:
        return value.text
    try:
        number = float(value.text)
    except ValueError:
        return value.text
    return int(number) if number.is_integer() else number


def _column_index(cell_reference: str) -> int:
    letters = "".join(char for char in cell_reference if char.isalpha()).upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return max(index - 1, 0)


def _row_warnings(
    row_number: int,
    row: dict[str, object],
    existing_keys: set[tuple[str, str]],
) -> list[dict[str, object]]:
    warnings = []
    symbol = str(row["symbol"])
    market = str(row["market"])
    avg_price = float(row["avg_price"])
    if market == "KR" and (avg_price < 100 or avg_price > 5_000_000):
        warnings.append(
            _issue(row_number, symbol, "KR 평균단가가 일반 범위를 벗어납니다.")
        )
    if market == "US" and avg_price > 1_000:
        warnings.append(
            _issue(
                row_number,
                symbol,
                "US 평균단가가 원화 단위처럼 큽니다. USD 기준인지 확인하세요.",
            )
        )
    if (market, symbol) in existing_keys:
        warnings.append(
            _issue(
                row_number,
                symbol,
                "기존 MockBroker 가상 포지션과 중복됩니다. 반영 방식에 따라 업데이트됩니다.",
            )
        )
    return warnings


def _finite_number(value: object) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _normalize_symbol(value: object) -> str:
    return _clean_text(value).upper()


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return ""
    return str(value).strip()


def _normalize_column_name(value: object) -> str:
    return _clean_text(value).lower().replace(" ", "").replace("_", "")


def _issue(row_number: int | None, symbol: str, message: str) -> dict[str, object]:
    return {"row": row_number, "symbol": symbol, "message": message}
