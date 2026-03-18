# 🦞 IdeaClaw

**Turn a rough idea into a usable, verifiable pack.**

One idea. One pack. Every claim backed by evidence.

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## ⚡ One Prompt. One Pack.

Open this repo in your favorite AI coding tool, then say:

```
Build a pack for: "Should I invest in a coffee shop franchise?"
```

That's it. The agent reads the skill, executes 15 pipeline stages, and delivers a complete, evidence-backed pack.

## 🧩 Works With Your IDE

IdeaClaw is **agent-first** — it runs inside AI coding tools as a skill. No API key needed. The IDE's built-in LLM is the execution engine.

| IDE | Entry Point | How to Use |
|---|---|---|
| **Claude Code** | [`.claude/skills/ideaclaw/SKILL.md`](.claude/skills/ideaclaw/SKILL.md) | Auto-detected when you open this repo |
| **Codex (OpenAI)** | [`AGENTS.md`](AGENTS.md) | Auto-detected by Codex agents |
| **Cursor / Windsurf / Others** | [`CLAUDE.md`](CLAUDE.md) | Point the agent to this file |
| **Standalone CLI (BYOK)** | `ideaclaw run` | Bring your own LLM API key |

### Quick Start: Claude Code

```bash
git clone https://github.com/StartripAI/ideaClaw.git
cd ideaClaw
# Claude Code auto-reads .claude/skills/ — just prompt:
# "Build a pack for: Should I switch from React to Vue?"
```

### Quick Start: Standalone CLI

```bash
git clone https://github.com/StartripAI/ideaClaw.git
cd ideaClaw
pip install -e .

# Interactive login (supports OpenAI, Anthropic, DeepSeek, OpenRouter, Groq, Together)
ideaclaw login

# Or bring your own key
export OPENAI_API_KEY="sk-..."

# Run!
ideaclaw run --idea "Should I quit my job?" --auto-approve
```

## 🤔 What Is This?

You think it. IdeaClaw builds it.

Drop a rough idea — get back a complete, evidence-backed **pack** with:

- ✅ **Conclusion summary** — the bottom line, in one paragraph
- ✅ **Reasoning tree** — every claim traced to a source
- ✅ **Counterarguments** — what could go wrong
- ✅ **Uncertainties** — what we don't know yet
- ✅ **Action items** — what to do next
- ✅ **Trust review** — PQS score with 7-dimension rubric
- ✅ **Shareable document** — Markdown / DOCX / JSON

**Not just another AI writer.** IdeaClaw tells you:

- 📌 Which claims have strong evidence
- ⚠️ Which claims need your verification
- 🚫 Which claims lack sufficient evidence
- 🔍 Full audit trail — every decision is traceable

## 📦 Pack Types

| Pack | Use Case |
|---|---|
| `decision` | Should I switch jobs? Is this purchase worth it? |
| `proposal` | Startup pitch, project application, partnership proposal |
| `comparison` | Product A vs B, City X vs Y, Framework comparison |
| `brief` | Complaint letter, business memo, learning report |
| `study` | Industry analysis, trend research, market overview |

## 🎯 Quality Profiles: 15 Domains, 122 Scenarios

IdeaClaw packs aren't one-size-fits-all. Each output is evaluated against real-world standards for its domain.

**One engine × 122 YAML profiles = every scenario covered.**

```bash
# Write an ICML paper → auto-detect cs_ml.icml profile
ideaclaw run --idea "Write an ICML paper on transformer efficiency"

# Specify a medical profile
ideaclaw run --idea "Systematic review of treatment X" --profile medical.systematic_review

# List all available profiles
ideaclaw profiles
ideaclaw profiles --domain medical
```

| Domain | Profiles | Standards |
|---|---|---|
| **cs_ml** | 9 | ICML, NeurIPS, ICLR, ACL, AAAI, CVPR, KDD review forms |
| **science** | 8 | Nature, IEEE, ACM, PLOS ONE |
| **medical** | 12 | CONSORT (25 items), PRISMA (27 items), STROBE, CARE, ICH |
| **business** | 10 | McKinsey MECE + Pyramid, BCG SCQA, Amazon 6-Pager |
| **finance** | 8 | YC/Sequoia memo, CFA, GRI/SASB/TCFD |
| **education** | 10 | APA/MLA, Bloom's Taxonomy, Common App |
| **grants** | 8 | NIH 5-criteria (1-9), NSF Merit + Impacts, EU Horizon (0-5) |
| **legal** | 8 | IRAC, Bluebook, RAND policy brief |
| **professional** | 9 | Google SRE postmortem, ADR, IEEE-ISO |
| **journalism** | 6 | AP Stylebook, Pulitzer, IFCN fact-check |
| **government** | 6 | CIA ICD 203, NEPA, OECD RIA |
| **marketing** | 6 | E-E-A-T, AIDA |
| **creative** | 6 | Flesch-Kincaid, Final Draft |
| **hr_ops** | 6 | SMART goals, ADDIE |
| **general** | 10 | IdeaClaw's 5 pack types + 5 new |

### 7-Dimension Scoring Rubric (PQS)

Each pack receives a **Pack Quality Score (PQS)** from 0-10:

