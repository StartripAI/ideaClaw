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
git clone https://github.com/startripai/ideaClaw.git
cd ideaClaw
# Claude Code auto-reads .claude/skills/ — just prompt:
# "Build a pack for: Should I switch from React to Vue?"
```

### Quick Start: Any AI Agent

```bash
git clone https://github.com/startripai/ideaClaw.git
cd ideaClaw
# Point your agent to CLAUDE.md or AGENTS.md and prompt away
```

### Quick Start: Standalone CLI (BYOK)

```bash
git clone https://github.com/startripai/ideaClaw.git
cd ideaClaw
pip install -e .
export OPENAI_API_KEY="sk-..."
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
- ✅ **Shareable document** — Markdown / DOCX / PDF

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

## 🔌 BYOK CLI Reference

```bash
# Run with auto-approve
ideaclaw run --idea "Compare React vs Vue" --pack-type comparison --auto-approve

# Resume from checkpoint
ideaclaw resume --run-id ic-20260318-091500-abc123

# With custom config
ideaclaw run --config config.ideaclaw.yaml --idea "Your idea"
```

See [config.ideaclaw.example.yaml](config.ideaclaw.example.yaml) for full configuration.

## 🙏 Acknowledgments

Inspired by:

- 🔬 [AutoResearchClaw](https://github.com/aiming-lab/AutoResearchClaw) (aiming-lab) — Pipeline architecture & agent skill pattern
- 🧠 [autoresearch](https://github.com/karpathy/autoresearch) (Karpathy) — Minimalist agent philosophy
- 📝 [OpenRevise](https://github.com/StartripAI/OpenRevise) (StartripAI) — Evidence gate engine

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
