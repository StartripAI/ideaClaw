"""Production-grade LLM hooks for the orchestrator loop.

Wires LLMClient (BYOK: OpenAI, Anthropic, DeepSeek, Groq, Together, custom)
into the orchestrator's hook protocols.

Architecture mapping (AR → IdeaClaw):
    program.md   → scenario YAML + optional program.md override → INPUT
    train.py     → draft document being iterated              → ARTIFACT
    train.md     → experiment log (auto-generated)            → LOG
    val_bpb      → composite score from evaluator             → SIGNAL
    final output → accepted document + reports                → OUTPUT

Input/Output contract:
    INPUT:  idea (str) + scenario profile (YAML) + [program.md] + [style_guide.md]
    OUTPUT: final document (.md) + train.md (log) + evolution report + state.json
"""

from __future__ import annotations

import json
import logging
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = ["UsageStats", "build_system_prompt", "build_user_prompt", "build_judge_prompt", "LLMHooks", "create_hooks"]


# ---------------------------------------------------------------------------
# Token / Cost tracking
# ---------------------------------------------------------------------------

@dataclass
class UsageStats:
    """Track LLM usage across the entire loop run."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    total_cost_usd: float = 0.0
    errors: int = 0
    retries: int = 0
    call_log: List[Dict[str, Any]] = field(default_factory=list)

    # Rough cost estimates per 1M tokens (input/output)
    COST_TABLE: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "claude-sonnet-4-20250514": (3.00, 15.00),
        "claude-haiku-4-20250514": (0.80, 4.00),
        "deepseek-chat": (0.14, 0.28),
        "deepseek-reasoner": (0.55, 2.19),
    })

    def record(self, model: str, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1
        costs = self.COST_TABLE.get(model, (1.0, 3.0))
        cost = (input_tokens * costs[0] + output_tokens * costs[1]) / 1_000_000
        self.total_cost_usd += cost
        self.call_log.append({
            "model": model, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "cost_usd": round(cost, 6),
        })

    def summary(self) -> str:
        return (
            f"LLM Usage: {self.total_calls} calls, "
            f"{self.total_input_tokens:,} in / {self.total_output_tokens:,} out tokens, "
            f"${self.total_cost_usd:.4f} est. cost, "
            f"{self.errors} errors, {self.retries} retries"
        )


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_system_prompt(profile: Any, program_md: str = "", style_guide: str = "") -> str:
    """Build the system prompt from profile + optional overrides.

    This is the equivalent of AR's program.md — it tells the LLM:
    - What to produce
    - What structure to follow
    - What style to use
    - What quality standards to meet
    """
    objective = program_md.strip() if program_md else getattr(profile, "objective", "")

    # Sections
    sections = ""
    if hasattr(profile, "style") and profile.style.required_sections:
        sections = "\n".join(f"  {i+1}. {s.title()}" for i, s in enumerate(profile.style.required_sections))

    # Style
    formality = getattr(profile.style, "formality", 0.8) if hasattr(profile, "style") else 0.8
    voice = getattr(profile.style, "voice", "third_person") if hasattr(profile, "style") else "third_person"
    cite_style = getattr(profile.style, "citation_style", "natbib") if hasattr(profile, "style") else "natbib"

    tone = "professional"
    if formality < 0.3: tone = "casual, conversational"
    elif formality < 0.6: tone = "professional but approachable"
    elif formality < 0.8: tone = "formal, professional"
    else: tone = "highly formal, academic"

    voice_map = {"first_person": "first person (I/we)", "third_person": "third person",
                 "second_person": "second person (you)", "mixed": "mixed voice"}
    voice_desc = voice_map.get(voice, voice)

    # Evaluation criteria as quality targets
    criteria_text = ""
    if hasattr(profile, "criteria") and profile.criteria:
        criteria_text = "QUALITY TARGETS:\n" + "\n".join(
            f"  - {c.name}: weight {c.weight:.0%}, minimum {c.min_score:.0%}"
            for c in profile.criteria
        )

    # Style guide override
    style_section = ""
    if style_guide:
        style_section = f"\nADDITIONAL STYLE GUIDE:\n{style_guide[:2000]}\n"

    return textwrap.dedent(f"""\
        You are an expert writer producing a {profile.display_name}.

        OBJECTIVE:
        {objective or f"Produce a high-quality {profile.display_name}."}

        REQUIRED STRUCTURE:
        {sections or "Use appropriate sections for this document type."}

        STYLE:
        - Tone: {tone}
        - Voice: {voice_desc}
        - Citation style: {cite_style}
        - Category: {getattr(profile, 'category', 'general')}

        {criteria_text}
        {style_section}
        RULES:
        - Write the COMPLETE document, not an outline or summary.
        - Include real citations referencing the provided sources where relevant.
        - Be specific, detailed, and substantive — match the quality expected for {profile.display_name}.
        - Output in markdown format.
    """).strip()


def build_user_prompt(
    sources: List[Any],
    previous_draft: Optional[str],
    feedback: str,
    idea: str = "",
) -> str:
    """Build the user prompt with sources, previous draft, and feedback."""
    parts = []

    if idea:
        parts.append(f"TOPIC/IDEA:\n{idea}")

    # Format sources
    if sources:
        refs = []
        for i, src in enumerate(sources[:20], 1):
            if isinstance(src, dict):
                title = src.get("title", "Untitled")
                year = src.get("year", "")
                abstract = (src.get("abstract", "") or "")[:300]
                ref = f"[{i}] {title} ({year})"
                if abstract:
                    ref += f"\n    {abstract}"
                refs.append(ref)
            else:
                refs.append(f"[{i}] {src}")
        parts.append(f"REFERENCE SOURCES:\n" + "\n".join(refs))

    if previous_draft and feedback:
        # Iterative improvement mode
        parts.append(f"PREVIOUS DRAFT:\n{previous_draft[:4000]}")
        parts.append(f"REVIEWER FEEDBACK (address these issues):\n{feedback}")
        parts.append("Rewrite the document, keeping what works and improving the weak areas.")
    elif previous_draft:
        parts.append(f"PREVIOUS DRAFT (improve it):\n{previous_draft[:4000]}")
        parts.append("Improve this draft's quality, depth, and completeness.")
    else:
        parts.append("Write the complete document now.")

    return "\n\n".join(parts)


def build_judge_prompt(profile: Any, draft: str, criteria_names: List[str]) -> Tuple[str, str]:
    """Build LLM-as-judge prompt for subjective evaluation."""
    criteria_desc = "\n".join(f"  - {name}: 0.0 (poor) to 1.0 (excellent)" for name in criteria_names)

    system_prompt = textwrap.dedent(f"""\
        You are a strict, expert reviewer evaluating a {profile.display_name}.
        Rate the document on each criterion:
        {criteria_desc}

        Scoring guide:
        - 0.0-0.3: Major deficiencies, unpublishable
        - 0.3-0.5: Below average, needs significant revision
        - 0.5-0.7: Adequate, meets minimum standards
        - 0.7-0.85: Good, above average quality
        - 0.85-1.0: Excellent, top-tier quality

        Return ONLY a JSON object: {{"criterion": score, ...}}
        Be critical and honest. Do not inflate scores.
    """).strip()

    user_prompt = f"DOCUMENT TO EVALUATE:\n\n{draft[:6000]}"
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# LLMHooks — production implementation
# ---------------------------------------------------------------------------

class LLMHooks:
    """Production LLM hooks for the orchestrator loop.

    Provides default implementations for all hook protocols:
    - search()   → source module (with graceful fallback)
    - generate() → LLM content generation (with retry)
    - evaluate() → hybrid heuristic + LLM-as-judge
    - learn()    → train.md experiment log

    Input/Output contract:
        INPUT:  idea + profile YAML + [program.md] + [style_guide.md]
        OUTPUT: draft text (str) per iteration → loop saves to disk

    AR integration:
        - program.md in CWD → overrides profile.objective
        - style_guide.md in CWD → appended to system prompt
        - train.md in CWD → auto-updated with experiment log
    """

    # Dimensions that require LLM judgment (can't be computed heuristically)
    LLM_JUDGE_DIMS = {"novelty", "significance", "soundness", "ethics"}

    # Max retries for LLM calls
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # seconds
    DEFAULT_BUDGET_USD = 10.0  # max cost per run
    MAX_SINGLE_CALL_USD = 2.0  # max estimated cost per single LLM call

    class BudgetExceededError(RuntimeError):
        """Raised when LLM cost budget is exceeded."""
        pass

    def __init__(
        self,
        config: Any = None,
        idea: str = "",
        program_md_path: Optional[Path] = None,
        style_guide_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        llm_callable: Optional[Any] = None,
    ):
        """Initialize with config and optional AR-style overrides.

        Supports two modes:
        1. BYOK mode: Pass config with llm.api_key → uses LLMClient
        2. IDE-native mode: Pass llm_callable → IDE provides LLM directly

        Args:
            config: IdeaClawConfig or dict with 'llm' key. Optional if llm_callable provided.
            idea: The user's idea/topic (main input).
            program_md_path: Path to program.md override.
            style_guide_path: Path to style_guide.md.
            output_dir: Where to write train.md and other logs.
            llm_callable: IDE-native LLM function(system_prompt, user_prompt, **kwargs) -> str.
                          When set, LLMClient is not needed — the IDE IS the LLM.
        """
        from ideaclaw.orchestrator.evaluator import UnifiedEvaluator

        self._ide_mode = llm_callable is not None
        self._llm_callable = llm_callable
        self.llm = None

        if not self._ide_mode:
            # BYOK mode: create LLMClient from config
            from ideaclaw.llm.client import LLMClient
            if hasattr(config, "llm"):
                from dataclasses import asdict
                llm_cfg = asdict(config.llm) if hasattr(config.llm, "__dataclass_fields__") else config.llm
            elif isinstance(config, dict):
                llm_cfg = config.get("llm", {})
            else:
                llm_cfg = {}
            self.llm = LLMClient(llm_cfg)

        self.evaluator = UnifiedEvaluator()
        self.usage = UsageStats()
        self.idea = idea
        self.output_dir = output_dir

        # Load AR-style markdown overrides
        self._program_md = self._load_md(program_md_path, "program.md")
        self._style_guide = self._load_md(style_guide_path, "style_guide.md")

        # Cache the system prompt per profile (avoid rebuilding every call)
        self._system_prompt_cache: Dict[str, str] = {}

    def _load_md(self, explicit_path: Optional[Path], filename: str) -> str:
        """Load an optional markdown file: explicit path → CWD fallback."""
        if explicit_path and explicit_path.exists():
            logger.info("Loaded %s from %s", filename, explicit_path)
            return explicit_path.read_text(encoding="utf-8")
        cwd_path = Path(filename)
        if cwd_path.exists():
            logger.info("Loaded %s from CWD", filename)
            return cwd_path.read_text(encoding="utf-8")
        return ""

    def _get_system_prompt(self, profile: Any) -> str:
        """Get (cached) system prompt for a profile."""
        pid = getattr(profile, "scenario_id", id(profile))
        if pid not in self._system_prompt_cache:
            self._system_prompt_cache[pid] = build_system_prompt(
                profile, self._program_md, self._style_guide,
            )
        return self._system_prompt_cache[pid]

    def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        purpose: str = "generate",
        budget_usd: Optional[float] = None,
    ) -> str:
        """Call LLM with retry logic, usage tracking, and budget enforcement.

        Supports two modes:
        1. IDE-native: routes through self._llm_callable (IDE is the LLM)
        2. BYOK: routes through self.llm (LLMClient with API key)

        Raises:
            BudgetExceededError: If cumulative cost exceeds budget_usd.
        """
        # Budget enforcement
        budget = budget_usd or self.DEFAULT_BUDGET_USD
        if self.usage.total_cost_usd >= budget:
            raise self.BudgetExceededError(
                f"Budget exceeded: ${self.usage.total_cost_usd:.4f} >= ${budget:.2f} "
                f"after {self.usage.total_calls} calls"
            )
        # Single-call limit (prevent anomalous large requests)
        estimated_cost = max_tokens * 0.00006  # rough upper bound
        if estimated_cost > self.MAX_SINGLE_CALL_USD:
            logger.warning("Single call estimate $%.2f exceeds limit $%.2f — capping tokens",
                           estimated_cost, self.MAX_SINGLE_CALL_USD)
            max_tokens = int(self.MAX_SINGLE_CALL_USD / 0.00006)
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                if self._ide_mode:
                    # IDE-native mode: call IDE's LLM directly
                    result = self._llm_callable(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        json_mode=json_mode,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    model_name = "ide-native"
                else:
                    # BYOK mode: call LLMClient
                    result = self.llm.chat_with_fallback(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        json_mode=json_mode,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    model_name = self.llm.primary_model

                # Track usage
                in_tokens = (len(system_prompt) + len(user_prompt)) // 4
                out_tokens = len(result) // 4
                self.usage.record(model_name, in_tokens, out_tokens)
                logger.debug("%s: %d in / %d out tokens (attempt %d)",
                             purpose, in_tokens, out_tokens, attempt + 1)
                return result

            except Exception as e:
                last_error = e
                self.usage.errors += 1
                if attempt < self.MAX_RETRIES - 1:
                    self.usage.retries += 1
                    delay = self.RETRY_DELAY * (2 ** attempt)
                    logger.warning("%s attempt %d failed: %s (retry in %.0fs)",
                                   purpose, attempt + 1, e, delay)
                    time.sleep(delay)

        raise RuntimeError(f"{purpose} failed after {self.MAX_RETRIES} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Hook implementations (match Protocol signatures in loop.py)
    # ------------------------------------------------------------------

    def search(self, profile: Any, context: Dict[str, Any]) -> List[Any]:
        """Search for reference sources.

        Uses the source/collector module. Falls back gracefully if unavailable.
        """
        try:
            from ideaclaw.source.collector import collect_sources
            query = self.idea or getattr(profile, "objective", "") or profile.display_name
            results = collect_sources(
                query=query,
                engines=profile.search.apis if hasattr(profile, "search") else ["arxiv"],
                limit=getattr(profile.search, "max_sources", 20) if hasattr(profile, "search") else 20,
            )
            logger.info("Search: %d sources for '%s'", len(results), query[:60])
            return results
        except ImportError:
            logger.info("Source module unavailable — continuing without external sources")
            return []
        except Exception as e:
            logger.warning("Search error: %s — continuing without sources", e)
            return []

    def _validate_structure(self, content: str, profile: Any) -> Tuple[bool, str]:
        """Validate if the generated content structurally satisfies the profile.
        
        This prevents silent truncation or ignored sections from passing to PackBuilder.
        """
        if not hasattr(profile, "style") or not profile.style.required_sections:
            return True, ""
            
        missing_sections = []
        content_lower = content.lower()
        for sec in profile.style.required_sections:
            # Check if the section name appears as a Markdown header
            sec_clean = sec.strip().lower()
            # Simple check: does the string loosely exist near header markers?
            if sec_clean not in content_lower:
                missing_sections.append(sec)
                
        if missing_sections:
            return False, f"CRITICAL STRUCTURAL ERROR: The generated draft is missing the following mandatory sections: {', '.join(missing_sections)}. You MUST include these exact section headers in your output."
            
        # Check for obvious truncation (ends without punctuation or ends mid-markdown)
        valid_endings = (
            # English punctuation
            ".", "!", "?", 
            # Asian/Multilingual punctuation
            "。", "！", "？", "”", "’", "》", "】",
            # Markdown/Code closers
            "```", ">", "*", "_", "]", ")", "}"
        )
        if not content.strip().endswith(valid_endings):
            return False, "CRITICAL ERROR: The output appears severely truncated and ends mid-sentence. You must generate the complete document to the very end."
            
        return True, ""

    def generate(
        self,
        profile: Any,
        sources: List[Any],
        previous_draft: Optional[str],
        feedback: str,
    ) -> str:
        """Generate document content using LLM with Self-Healing Structural Retries.

        INPUT:  profile + sources + previous_draft + feedback
        OUTPUT: complete document text (markdown)
        """
        system_prompt = self._get_system_prompt(profile)
        base_user_prompt = build_user_prompt(sources, previous_draft, feedback, self.idea)

        max_self_healing_retries = 3
        current_prompt = base_user_prompt
        content = ""

        for attempt in range(max_self_healing_retries):
            content = self._call_llm(
                system_prompt=system_prompt,
                user_prompt=current_prompt,
                temperature=0.7 if not previous_draft else 0.5,  # Lower temp for revisions
                max_tokens=4096,
                purpose=f"generate_attempt_{attempt+1}",
            )
            
            # Self-Healing Structural Check (The IdeaClaw edge over ARC)
            is_valid, validation_error = self._validate_structure(content, profile)
            if is_valid:
                logger.info("Generated %d chars, structure looks solid.", len(content))
                break
                
            logger.warning("Generation structural failure on attempt %d: %s", attempt+1, validation_error)
            # Feed the error back to the LLM for immediate self-correction
            current_prompt = (
                f"{base_user_prompt}\n\n"
                f"--- YOUR LAST OUTPUT FAILED VALIDATION ---\n"
                f"Error: {validation_error}\n"
                f"Previous Output snippet: {content[-500:]}\n\n"
                f"Please completely rewrite the document and carefully ensure ALL sections are present and the text is not truncated."
            )
        else:
            logger.warning("Failing gracefully after %d structure retries.", max_self_healing_retries)

        return content

    def evaluate(
        self,
        profile: Any,
        draft: str,
        sources: List[Any],
    ) -> Dict[str, float]:
        """Hybrid evaluation: heuristic + LLM-as-judge.

        Delegates to _heuristic_eval() for free instant scoring,
        then _llm_judge() for subjective dimensions that need LLM.
        """
        scores = self._heuristic_eval(profile, draft, sources)
        scores = self._llm_judge(profile, draft, scores)
        return scores

    def _heuristic_eval(
        self, profile: Any, draft: str, sources: List[Any],
    ) -> Dict[str, float]:
        """Free, instant heuristic scoring: structure, citations, style, depth."""
        return self.evaluator.evaluate(profile, draft, sources)

    def _llm_judge(
        self, profile: Any, draft: str, scores: Dict[str, float],
    ) -> Dict[str, float]:
        """LLM-as-judge for subjective dimensions (novelty, significance, etc).

        Includes JSON schema validation: only known dimension names
        with float values in [0, 1] are accepted.
        """
        criteria_names = [c.name for c in profile.criteria] if hasattr(profile, "criteria") else []
        llm_dims = [n for n in criteria_names if n in self.LLM_JUDGE_DIMS]

        if not llm_dims or not draft.strip():
            return scores

        try:
            sys_prompt, user_prompt = build_judge_prompt(profile, draft, llm_dims)
            raw = self._call_llm(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.1,
                max_tokens=256,
                purpose="evaluate",
            )
            llm_scores = json.loads(raw)

            # Schema validation: only accept known dims with float 0-1 values
            if not isinstance(llm_scores, dict):
                logger.warning("LLM judge returned non-dict: %s", type(llm_scores).__name__)
                return scores

            for dim in llm_dims:
                if dim in llm_scores:
                    val = llm_scores[dim]
                    if isinstance(val, (int, float)) and 0.0 <= float(val) <= 1.0:
                        scores[dim] = round(float(val), 4)
                    else:
                        logger.warning("LLM judge dim '%s' invalid value: %s", dim, val)

        except json.JSONDecodeError as e:
            logger.warning("Judge returned invalid JSON: %s", e)
        except self.BudgetExceededError:
            logger.info("Budget exceeded — skipping LLM judge, keeping heuristic scores")
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM judge failed (keeping heuristic): %s", e)

        return scores

    def learn(
        self,
        profile: Any,
        draft: str,
        scores: Dict[str, float],
        failure_reason: str,
    ) -> None:
        """Update train.md experiment log.

        AR pattern: each iteration records what happened, what failed,
        and what to try next. This creates a persistent experiment log
        that the user can review.
        """
        import datetime as dt

        timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scores_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(scores.items()))

        entry = (
            f"\n### {timestamp} — {profile.display_name}\n"
            f"- **Scores**: {scores_str}\n"
            f"- **Draft**: {len(draft)} chars, {draft.count(chr(10))} lines\n"
        )
        if failure_reason:
            entry += f"- **REVERTED**: {failure_reason}\n"
        entry += f"- **Usage**: {self.usage.summary()}\n"

        # Write to output_dir/train.md or CWD/train.md
        train_path = (self.output_dir / "train.md") if self.output_dir else Path("train.md")
        try:
            existing = train_path.read_text(encoding="utf-8") if train_path.exists() else "# Experiment Log\n"
            train_path.write_text(existing + entry, encoding="utf-8")
        except OSError as e:
            logger.warning("Could not write train.md: %s", e)

    # ------------------------------------------------------------------
    # Output finalization
    # ------------------------------------------------------------------

    def finalize_output(
        self,
        profile: Any,
        state: Any,
        run_dir: Path,
    ) -> Dict[str, Path]:
        """Save all final outputs after loop completes.

        OUTPUT files:
        - output.md        → the final accepted document
        - train.md         → experiment log (AR pattern)
        - evolution.md     → score progression report
        - state.json       → full loop state
        - usage.json       → LLM token/cost tracking

        Returns dict of output_name → file_path.
        """
        outputs: Dict[str, Path] = {}
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. Final document
        if state.current_draft:
            out_path = run_dir / "output.md"
            out_path.write_text(state.current_draft, encoding="utf-8")
            outputs["document"] = out_path
            logger.info("Saved final document: %s (%d chars)", out_path, len(state.current_draft))

        # 2. Train.md (copy from output_dir if exists)
        train_src = (self.output_dir / "train.md") if self.output_dir else Path("train.md")
        if train_src.exists():
            train_dst = run_dir / "train.md"
            if train_src != train_dst:
                train_dst.write_text(train_src.read_text(encoding="utf-8"), encoding="utf-8")
            outputs["train_log"] = train_dst

        # 3. Usage stats
        usage_path = run_dir / "usage.json"
        usage_data = {
            "total_calls": self.usage.total_calls,
            "total_input_tokens": self.usage.total_input_tokens,
            "total_output_tokens": self.usage.total_output_tokens,
            "total_cost_usd": round(self.usage.total_cost_usd, 6),
            "errors": self.usage.errors,
            "retries": self.usage.retries,
            "call_log": self.usage.call_log,
        }
        usage_path.write_text(json.dumps(usage_data, indent=2), encoding="utf-8")
        outputs["usage"] = usage_path

        # 4. Summary
        summary_path = run_dir / "summary.md"
        summary = self._build_summary(profile, state)
        summary_path.write_text(summary, encoding="utf-8")
        outputs["summary"] = summary_path

        return outputs

    def _build_summary(self, profile: Any, state: Any) -> str:
        """Build a human-readable summary of the run."""
        lines = [
            f"# {profile.display_name} — Run Summary",
            "",
            f"**Status**: {state.status}",
            f"**Best Score**: {state.best_score:.3f} (iteration {state.best_iteration})",
            f"**Iterations**: {state.iteration_count}",
            f"**Elapsed**: {state.total_elapsed:.1f}s",
            f"**{self.usage.summary()}**",
            "",
            "## Iteration History",
            "",
            "| # | Score | Status | Key Scores |",
            "|---|---|---|---|",
        ]
        for r in getattr(state, "iterations", []):
            status = "✅ Accept" if r.accepted else "❌ Revert"
            detail = ", ".join(f"{k}={v:.2f}" for k, v in sorted(r.scores_detail.items())[:4])
            lines.append(f"| {r.iteration} | {r.score:.3f} | {status} | {detail} |")

        if state.current_draft:
            lines.extend([
                "",
                f"## Output Preview",
                "",
                f"```",
                state.current_draft[:500] + ("..." if len(state.current_draft) > 500 else ""),
                f"```",
            ])

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_hooks(
    config: Any,
    idea: str = "",
    program_md: Optional[Path] = None,
    style_guide: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> LLMHooks:
    """Create production LLMHooks. Convenience factory."""
    return LLMHooks(
        config=config,
        idea=idea,
        program_md_path=program_md,
        style_guide_path=style_guide,
        output_dir=output_dir,
    )
