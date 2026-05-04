# Plan: Agentic EDD Loop with Embedded FinCEN Rules

## Context

The current pipeline at `backend/app/routers/edd.py:_analyze_case` is a fixed sequence (extract graph → resolve UBOs → screen → score risk → draft memo). Claude is called at exactly two slots; everything else is deterministic. This means cases that need investigative judgment — "should I ask for the operating agreement of this sub-LLC?", "is this OFAC near-match worth chasing?", "did the memo address every adverse-media hit?" — get the same canned treatment as the easy ones.

We are converting the investigative middle of the pipeline into an **agent loop driven by Claude Opus 4.7** with a tool registry, a per-case scratchpad, lazy ownership traversal, real screening tool calls (still backed by stubs), a self-critique pass, and parallel subagents per UBO. The deterministic legal rails — FinCEN 25% math, trust look-through arithmetic, citation resolution — stay deterministic. A static FinCEN rules digest is embedded in the agent system prompt so the agent can quote regulations without a network call.

The existing `_analyze_case` path stays intact behind the existing endpoint. The agent runs behind a new endpoint so we can A/B and so fixtures keep working.

## Approach

A new orchestrator (`agent_orchestrator.py`) runs `client.messages.create` in a `while stop_reason == "tool_use"` loop. The loop has access to a tool registry that wraps existing services (no rewrites). The orchestrator owns a per-case `AgentScratchpad` that persists across upload-driven re-analyses. After the agent finalizes a memo, a verifier subagent reviews it and can reject/request revisions. Per-UBO screening runs as parallel subagents.

### Critical files to modify

| File | Change |
|---|---|
| `backend/app/config.py:21` | Add `ANTHROPIC_AGENT_MODEL: str = "claude-opus-4-7"`. Keep `ANTHROPIC_MODEL` for the legacy pipeline. |
| `backend/app/routers/edd.py` | Add `POST /api/edd/analyze-agent` (mirrors `AnalyzeRequest`/`AnalyzeResponse`). Old `/api/edd/analyze` untouched. |
| `backend/app/models.py` | Add `AgentScratchpad`, `AgentToolCall`, `AgentTrace` models. Extend `_Case` (in `case_store.py`) with `scratchpad: AgentScratchpad`. |
| `backend/app/services/case_store.py` | Add `update_scratchpad(case_id, scratchpad)` and `get_scratchpad(case_id)`. |
| `frontend/components/scenario/use-scenario.ts` | Add a feature flag (env-driven) selecting `analyzeCaseAgent` vs `analyzeCase`. |
| `frontend/components/memo/memo-panel.tsx` | The Reasoning tab already exists; replace its `AgentWorkProduct` consumer with one that also renders `AgentTrace` tool calls when present. |

### New files

| File | Role |
|---|---|
| `backend/app/services/agent_orchestrator.py` | The tool-use loop. ~250 lines. |
| `backend/app/services/agent_tools.py` | Tool schemas + dispatcher (Python `dict[str, Callable]` keyed by tool name). |
| `backend/app/services/agent_prompts.py` | System prompt + embedded FinCEN digest. |
| `backend/app/services/fincen_digest.py` | Loads `fincen_rules.md` once at import and exposes `RULES_MARKDOWN`. |
| `backend/fixtures/fincen_rules.md` | Static digest: 25% threshold, 31 CFR § 1010.230 CDD, § 1020.220 CIP, BOI reporting (31 USC § 5336), trust look-through, jurisdiction risk lists. ~3 KB. |
| `backend/app/services/agent_verifier.py` | Self-critique subagent. |

## Tool Registry

All tools wrap existing functions (no behavior changes; just exposed as tool calls). Schemas live in `agent_tools.py`. The dispatcher mutates `AgentScratchpad` and returns JSON-serializable results.