| Dimension | Description |
|---|---|
| Evidence Coverage | How well are claims backed by evidence? |
| Claim Accuracy | Are claims accurate and not overreaching? |
| Reasoning Quality | Is reasoning MECE, logical, and gap-free? |
| Actionability | Can the reader take immediate action? |
| Uncertainty Honesty | Are uncertainties explicitly flagged? |
| Structure & Clarity | Is the document scannable and well-organized? |
| Counterargument Depth | Are opposing viewpoints substantive? |

Dimension weights are customized per profile. E.g., `medical.rct` puts 25% weight on evidence, while `business.mckinsey_memo` puts 25% on actionability.

### Benchmark: L1 → L2 → L3

| Level | What It Checks |
|---|---|
| **L1** | Structure compliance — all required sections present |
| **L2** | Evidence traceability — claims linked to sources |
| **L3** | PQS threshold — quality score meets profile's pass mark |

```bash
# Run benchmark on existing packs
ideaclaw benchmark --dir artifacts/
```

## 🔬 Pipeline: 15 Stages, 6 Phases

```
Phase A: Idea Scoping          Phase D: Synthesis & Decision
 1. IDEA_INIT                    9. EVIDENCE_SYNTHESIS
 2. IDEA_DECOMPOSE              10. DECISION_TREE
                                11. COUNTERARGUMENT_GEN
Phase B: Source Discovery
 3. SEARCH_STRATEGY             Phase E: Pack Assembly
 4. SOURCE_COLLECT              12. PACK_OUTLINE
 5. SOURCE_SCREEN [gate]        13. PACK_DRAFT
 6. EVIDENCE_EXTRACT            14. TRUST_REVIEW [gate]

Phase C: Evidence Verification  Phase F: Export & Archive
 7. EVIDENCE_GATE [gate]        15. EXPORT_PUBLISH
 8. CLAIM_VERIFY
```

Gate stages (5, 7, 14) pause for human approval or auto-approve with `--auto-approve`.

Decision loops:
- Stage 10 → insufficient evidence → back to Stage 3 (re-search)
- Stage 14 → trust review fails → back to Stage 13 (revise draft)

## 🔌 CLI Reference

```bash
# Run with auto-detect profile
ideaclaw run --idea "Compare React vs Vue" --auto-approve

# Specify profile explicitly
ideaclaw run --idea "NIH R01 grant proposal" --profile grants.nih_r01

# Authentication
ideaclaw login                   # Interactive login (6 providers)
ideaclaw whoami                  # Show current auth status
ideaclaw logout                  # Remove stored credentials

# Quality profiles
ideaclaw profiles                # List all 122 profiles
ideaclaw profiles --domain cs_ml # Filter by domain

# Benchmark
ideaclaw benchmark --dir artifacts/

# Resume from checkpoint
ideaclaw resume --run-id ic-20260318-091500-abc123

# With custom config
ideaclaw run --config config.ideaclaw.yaml --idea "Your idea"
```

### Supported LLM Providers

| Provider | Setup |
|---|---|
| **OpenAI** | `export OPENAI_API_KEY=sk-...` or `ideaclaw login` |
| **Anthropic** | `export ANTHROPIC_API_KEY=sk-ant-...` |
| **DeepSeek** | `export DEEPSEEK_API_KEY=sk-...` |
| **OpenRouter** | `export OPENROUTER_API_KEY=sk-or-...` |
| **Groq** | `export GROQ_API_KEY=gsk_...` |
| **Together** | `export TOGETHER_API_KEY=...` |
| **Custom** | Set `base_url` in config or via `ideaclaw login` |

See [config.ideaclaw.example.yaml](config.ideaclaw.example.yaml) for full configuration.

## 📁 Project Structure

```
ideaClaw/
├── ideaclaw/
│   ├── cli.py              # CLI entry point (8 subcommands)
│   ├── config.py            # YAML config loader
│   ├── prompts.py           # Prompt engine
│   ├── pipeline/            # 15-stage pipeline runner
│   ├── llm/                 # LLM client + auth (BYOK + OAuth)
│   ├── evidence/            # Evidence extraction & verification
│   ├── quality/             # Quality profile system
│   │   ├── loader.py        # YAML inheritance + auto-detect
│   │   ├── scorer.py        # 7-dim PQS scorer
│   │   ├── reviewer.py      # Structural review
│   │   ├── benchmark.py     # L1/L2/L3 benchmark runner
│   │   └── profiles/        # 136 YAML profile files
│   │       ├── cs_ml/       # 9 profiles
│   │       ├── medical/     # 12 profiles
│   │       ├── business/    # 10 profiles
│   │       └── ...          # 12 more domains
│   ├── pack/                # Pack assembly + templates
│   │   ├── builder.py       # Jinja2 template rendering
│   │   ├── trust_review.py  # Profile-aware trust review
│   │   └── templates/       # 6 Jinja2 templates
│   ├── export/              # Markdown, DOCX, JSON export
│   └── knowledge/           # Knowledge base archiver
├── .claude/skills/          # Claude Code skill entry
├── AGENTS.md                # Codex (OpenAI) entry
├── CLAUDE.md                # Universal agent entry
└── config.ideaclaw.example.yaml
```

## 🙏 Acknowledgments

Inspired by:

- 🔬 [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) (aiming-lab) — Pipeline architecture & agent skill pattern
- 🧠 [autoresearch](https://github.com/karpathy/autoresearch) (Karpathy) — Minimalist agent philosophy
- 📝 [OpenRevise](https://github.com/StartripAI/OpenRevise) (StartripAI) — Evidence gate engine

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
