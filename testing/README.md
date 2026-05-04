# Testing fixtures — synthetic formation, operating, and trust PDFs

This directory contains AI-generated PDFs for each demo scenario (A, B, C, D
plus the RM-facing E, F, G). Drop any of these PDFs into the BSA/AML Copilot
upload panel to exercise the full document-ingestion → UBO-resolution →
KYC/KYB screening → justification + escalation pipeline end-to-end.

Every document here is synthetic. Names, addresses, IDs, and facts were written
for testing only; none of these documents represent real people or entities.
Each page footer carries a "TEST FIXTURE — SYNTHETIC DOCUMENT" stamp.

## Layout

| Directory | Scenario | What it exercises |
|---|---|---|
| `scenario_a/` | Clean nested LLC + revocable trust | Single US-citizen UBO, no adverse media |
| `scenario_b/` | Irrevocable trust + adverse media | Full EDD memo, OFAC potential match, foreign national |
| `scenario_c/` | 3-level nesting + German GmbH + LP | Deep graph traversal, multiple foreign nationals |
| `scenario_d/` | Joint revocable trust + Cayman entity | Joint grantors, high-risk jurisdiction |
| `scenario_e/` | **RM intake — foreign founder of US LLC** | Brazilian sole-member of a Delaware LLC; agent should request passport, ITIN/W-8BEN, source of funds, CTA BOI |
| `scenario_f/` | **RM intake — foreign-domiciled parent + US sub** | UK Ltd opens a Delaware C-corp; agent should request apostille, certified translation, foreign UBO certification, W-8BEN-E, full Companies House filing |
| `scenario_g/` | **RM intake — escalation case** | Multi-tier global enterprise (Cayman + Singapore + BVI + Switzerland) with nominee + irrevocable trust; agent should call `recommend_escalation` |

Each scenario directory contains formation documents (Articles of Organization
/ Certificate of Formation / commercial register extracts), operating
agreements, trust agreements, and — for Scenario B — a stubbed adverse media
report.

## Regenerating

```bash
# from repo root
pip install -r backend/requirements.txt
python testing/scripts/generate_pdfs.py
```

The generator reads `backend/fixtures/fixture_*.json` and renders one PDF per
document definition. Update the fixtures to evolve the synthetic corpus, then
re-run the script.

## Using in the copilot

1. Start the backend (`uvicorn app.main:app --reload --port 8001` in
   `backend/`).
2. Start the frontend (`npm run dev` in `frontend/`).
3. Open `http://localhost:3001`, drag one scenario's PDFs into the upload
   area, and click "Run analysis".
