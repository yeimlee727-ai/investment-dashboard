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


RISK_TAG_SCORES = {
    "positive": 15,
    "neutral": 38,
    "caution": 60,
    "risk": 78,
    "critical": 95,
}


def classify_disclosure(report_name: str) -> tuple[str, str, int]:
    name = report_name.replace(" ", "").upper()

    critical_rules: list[tuple[list[str], str]] = [
        (["의견거절", "부적정", "계속기업불확실성", "상장폐지사유발생"], "감사의견"),
        (["상장폐지", "거래정지", "관리종목"], "거래위험"),
        (["횡령", "배임"], "횡령배임"),
        (["회생절차"], "회생절차"),
        (["자본잠식"], "자본잠식"),
    ]
    for keywords, disclosure_type in critical_rules:
        if any(keyword in name for keyword in keywords):
            return disclosure_type, "critical", RISK_TAG_SCORES["critical"]

    audit_risk_keywords = [
        "한정",
        "감사범위제한",
        "내부회계관리제도비적정",
    ]
    if any(keyword in name for keyword in audit_risk_keywords):
        return "감사의견", "risk", RISK_TAG_SCORES["risk"]

    rules: list[tuple[list[str], str, str]] = [
        (["공급계약", "단일판매", "판매공급계약"], "공급계약", "positive"),
        (["자기주식", "자사주"], "자기주식취득", "positive"),
        (["현금배당", "배당결정"], "현금배당", "positive"),
        (["무상증자"], "무상증자", "positive"),
        (["신규시설투자", "시설투자"], "신규시설투자", "neutral"),
        (["합병", "영업양수"], "합병영업양수", "neutral"),
        (["유상증자"], "유상증자", "caution"),
        (["전환사채", "CB"], "전환사채", "caution"),
        (["신주인수권부사채", "BW"], "신주인수권부사채", "caution"),
        (["교환사채", "EB"], "교환사채", "caution"),
        (["최대주주변경", "최대주주 변경"], "최대주주변경", "caution"),
        (["소송", "분쟁", "청구"], "소송", "risk"),
        (["영업정지"], "영업정지", "risk"),
        (["불성실공시"], "불성실공시", "risk"),
        (["감사의견", "감사보고서"], "감사의견", "neutral"),
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
            "neutral",
        ),
    ]
    for keywords, disclosure_type, risk_tag in rules:
        if any(keyword in name for keyword in keywords):
            return disclosure_type, risk_tag, RISK_TAG_SCORES[risk_tag]
    return "기타", "neutral", RISK_TAG_SCORES["neutral"]


def aggregate_disclosure_risk(disclosures: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "stock_code",
        "aggregate_risk_tag",
        "aggregate_risk_score",
        "recent_caution_count",
        "recent_risk_count",
        "latest_disclosure_date",
    ]
    if disclosures.empty or "stock_code" not in disclosures.columns:
        return pd.DataFrame(columns=columns)

    df = disclosures.copy()
    if "risk_score" not in df.columns:
        classifications = df["report_nm"].fillna("").map(classify_disclosure)
        df["risk_score"] = classifications.map(lambda item: item[2])
        df["risk_tag"] = classifications.map(lambda item: item[1])
    df["rcept_date"] = pd.to_datetime(
        df.get("rcept_dt", ""), format="%Y%m%d", errors="coerce"
    )
    latest_date = df["rcept_date"].max()
    if pd.isna(latest_date):
        latest_date = pd.Timestamp.today().normalize()
    recent_cutoff = latest_date - pd.Timedelta(days=30)

    rows: list[dict[str, object]] = []
    for stock_code, group in df.groupby("stock_code"):
        tags = set(group["risk_tag"].fillna("neutral"))
        recent = group[group["rcept_date"].fillna(pd.Timestamp.min) >= recent_cutoff]
        recent_caution_count = int(recent["risk_tag"].isin(["caution"]).sum())
        recent_risk_count = int(recent["risk_tag"].isin(["risk", "critical"]).sum())
        max_score = float(group["risk_score"].fillna(RISK_TAG_SCORES["neutral"]).max())
        positive_count = int(group["risk_tag"].eq("positive").sum())

        if "critical" in tags:
            aggregate_tag = "critical"
            aggregate_score = max(90.0, max_score)
        else:
            aggregate_score = max_score
            aggregate_score += min(recent_caution_count * 5, 10)
            aggregate_score += min(recent_risk_count * 8, 16)
            aggregate_score -= min(positive_count * 4, 8)
            aggregate_score = max(10.0, min(89.0, aggregate_score))
            aggregate_tag = _risk_tag_from_score(aggregate_score)

        rows.append(
            {
                "stock_code": stock_code,
                "aggregate_risk_tag": aggregate_tag,
                "aggregate_risk_score": round(aggregate_score, 1),
                "recent_caution_count": recent_caution_count,
                "recent_risk_count": recent_risk_count,
                "latest_disclosure_date": (
                    group["rcept_date"].max().strftime("%Y%m%d")
                    if not pd.isna(group["rcept_date"].max())
                    else ""
                ),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _risk_tag_from_score(score: float) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "risk"
    if score >= 50:
        return "caution"
    if score >= 30:
        return "neutral"
    return "positive"


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
                "risk_score",
                "data_source",
            ]
        )
        empty.attrs["data_source"] = data_source
        return empty
    enriched = df.copy()
    classifications = enriched["report_nm"].fillna("").map(classify_disclosure)
    enriched["disclosure_type"] = classifications.map(lambda item: item[0])
    enriched["risk_tag"] = classifications.map(lambda item: item[1])
    enriched["risk_score"] = classifications.map(lambda item: item[2])
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