| Tool name | Wraps | Why the agent calls it |
|---|---|---|
| `list_documents` | `case_store.get_case` (documents only) | Inventory before reading anything. |
| `read_document` | `pdf_extractor.ExtractedPDF.pages` (already in `case.pdfs`) | Lazy page-level read; agent picks which doc to inspect. |
| `extract_subgraph` | `document_intelligence.extract_graph` over a *subset* of docs | Re-extract entities for newly-uploaded docs only. |
| `resolve_ownership` | `ubo_resolver.resolve` on a synthetic fixture | Run UBO resolution after the graph is assembled. Deterministic, but the agent decides *when* to call it. |
| `screen_ofac` | `ofac_service.screen` (`backend/app/services/ofac_service.py:76`) | Stub today; tool surface is real. |
| `screen_pep` | `pep_service.screen` (`pep_service.py:74`) | Same. |
| `screen_adverse_media` | `adverse_media_service.screen` (`adverse_media_service.py:71`) | Same. |
| `assess_business_risk` | `business_risk.assess` | Deterministic risk classification. |
| `check_name_consistency` | `name_consistency.check` (`name_consistency.py:151`) | Already async + already calls Claude internally for ambiguity; expose as a tool. |
| `assess_ubo_completeness` | `ubo_completeness.assess` | Audit declared owners against ≥25% threshold. |
| `build_cdd_checklist` | `cdd_requirements.build_checklist` | Materialize the FinCEN-mandated docs list. |
| `mark_required_document` | New helper in `case_store` | Agent can request a doc the deterministic checklist didn't catch (e.g., second-tier LLC's operating agreement). Adds to `case.scratchpad.requested_documents`. |
| `note` | Appends to `scratchpad.notes` | Free-form journal entry; survives across re-analyses. |
| `draft_memo` | `claude_client.draft_full_edd_memo` / `draft_ubo_resolution_memo` | Final step. Returns memo sections with citations. |
| `finalize` | Returns the assembled `AnalyzeResponse` and exits the loop | Agent's "I'm done" signal. |

Tool schemas reuse existing Pydantic models (`ResolvedUBO`, `OFACResult`, `PEPResult`, `CDDChecklist`) by emitting `.model_json_schema()` into the `input_schema`. The deterministic `_resolve_citation_markers` helper at `claude_client.py:44` is reused unchanged.

## Agent Loop

```python
# backend/app/services/agent_orchestrator.py (sketch)

async def run(case: _Case) -> AnalyzeResponse:
    scratchpad = case.scratchpad or AgentScratchpad.fresh()
    messages = [
        {"role": "user", "content": render_case_brief(case, scratchpad)}
    ]
    trace: list[AgentToolCall] = []
    final_response: AnalyzeResponse | None = None

    for _ in range(MAX_ITERATIONS := 30):
        response = await client.messages.create(
            model=settings.ANTHROPIC_AGENT_MODEL,
            max_tokens=4000,
            system=AGENT_SYSTEM_PROMPT,        # includes FinCEN digest
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        tool_uses = [b for b in response.content if b.type == "tool_use"]

        # Parallelize per-UBO screening (and any other independent calls)
        results = await asyncio.gather(*[dispatch(t, case, scratchpad) for t in tool_uses])

        for tu, result in zip(tool_uses, results):
            trace.append(AgentToolCall(name=tu.name, input=tu.input, output=result))
            if tu.name == "finalize":
                final_response = result  # already an AnalyzeResponse
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": json.dumps(result, default=pydantic_encoder),
            })

        messages.append({"role": "user", "content": tool_results})
        if final_response is not None:
            break

    if final_response is None:
        raise AnalysisError("Agent exited without finalizing.")

    # Verifier pass
    revision = await agent_verifier.review(final_response, scratchpad)
    if revision.needs_revision:
        final_response = await _apply_verifier_revisions(final_response, revision)

    case_store.update_scratchpad(case.case_id, scratchpad.with_trace(trace))
    return final_response
```

`MAX_ITERATIONS=30` is a hard cap. Per-tool timeouts are 30s. Failed tool calls return `{"error": ...}` so the agent can retry.

## FinCEN Digest

`backend/fixtures/fincen_rules.md` is a curated ~3 KB markdown file covering:

- **31 CFR § 1010.230 (CDD Rule)** — 25% beneficial ownership threshold, control prong, exempted entity types.
- **31 CFR § 1020.220 (CIP Rule)** — identity verification requirements per UBO ≥25%.
- **31 USC § 5336 (Corporate Transparency Act / BOI)** — BOI reporting effective Jan 1, 2024; reporting company definition; exemptions.
- **Trust look-through** — revocable → grantor; irrevocable → trustee (control) + named beneficiaries (economic).
- **Jurisdiction risk** — FATF grey/black-list snapshot, FFIEC high-risk list (Cayman, BVI, Panama, Seychelles, Belize already used in `case_analyzer.py:120`).

`fincen_digest.py` reads the file once and exports `RULES_MARKDOWN: str`. `agent_prompts.AGENT_SYSTEM_PROMPT` interpolates it under a `<fincen_rules>` block. Anthropic prompt caching (`cache_control: {"type": "ephemeral"}` on the system block) keeps the digest cheap across iterations.

The digest is also surfaced in the citation system: when the agent cites a rule, the prompt requires `[fincen:31CFR1010.230]` or `[fincen:31USC5336]` markers. `_resolve_citation_markers` is extended to recognize the `fincen:` prefix and resolve to a "FinCEN Rules" pseudo-document with the section title as excerpt.

