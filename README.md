# Conversion QA

Upload Google Ads, Meta Ads and Shopify CSV exports. Run deterministic data-quality checks, review evidence-backed exceptions and export reports.

## Stack
- React + Vite + TypeScript
- FastAPI + Pandas
- SQLite + SQLAlchemy

## Status
Initial scaffold is being built. The application is designed to compare aggregate platform conversion totals with Shopify order data without claiming transaction-level attribution.

## Local development
Backend:
```bash
cd backend
python -m venv .venv
# activate the environment, then:
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

See backend tests and sample datasets for deterministic checks.