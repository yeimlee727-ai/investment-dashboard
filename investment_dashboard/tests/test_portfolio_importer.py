from __future__ import annotations

from io import BytesIO
import zipfile

import pandas as pd

from src.broker.portfolio_importer import (
    map_upload_columns,
    normalize_currency,
    normalize_market,
    read_portfolio_upload,
    validate_portfolio_frame,
)


def test_korean_columns_are_mapped() -> None:
    frame = pd.DataFrame(
        [{"종목코드": "005930", "시장": "국내", "수량": 10, "평균단가": 70000}]
    )

    mapped = map_upload_columns(frame)

    assert {"symbol", "market", "quantity", "avg_price"}.issubset(mapped.columns)


def test_english_columns_are_mapped() -> None:
    frame = pd.DataFrame(
        [{"ticker": "GRAB", "market": "US", "qty": 30, "average_price": 3.56}]
    )

    mapped = map_upload_columns(frame)

    assert mapped.iloc[0]["symbol"] == "GRAB"
    assert "quantity" in mapped.columns
    assert "avg_price" in mapped.columns


def test_market_and_currency_normalization() -> None:
    assert normalize_market("한국") == "KR"
    assert normalize_market("NASDAQ") == "US"
    assert normalize_market("UNKNOWN") is None
    assert normalize_currency("", "KR") == "KRW"
    assert normalize_currency("", "US") == "USD"
    assert normalize_currency("달러", "US") == "USD"


def test_valid_rows_are_normalized() -> None:
    frame = pd.DataFrame(
        [
            {
                "종목코드": "grab",
                "시장": "미국",
                "수량": "30",
                "평균단가": "3.56",
                "종목명": "Grab Holdings",
            }
        ]
    )

    result = validate_portfolio_frame(frame)

    assert result.error_count == 0
    assert result.valid_count == 1
    row = result.valid_rows[0]
    assert row["symbol"] == "GRAB"
    assert row["market"] == "US"
    assert row["currency"] == "USD"
    assert row["quantity"] == 30
    assert row["avg_price"] == 3.56


def test_missing_or_invalid_required_values_are_errors() -> None:
    frame = pd.DataFrame(
        [
            {"symbol": "", "market": "KR", "quantity": 1, "avg_price": 1000},
            {"symbol": "A", "market": "JP", "quantity": 1, "avg_price": 1000},
            {"symbol": "B", "market": "KR", "quantity": 0, "avg_price": 1000},
            {"symbol": "C", "market": "KR", "quantity": 1, "avg_price": -1},
        ]
    )

    result = validate_portfolio_frame(frame)

    assert result.valid_count == 0
    assert result.error_count == 4


def test_nan_or_inf_values_are_errors() -> None:
    frame = pd.DataFrame(
        [
            {"symbol": "A", "market": "KR", "quantity": float("nan"), "avg_price": 1},
            {"symbol": "B", "market": "KR", "quantity": 1, "avg_price": float("inf")},
        ]
    )

    result = validate_portfolio_frame(frame)

    assert result.valid_count == 0
    assert result.error_count == 2


def test_file_duplicate_is_error_and_existing_duplicate_is_warning() -> None:
    frame = pd.DataFrame(
        [
            {"symbol": "GRAB", "market": "US", "quantity": 30, "avg_price": 3.56},
            {"symbol": "GRAB", "market": "US", "quantity": 20, "avg_price": 4.00},
            {"symbol": "005930", "market": "KR", "quantity": 1, "avg_price": 70000},
        ]
    )

    result = validate_portfolio_frame(frame, existing_keys={("KR", "005930")})

    assert result.valid_count == 2
    assert result.error_count == 1
    assert "중복" in result.errors.iloc[0]["message"]
    assert result.warning_count == 1
    assert "기존" in result.warnings.iloc[0]["message"]


def test_us_price_that_looks_like_krw_is_warning() -> None:
    frame = pd.DataFrame(
        [{"symbol": "GRAB", "market": "US", "quantity": 30, "avg_price": 35000}]
    )

    result = validate_portfolio_frame(frame)

    assert result.valid_count == 1
    assert result.warning_count == 1
    assert "USD" in result.warnings.iloc[0]["message"]


def test_warning_rows_remain_importable_after_confirmation() -> None:
    frame = pd.DataFrame(
        [{"symbol": "GRAB", "market": "US", "quantity": 30, "avg_price": 35000}]
    )

    result = validate_portfolio_frame(frame)

    assert result.warning_count == 1
    assert result.error_count == 0
    assert result.can_import is True
    assert result.valid_rows[0]["symbol"] == "GRAB"


def test_error_rows_are_not_in_valid_rows() -> None:
    frame = pd.DataFrame(
        [
            {"symbol": "A", "market": "KR", "quantity": -1, "avg_price": 1000},
            {"symbol": "B", "market": "KR", "quantity": 2, "avg_price": 2000},
        ]
    )

    result = validate_portfolio_frame(frame)

    assert [row["symbol"] for row in result.valid_rows] == ["B"]


def test_read_csv_upload() -> None:
    content = "종목코드,시장,수량,평균단가\n005930,KR,1,70000\n".encode("utf-8-sig")

    frame = read_portfolio_upload("positions.csv", content)

    assert frame.iloc[0]["종목코드"] == "005930"


def test_read_xlsx_upload_without_extra_dependency() -> None:
    frame = read_portfolio_upload("positions.xlsx", _minimal_xlsx_bytes())
    result = validate_portfolio_frame(frame)

    assert frame.iloc[0]["symbol"] == "GRAB"
    assert result.valid_rows[0]["avg_price"] == 3.56


def test_unsupported_file_extension_is_error() -> None:
    try:
        read_portfolio_upload("positions.txt", b"")
    except ValueError as exc:
        assert "지원하지" in str(exc)
    else:
        raise AssertionError("unsupported extension should fail")


def _minimal_xlsx_bytes() -> bytes:
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        "xl/sharedStrings.xml": """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="8" uniqueCount="8">
<si><t>symbol</t></si><si><t>market</t></si><si><t>quantity</t></si><si><t>avg_price</t></si>
<si><t>GRAB</t></si><si><t>US</t></si><si><t>30</t></si><si><t>3.56</t></si>
</sst>""",
        "xl/worksheets/sheet1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c></row>
<row r="2"><c r="A2" t="s"><v>4</v></c><c r="B2" t="s"><v>5</v></c><c r="C2" t="s"><v>6</v></c><c r="D2" t="s"><v>7</v></c></row>
</sheetData>
</worksheet>""",
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()
