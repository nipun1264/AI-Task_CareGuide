# Document Intelligence

An AI-assisted invoice/document-processing MVP: upload PDFs, images, XLSX/XLS and CSV; extract text; create a structured invoice record; validate totals; reconcile matching documents; and search the results.

## Start locally

1. Copy `.env.example` to `.env` and optionally set `OPENAI_API_KEY`.
2. Run `docker compose up --build`.
3. Open `http://localhost:8000/docs` for the API and `http://localhost:3000` for the dashboard.

Without an OpenAI key the application still runs and uses a conservative rule-based extractor. Set `OPENAI_API_KEY` to enable structured LLM extraction.

## API flow

`POST /api/v1/documents/upload` accepts one or more files and queues processing. Poll `GET /api/v1/documents/{id}`. Extracted invoices, validation results, search, corrections, and reconciliation are exposed under `/api/v1`.

## Architecture

FastAPI owns the API; Celery runs slow processing; PostgreSQL stores records; Redis brokers jobs; MinIO stores originals. The processing pipeline records source text, derives structured fields, applies deterministic financial rules, and creates reconciliation candidates. This is deliberately a modular monolith so its contracts can later be split into services.
