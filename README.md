# AI Document Intelligence Platform

Enterprise-grade, AI-driven document comparison platform that compares **only unified Input vs unified Output** across structural, lexical, OCR, semantic, and numeric layers.

## Key Features

- Multi-file ingestion for both sides (`.docx`, `.pdf`, `.txt`, `.xlsx`, `.png`, `.jpg`, `.jpeg`)
- Unified comparison scope:
  - Combine all Input files into one logical document
  - Combine all Output files into one logical document
  - Compare **Input vs Output only** (never input-input or output-output)
- 5-layer analysis engine:
  - Structural differences (section/block movement and heading changes)
  - Lexical differences (word-level, case, punctuation, typo-like edits)
  - OCR + visual text differences (including missing images in output)
  - Semantic drift and paraphrase detection (transformer embeddings)
  - Numeric/entity consistency checks (date/currency/percent/entity changes)
- Risk scoring (`Low | Medium | High`) with critical change highlights
- Professional reporting:
  - Export PDF report
  - Export JSON report
  - Export audit log
- Enterprise UI:
  - Dual upload zones
  - Remove file / cancel-all controls
  - Refresh/new operation button
  - Multi-stage analysis progress
  - Side-by-side mismatch viewer with filters

## Tech Stack

- Frontend: React + Tailwind CSS + Axios + jsPDF
- Backend: FastAPI + spaCy + sentence-transformers + pytesseract + pdfplumber + python-docx + rapidfuzz
- Runtime: Docker + Docker Compose

## System Architecture

```text
Frontend (React + Tailwind)
  -> POST /api/compare/jobs
  -> GET /api/compare/jobs/{job_id}

FastAPI API
  -> ingestion_service.py
      - parse docx/pdf/txt/xlsx
      - OCR images
      - preserve location metadata
      - unify Input and unify Output
  -> diff_engine.py
      - structural + lexical + OCR + numeric/entity diff
  -> semantic_engine.py
      - chunked embedding-based semantic analysis
  -> risk_analyzer.py
      - aggregate risk classification
  -> report_generator.py
      - summary, critical changes, audit log
```

## Project Structure

```text
.
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  │  └─ api_routes.py
│  │  ├─ services/
│  │  │  ├─ ingestion_service.py
│  │  │  ├─ ocr_service.py
│  │  │  ├─ diff_engine.py
│  │  │  ├─ semantic_engine.py
│  │  │  ├─ risk_analyzer.py
│  │  │  └─ report_generator.py
│  │  ├─ config.py
│  │  ├─ schemas.py
│  │  └─ main.py
│  ├─ requirements.txt
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ components/
│  │  │  ├─ UploadZone.jsx
│  │  │  └─ ResultsPanel.jsx
│  │  ├─ App.jsx
│  │  ├─ main.jsx
│  │  └─ main.css
│  └─ Dockerfile
└─ docker-compose.yml
```

## API Endpoints

- `GET /api/health`
- `POST /api/compare/jobs`
  - Starts async comparison job
- `GET /api/compare/jobs/{job_id}`
  - Returns status/progress/result
- `POST /api/compare`
  - Synchronous wrapper that waits for result

### Result Schema (Simplified)

```json
{
  "overall_similarity_score": 92.4,
  "structural_similarity": 95.1,
  "semantic_similarity": 90.2,
  "risk_assessment": "Medium",
  "critical_changes": [],
  "mismatches": [],
  "summary_explanation": "",
  "entity_comparison": [],
  "stage_progress": {},
  "audit_log": []
}
```

## Quick Start (Docker)

```powershell
cd C:\SOLOMON\Project\Cproject
docker compose up --build
```

Open:

- Frontend: `http://localhost:5173`
- API health: `http://localhost:8000/api/health`

## Local Development

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

## Deployment Notes

- Tesseract OCR must be available in runtime image/host.
- Current Docker backend runs single worker to avoid model duplication memory spikes.
- For production scale:
  - move job/cache state to Redis + worker queue
  - persist files in object storage
  - enable autoscaling for API and workers

## Performance Targets

- 100+ files per side (subject to file size/runtime limits)
- chunked semantic processing for large content
- async job pipeline with cached results

## Security and Operational Recommendations

- Add authentication and tenant isolation
- Add upload virus scanning and content validation
- Add rate-limiting and request-size controls
- Add persistent audit storage (DB)

## Future Improvements

- Layout-aware structural modeling (LayoutLM-family)
- Table cell-level semantic comparison
- Stamp/signature region detection with CV models
- Policy/rules engine for domain-specific risk scoring

## License

Add your preferred license (MIT/Apache-2.0/Proprietary) before publishing.
