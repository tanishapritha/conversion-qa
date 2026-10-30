# Conversion QA

Conversion QA is a lightweight quality-assurance tool for ecommerce advertising agencies.

**Workflow:** Upload → Map → Analyze → Investigate → Export.

## Stack
- React + Vite + TypeScript
- FastAPI + Pandas
- SQLite + SQLAlchemy

## Run locally

Backend:
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.sample_data
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

API docs: http://127.0.0.1:8000/docs · UI: http://localhost:5173

## Detection semantics
- Duplicate IDs mean repeated records, not proven duplicate purchases.
- Missing UTMs mean attribution fields are absent from this export, not necessarily a tracking failure.
- Conversion drops are signals against the preceding seven available reporting dates and require an average baseline of at least two.
- Reconciliation is aggregate-only; it does not establish transaction-level or campaign-level attribution.
- Cancelled/test orders stay in the source data and are flagged. Basic order count excludes them; refunds remain included.

## Tests
```bash
cd backend
pytest
```

Uploaded files and SQLite data are stored under `backend/data/`. Upload registry is process-local, so upload and analysis must use the same backend process.

## V1 limitations
Attribution windows, conversion lag, timezone normalization across platforms, currency conversion and multi-user security are not modeled. Use synthetic or appropriately permissioned data for pilots.
