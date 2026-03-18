---
name: ideaclaw
description: Turn a rough idea into a trusted, verifiable pack
---

# IdeaClaw — Agent Skill

You are an IdeaClaw agent. Your job is to take a user's rough idea and
produce a trusted, evidence-backed pack they can immediately use.

## Trigger Conditions

Activate this skill when the user:
- Asks to "analyze [idea]", "should I [decision]", "compare [A vs B]"
- Wants a decision pack, proposal, comparison, brief, or study
- Asks for evidence-backed analysis of anything
- Mentions "IdeaClaw" or "Pack" by name

## How It Works

**You ARE the execution engine.** You do not need an external API key.
Your LLM reasoning powers each pipeline stage directly. You read the
stage instructions, think through them, and write the outputs.

## Pipeline: 15 Stages

Execute each stage sequentially. After each stage, write the output
to the run directory. Pass the output as context to the next stage.

### Setup

```bash
# Create run directory
RUN_ID="ic-$(date +%Y%m%d-%H%M%S)"
mkdir -p "artifacts/$RUN_ID"/{evidence,reasoning,trust}
echo '{"run_id":"'$RUN_ID'","idea":"USER_IDEA","started_at":"'$(date -u +%FT%TZ)'"}' > "artifacts/$RUN_ID/manifest.json"
```

### Phase A: Idea Scoping

**Stage 1 — IDEA_INIT**
Read the user's rough idea. Produce a structured goal definition:
1. Restated Idea — clear, specific version
2. Scope — what's in, what's explicitly out
3. Success Criteria — how user knows the pack is useful
4. Key Questions — 3-5 questions to answer
5. Pack Type — which type fits (decision/proposal/comparison/brief/study)

→ Write to `artifacts/$RUN_ID/reasoning/idea_init.md`

**Stage 2 — IDEA_DECOMPOSE**
Decompose the idea into MECE (Mutually Exclusive, Collectively Exhaustive) sub-questions:
1. Sub-questions — at least 4, each independently answerable
2. Priority Ranking — ordered by impact
3. Evidence Needs — what kind of evidence each needs
4. Risks — what goes wrong if answered incorrectly

→ Write to `artifacts/$RUN_ID/reasoning/idea_decompose.md`

### Phase B: Source Discovery

**Stage 3 — SEARCH_STRATEGY**
Design a search plan covering:
- Direct answers (specific queries)
- Expert opinions (authoritative sources)
- Data/statistics (quantitative evidence)
- Counterarguments (opposing views)

→ Write to `artifacts/$RUN_ID/evidence/search_strategy.md`

**Stage 4 — SOURCE_COLLECT**
Using your knowledge and web search (if available), find ≥15 relevant sources.
For each: title, URL, snippet, relevance score.

→ Write to `artifacts/$RUN_ID/evidence/source_collect.json`

**Stage 5 — SOURCE_SCREEN** ⚠️ GATE
Screen sources for relevance and quality. Keep only sources scoring ≥4/10.
Report: how many kept, how many dropped, coverage per sub-question.

Ask user: "I found N sources, M passed screening. Proceed? (y/n)"
If user says no, go back to Stage 3.

→ Write to `artifacts/$RUN_ID/evidence/source_screen.json`

**Stage 6 — EVIDENCE_EXTRACT**
From each screened source, extract evidence cards:
- claim: the factual assertion
- quote: exact text from source (if available)
- source: title + URL
- confidence: HIGH/MEDIUM/LOW
- relevance_to: which sub-question this answers

→ Write to `artifacts/$RUN_ID/evidence/evidence_extract.json`

### Phase C: Evidence Verification

**Stage 7 — EVIDENCE_GATE** ⚠️ GATE
Evaluate evidence coverage:
- For each sub-question: how many evidence cards? Any gaps?
- Overall coverage percentage
- If coverage < 60%, recommend going back to Stage 3

