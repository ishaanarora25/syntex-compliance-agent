# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Syntex Compliance Agent is an AI-native Enhanced Due Diligence (EDD) system for commercial lending. It resolves Ultimate Beneficial Owners (UBOs) through trust look-through logic, screens against OFAC sanctions, and generates structured compliance memos with citations — all backed by Claude.

The repo has two deployable services:
- **`backend/`** — FastAPI (Python 3.11) API deployed on Render
- **`frontend/`** — Next.js 16 app deployed on Vercel

## Commands

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8001
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:3001
npm run build
npm run lint
```

## Architecture

### Data Flow

```
User selects fixture (test scenario JSON)
  → POST /api/edd/analyze
      → UBO Resolver: DFS traversal + trust look-through → effective ownership %
      → OFAC Service: stub screening per entity
      → Graph Builder: BFS layout → React Flow nodes/edges
      → Reasoning Writer: deterministic step trace
      → Claude API: draft memo with [doc_id:page] citation markers
      → Citation parser: maps markers → sequential [N] with excerpts
  → Frontend renders ownership graph (React Flow) + tabbed memo + reasoning trace
  → POST /api/edd/approve → in-memory audit log
```

### Trust Look-Through Logic (`backend/app/services/trust_logic.py`, `ubo_resolver.py`)

- **Revocable trusts:** Pass through 100% to grantor (grantor controls assets)
- **Irrevocable trusts:** Look to trustee (control) + named beneficiaries (economic interest)
- UBO threshold: 25% (FinCEN CDD rules)
- Joint trusts: each grantor treated as 50% controller

### Citation System

Claude is prompted to embed `[doc_id:page]` markers inline. The backend parses these into sequential `[N]` references with pulled excerpts from the fixture document corpus. Frontend renders them as clickable footnotes.

### In-Memory State

No database. Two in-memory stores in the backend:
- Fixture cache (loaded at startup from `backend/fixtures/fixture_*.json`)
- Audit log (lost on restart)

### Long-Running Requests

The analyze endpoint takes 60–90s for full EDD memo generation. `frontend/app/api/backend/edd/analyze/route.ts` is a custom Next.js route handler that proxies directly to the backend with a 3-minute timeout, bypassing the default Next.js proxy limit.

## Key Files

| File | Role |
|---|---|
| `backend/app/routers/edd.py` | Core endpoints: `/fixtures`, `/analyze`, `/approve`, `/audit` |
| `backend/app/services/claude_client.py` | AsyncAnthropic wrapper; memo drafting via Claude |
| `backend/app/services/ubo_resolver.py` | DFS UBO traversal with trust look-through |
| `backend/app/services/trust_logic.py` | FinCEN trust rules implementation |
| `backend/app/services/graph_builder.py` | Fixture → React Flow schema conversion |
| `backend/app/services/reasoning_writer.py` | Deterministic agent work product trace |
| `backend/app/services/prompts.py` | Claude system prompts |
| `backend/app/models.py` | All Pydantic request/response models (~35+) |
| `backend/fixtures/` | Test scenarios A, B, stress_c, stress_d as JSON |
| `frontend/app/page.tsx` | Main 2-panel layout (graph + memo) |
| `frontend/components/scenario/use-scenario.ts` | Central state hook |
| `frontend/lib/api.ts` | Typed fetch wrappers for backend |
| `frontend/types/edd.ts` | TypeScript interfaces mirroring backend models |

## Environment Variables

### Backend (`backend/.env`)
```
ANTHROPIC_API_KEY=sk-ant-...         # Required
ANTHROPIC_MODEL=claude-sonnet-4-5    # Optional; defaults to claude-sonnet-4-5
ALLOWED_ORIGINS=http://localhost:3001 # Comma-separated CORS origins
```

### Frontend (`frontend/.env.local`)
```
BACKEND_URL=http://localhost:8001    # Optional; defaults to http://localhost:8001
```

## Deployment

- **Backend:** Render (`render.yaml`) — Python 3.11 web service, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Frontend:** Vercel (`frontend/vercel.json`) — Next.js framework
