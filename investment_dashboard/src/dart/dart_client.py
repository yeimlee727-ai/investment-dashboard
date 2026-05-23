from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import zipfile
import io
import xml.etree.ElementTree as ET

import pandas as pd
import requests

from src.config import settings

SAMPLE_DISCLOSURES = [
    {
        "corp_name": "삼성전자",
        "stock_code": "005930",
        "report_nm": "분기보고서 샘플",
        "rcept_dt": "20260520",
        "url": "",
    },
    {
        "corp_name": "NAVER",
        "stock_code": "035420",
        "report_nm": "단일판매ㆍ공급계약체결 샘플",
        "rcept_dt": "20260519",
        "url": "",
    },
    {
        "corp_name": "카카오",
        "stock_code": "035720",
        "report_nm": "감사보고서 제출 지연 및 계속기업 불확실성 샘플",
        "rcept_dt": "20260518",
        "url": "",
    },
]


def classify_disclosure(report_name: str) -> tuple[str, str]:
    name = report_name.replace(" ", "")
    danger_keywords = [
        "의견거절",
        "한정",
        "부적정",
        "계속기업불확실성",
        "상장폐지",
        "거래정지",
    ]
    if any(keyword in name for keyword in danger_keywords):
        if "감사" in name or "의견" in name:
            return "감사의견", "위험"
        return "기타", "위험"
    rules: list[tuple[list[str], str, str]] = [
        (["공급계약", "단일판매", "판매공급계약"], "공급계약", "긍정"),
        (["유상증자"], "유상증자", "주의"),
        (["전환사채", "CB", "신주인수권부사채", "BW"], "전환사채", "주의"),
        (["자기주식", "자사주"], "자기주식", "긍정"),
        (["최대주주변경", "최대주주 변경"], "최대주주변경", "주의"),
        (["소송", "분쟁", "청구"], "소송", "위험"),
        (["감사의견", "감사보고서"], "감사의견", "중립"),
        (
            [
                "잠정실적",
                "매출액",
                "영업이익",
                "분기보고서",
                "반기보고서",
                "사업보고서",
            ],
            "실적공시",
            "중립",
        ),
    ]
    for keywords, disclosure_type, sentiment in rules:
        if any(keyword in name for keyword in keywords):
            return disclosure_type, sentiment
    return "기타", "중립"


def enrich_disclosures(df: pd.DataFrame, data_source: str) -> pd.DataFrame:
    if df.empty:
        empty = pd.DataFrame(
            columns=[
                "corp_name",
                "stock_code",
                "report_nm",
                "rcept_dt",
                "url",
                "disclosure_type",
                "risk_tag",
                "data_source",
            ]
        )
        empty.attrs["data_source"] = data_source
        return empty
    enriched = df.copy()
    classifications = enriched["report_nm"].fillna("").map(classify_disclosure)
    enriched["disclosure_type"] = classifications.map(lambda item: item[0])
    enriched["risk_tag"] = classifications.map(lambda item: item[1])
    enriched["data_source"] = data_source
    return enriched


@dataclass
class DartClient:
    api_key: str | None = settings.dart_api_key
    base_url: str = "https://opendart.fss.or.kr/api"
    timeout: int = 10

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def search_disclosures(
        self,
        corp_code: str | None = None,
        begin: str | None = None,
        end: str | None = None,
        page_count: int = 20,
    ) -> pd.DataFrame:
        if not self.api_key:
            return enrich_disclosures(
                pd.DataFrame(SAMPLE_DISCLOSURES), "SAMPLE_NO_API_KEY"
            )
        begin = begin or (date.today() - timedelta(days=14)).strftime("%Y%m%d")
        end = end or date.today().strftime("%Y%m%d")
        params = {
            "crtfc_key": self.api_key,
            "bgn_de": begin,
            "end_de": end,
            "page_count": page_count,
        }
        if corp_code:
            params["corp_code"] = corp_code
        try:
            response = requests.get(
                f"{self.base_url}/list.json", params=params, timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") not in {"000", "013"}:
                raise RuntimeError(payload.get("message", "DART 조회 실패"))
            rows = payload.get("list", [])
            for row in rows:
                receipt = row.get("rcept_no", "")
                row["url"] = (
                    f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}"
                    if receipt
                    else ""
                )
            if rows:
                return enrich_disclosures(pd.DataFrame(rows), "DART_API")
            return enrich_disclosures(pd.DataFrame(), "DART_API_NO_DATA")
        except Exception:
            return enrich_disclosures(
                pd.DataFrame(SAMPLE_DISCLOSURES), "SAMPLE_FALLBACK"
            )

    def fetch_corp_codes(self) -> pd.DataFrame:
        if not self.api_key:
            return pd.DataFrame(
                [
                    {
                        "corp_code": "00126380",
                        "corp_name": "삼성전자",
                        "stock_code": "005930",
                    },
                    {
                        "corp_code": "00266961",
                        "corp_name": "NAVER",
                        "stock_code": "035420",
                    },
                ]
            )
        try:
            response = requests.get(
                f"{self.base_url}/corpCode.xml",
                params={"crtfc_key": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as zipped:
                xml_bytes = zipped.read(zipped.namelist()[0])
            root = ET.fromstring(xml_bytes)
            rows = []
            for item in root.findall("list"):
                rows.append(
                    {
                        "corp_code": item.findtext("corp_code", ""),
                        "corp_name": item.findtext("corp_name", ""),
                        "stock_code": item.findtext("stock_code", ""),
                    }
                )
            return pd.DataFrame(rows)
        except Exception:
            return pd.DataFrame()