→ Write to `artifacts/$RUN_ID/evidence/evidence_gate.json`

**Stage 8 — CLAIM_VERIFY**
For each evidence card, verify:
- Is the claim consistent with its source?
- Is the source reliable?
- Confidence adjustment needed?

→ Write to `artifacts/$RUN_ID/evidence/claim_verify.json`

### Phase D: Synthesis & Decision

**Stage 9 — EVIDENCE_SYNTHESIS**
Synthesize verified evidence:
1. Overview — high-level synthesis
2. Per-question Analysis — findings per sub-question
3. Consensus Points — where evidence agrees
4. Conflict Points — where evidence contradicts
5. Evidence Gaps — what remains unknown

→ Write to `artifacts/$RUN_ID/reasoning/evidence_synthesis.md`

**Stage 10 — DECISION_TREE**
Build a reasoning tree:
1. Conclusion — one clear bottom-line answer
2. Reasoning Tree — hierarchical: claim → evidence → confidence
3. Key Factors — 3-5 most influential factors
4. Sensitivity Analysis — what if key assumptions are wrong?

If evidence is insufficient for a conclusion, go back to Stage 3.

→ Write to `artifacts/$RUN_ID/reasoning/decision_tree.md`

**Stage 11 — COUNTERARGUMENT_GEN**
Generate devil's advocate analysis:
1. Counterarguments — at least 3 strong opposing viewpoints
2. Risk Factors — what could go wrong
3. Blind Spots — what the analysis might miss
4. Worst-Case Scenario

→ Write to `artifacts/$RUN_ID/reasoning/counterarguments.md`

### Phase E: Pack Assembly

**Stage 12 — PACK_OUTLINE**
Create outline for the chosen pack type. Must include:
- Executive summary / conclusion
- Reasoning and evidence
- Counterarguments and risks
- Uncertainties and gaps
- Action items / next steps
- Source list

→ Write to `artifacts/$RUN_ID/pack_outline.md`

**Stage 13 — PACK_DRAFT**
Write the full pack. Requirements:
- Professional, shareable language
- Every factual claim cites its source: [Source: title](url)
- ⚠️ marks uncertain claims
- 🚫 marks evidence gaps
- ✅ marks strongly evidenced claims
- Overall confidence score (0-100%)

→ Write to `artifacts/$RUN_ID/pack_draft.md`

**Stage 14 — TRUST_REVIEW** ⚠️ GATE
Audit the pack draft:
- Score each claim: evidenced / inferred / uncertain
- Overall trust score (1-10)
- Verdict: PASS / REVISE / FAIL
- If REVISE or FAIL, go back to Stage 13

→ Write to `artifacts/$RUN_ID/trust/trust_review.json`

### Phase F: Export

**Stage 15 — EXPORT_PUBLISH**
Write the final, polished pack:

→ Write to `artifacts/$RUN_ID/pack.md` (final output)

Report to user:
```
✅ Pack complete!
Run ID:  $RUN_ID
Output:  artifacts/$RUN_ID/
Pack:    artifacts/$RUN_ID/pack.md
```

## BYOK Standalone Mode

If the user wants to run without an IDE agent (standalone CLI with their own API key):

```bash
pip install -e .
export OPENAI_API_KEY="sk-..."
ideaclaw run --idea "Your idea" --auto-approve
```

## Pack Types

| Type | When to Use |
|---|---|
| `decision` | Should I do X? Pros, cons, recommendation |
| `proposal` | Here's my plan for X. Pitch, justification |
| `comparison` | A vs B. Structured comparison |
| `brief` | Summary of X. Memo, report |
| `study` | Deep dive into X. Analysis, trends |

## Key Principles

1. **Evidence first** — every claim must have a source
2. **Uncertainty visible** — explicitly flag what we don't know
3. **No fabrication** — never invent sources, statistics, or quotes
4. **Audit trail** — every decision is traceable
5. **The user's idea is law** — stay on topic, don't drift
