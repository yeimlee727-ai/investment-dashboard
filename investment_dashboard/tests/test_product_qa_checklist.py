from __future__ import annotations

from pathlib import Path


def test_product_qa_checklist_covers_stabilization_baseline() -> None:
    checklist = Path("docs/QA_CHECKLIST.md")

    text = checklist.read_text(encoding="utf-8")

    assert "decision-support" in text
    assert "MockBroker" in text
    assert "TossBrokerPlaceholder" in text
    assert "REAL_WITH_FALLBACK" in text
    assert "2,630,785원" in text
    assert "GRAB is not part of the default mock portfolio sample" in text
    assert "LLM API" not in text
    assert "order execution" in text
    assert "control appears" in text
