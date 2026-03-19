"""ARC (AI-Scientist) — full port into IdeaClaw.

This package contains 1:1 ports of every AI-Scientist module,
adapted to work with IdeaClaw's LLMClient and SandboxExecutor.

Modules:
  - llm: Multi-model LLM interface (OpenAI, Anthropic, Gemini, DeepSeek)
  - generate_ideas: Idea generation + novelty checking via S2
  - perform_experiments: Experiment loop (Aider coder → sandbox)
  - perform_writeup: Per-section LaTeX writing + citation loop + refinement
  - perform_review: NeurIPS review + ensemble + meta-review
  - launch: Full orchestrator (generate → experiment → writeup → review)
"""