## Subagents

**Per-UBO screening** — when the agent calls `screen_ofac`/`screen_pep`/`screen_adverse_media` for multiple UBOs in the same turn, the dispatcher already runs them in parallel via `asyncio.gather`. No subagent needed.

**Verifier (`agent_verifier.py`)** — after `finalize`, runs one Claude call with a different system prompt: *"You are a senior BSA reviewer. Check every claim in this memo against the screening results and document corpus. Return a `verifier_report` tool call with: claims_unsupported (list of section_id + claim text), risks_unaddressed (risk_flag values not mentioned in memo), citations_missing (factual statements with no marker), needs_revision (bool)."* If `needs_revision`, the orchestrator re-invokes the drafter with the verifier feedback appended; capped at 2 revision rounds.

## Persistence

`AgentScratchpad` (Pydantic model in `models.py`):

```python
class AgentScratchpad(BaseModel):
    notes: list[str] = []                              # `note` tool appends
    requested_documents: list[RequestedDoc] = []        # `mark_required_document`
    last_trace: list[AgentToolCall] = []                # for debugging / UI
    iteration_count: int = 0
    fincen_lookups: list[str] = []                     # rule refs the agent invoked
```

Stored on `_Case.scratchpad` in `case_store.py`. Survives upload-driven re-runs: when the user uploads a new doc, the next `run()` sees the previous scratchpad and the agent can say "you asked for the operating agreement on April 12; this upload satisfies that request" via the `notes` history rendered in the case brief.

## Frontend

The Reasoning tab in `frontend/components/memo/memo-panel.tsx` already renders `AgentWorkProduct.steps`. Extend it to also render `AgentTrace.tool_calls` (collapsible, showing tool name + summarized input/output). Existing components (`citation-tooltip.tsx`, `cited-text.tsx`) handle `[fincen:...]` markers automatically once `_resolve_citation_markers` emits them as Citations with `doc_id="fincen"`.

A toggle in `case-sidebar.tsx` ("Use agent loop" — default on, env-defaultable via `NEXT_PUBLIC_AGENT_DEFAULT`) chooses between `analyzeCase` (legacy) and `analyzeCaseAgent` (new).

## Removed Functionality

`POST /api/edd/approve` and `GET /api/edd/audit` were already removed in a prior change. No further cleanup needed there.

## Verification

End-to-end checks, in order:

1. **Backend boots** — `uvicorn app.main:app --port 8001` starts without import errors. Verify `from app.services import agent_orchestrator, agent_tools, agent_verifier, fincen_digest` succeeds.
2. **FinCEN digest loads** — `python -c "from app.services.fincen_digest import RULES_MARKDOWN; print(len(RULES_MARKDOWN))"` is non-zero.
3. **Tool schemas validate** — `python -c "from app.services.agent_tools import TOOL_SCHEMAS; import json; json.dumps(TOOL_SCHEMAS)"` works.
4. **Legacy path unchanged** — `curl -X POST localhost:8001/api/edd/analyze -d '{"fixture_id":"fixture_a"}'` returns the same `AnalyzeResponse` shape it did before.
5. **Agent path on a fixture-derived case** — upload `fixture_b` documents to a fresh case, then `POST /api/edd/analyze-agent` with the case_id. Confirm:
   - Final `AnalyzeResponse` includes resolved UBOs ≥25%.
   - At least one `[fincen:31CFR1010.230]` citation appears in the memo.
   - `case.scratchpad.last_trace` shows a sequence of tool calls (extract_subgraph → resolve_ownership → screen_* → draft_memo → finalize).
6. **Re-analysis on upload** — upload an additional document; re-run `analyze-agent`. Confirm the scratchpad's `notes` from the prior run appear in the case brief and that the agent acknowledges them.
7. **Verifier rejects an obviously broken memo** — temporarily monkeypatch `draft_memo` to omit the OFAC section when there's a hit; confirm verifier returns `needs_revision=true` and a revision round runs.
8. **Frontend** — `cd frontend && npm run dev`. Toggle agent loop on; run a case; Reasoning tab renders both deterministic steps and the new tool-call trace; FinCEN citations render with `[N]` numbering and tooltip excerpts.
9. **Iteration cap** — temporarily set `MAX_ITERATIONS=2`; confirm `AnalysisError("Agent exited without finalizing.")` surfaces cleanly through the existing `AnalysisError` handler in `app/exceptions.py`.

Tests to add: a unit test in `backend/tests/test_agent_orchestrator.py` (new) that uses a `FakeAnthropicClient` returning canned tool-use responses to assert the dispatcher routes correctly and the loop terminates on `finalize`.
