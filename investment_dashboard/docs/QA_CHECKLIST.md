# Product QA Checklist

This checklist is for the read-only investment decision-support dashboard. It is
not a trading checklist, recommendation workflow, brokerage connection guide, or
account lookup process.

## Safety Baseline

- Confirm the app states that it is decision-support only.
- Confirm MockBroker actions are described as virtual orders or virtual
  positions only.
- Confirm TossBrokerPlaceholder remains a placeholder.
- Confirm no API key input, brokerage login, account lookup, or order execution
  control appears.
- Confirm report downloads are local review files only.

## Data Mode Clarity

- SAMPLE mode must be described as local sample/reference data, not a real
  account.
- REAL_WITH_FALLBACK mode must be described as public/external quote lookup with
  possible fallback, not a real account or trade confirmation source.
- SAMPLE/FALLBACK warnings should remain visible near analysis outputs.

## Display Consistency

- Stock labels should prefer name first and fall back to symbol when name is
  missing.
- KRW amounts should display as `1,234,567원`.
- Percentage and weight fields should display as `12.34%`.
- USD local-currency values should display with `$` or `USD`, not as KRW.
- Return columns must never show the KRW suffix.

## Mock Portfolio Reference

- Default mock portfolio sample contains three KR positions: `360750`, `390390`,
  and `453870`.
- GRAB is not part of the default mock portfolio sample.
- Sample quote reference prices are:
  - `360750`: `28,300`
  - `390390`: `62,070`
  - `453870`: `12,465`
- Total market value should equal `2,630,785원` after replacing MockBroker
  positions with the default sample CSV.
- Summary totals should match the position table totals.

## Page Review

- Main app: top scanner chart uses stock names, with symbol retained in hover or
  table details.
- Stock scanner: table and chart use name-first labels and keep data source
  visible.
- Mock trading: table shows name, symbol, local-currency amount, KRW amount, and
  percent fields clearly.
- Portfolio strategy: language stays in review/check mode and avoids trading
  commands.
- Risk rebalancing: outputs remain scenario/review information, not exact order
  instructions.
- Decision Support: cockpit cards are visible first; payload JSON and safety
  flags stay in expandable detail sections.

## Validation Before Merge

Run from the project directory:

```powershell
.venv\Scripts\python.exe -m compileall app.py pages src tests
.venv\Scripts\python.exe -m pytest -vv -p no:cacheprovider
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m black --check .
git diff --check
```
