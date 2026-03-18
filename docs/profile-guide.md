# Quality Profile Guide

IdeaClaw uses YAML-based quality profiles to standardize output for 122+ scenarios across 15 domains.

## How Profiles Work

Each profile defines 4 layers:

1. **Format** — Required sections, word limits, citation style
2. **Rubric** — 7-dimension weights and pass threshold
3. **Review** — Checklist items and auto-reject conditions
4. **Benchmark** — Reference scores for accepted/rejected work

## Using Profiles

### Auto-detect (default)

IdeaClaw auto-detects the best profile from your idea text:

```bash
ideaclaw run --idea "Write a systematic review of COVID treatments"
# → auto-detects: medical.systematic_review
```

### Explicit selection

```bash
ideaclaw run --idea "My grant proposal" --profile grants.nih_r01
```

### List available profiles

```bash
ideaclaw profiles                    # all 122 profiles
ideaclaw profiles --domain medical   # 12 medical profiles
ideaclaw profiles --domain cs_ml     # 9 CS/ML profiles
```

## Profile Inheritance

Profiles use YAML inheritance to reduce duplication:

```
_base_medical.yaml      ← shared format, rubric, review
  ├── rct.yaml          ← adds CONSORT checklist
  ├── systematic_review ← adds PRISMA checklist
  └── case_report.yaml  ← customizes sections
```

## Creating Custom Profiles

1. Create a YAML file in `ideaclaw/quality/profiles/{domain}/{scene}.yaml`
2. Follow this structure:

```yaml
meta:
  id: "mydomain.myscenario"
  name: "My Custom Profile"
  domain: "mydomain"
  inherits: "_base_mydomain"  # optional

format:
  sections:
    - name: "introduction"
      required: true
    - name: "analysis"
      required: true
    - name: "conclusion"
      required: true
  constraints:
    max_words: 5000
    citation_style: "apa"

rubric:
  dimensions:
    evidence_coverage:    { weight: 20 }
    claim_accuracy:       { weight: 20 }
    reasoning_quality:    { weight: 20 }
    actionability:        { weight: 15 }
    uncertainty_honesty:  { weight: 10 }
    structure_clarity:    { weight: 10 }
    counterargument_depth:{ weight: 5 }
  pass_threshold: 7.0

review:
  checklist:
    - "Introduction states the research question"
    - "Methods are reproducible"
  reject_if:
    - "No sources cited"
  source_requirements:
    min_sources: 10
    preferred_databases: ["google_scholar", "pubmed"]

benchmark:
  reference_scores:
    excellent: 9.0
    accepted: 7.0
    borderline: 5.5
```

3. Add auto-detection keywords to `ideaclaw/quality/loader.py` (optional)

## 7-Dimension Scoring

| Dimension | Description | Example High-Weight Profiles |
|---|---|---|
| evidence_coverage | Claims backed by evidence | medical.rct (25%), general.study (30%) |
| claim_accuracy | Claims accurate, not overreaching | finance (25%), legal (25%) |
| reasoning_quality | MECE, logical, gap-free | cs_ml (25%), grants (25%) |
| actionability | Reader can take action | business (25%), professional (25%) |
| uncertainty_honesty | Uncertainties flagged | medical (15%), journalism (15%) |
| structure_clarity | Scannable, well-organized | education (25%), creative (30%) |
| counterargument_depth | Opposing views substantive | creative (30%), general.comparison (10%) |

## Benchmark Levels

| Level | Check | Pass Criteria |
|---|---|---|
| **L1** | Structure | All required sections present |
| **L2** | Evidence | Claims linked to sources (✅/⚠️/🚫) |
| **L3** | PQS | Score ≥ profile's pass_threshold |
