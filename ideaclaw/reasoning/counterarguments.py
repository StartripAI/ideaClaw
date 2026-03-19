"""Counterargument generator — systematic identification of opposing viewpoints.

Integrates with:
  - reasoning.debate → feeds counter-arguments into the debate system
  - orchestrator.loop → used in the evidence verification phase
  - prompts.generation → uses domain context for targeted counter-args

Features:
  - Steelman/strawman argument generation
  - Evidence-linked counterarguments
  - Strength scoring per argument
  - Rebuttal generation
  - Domain-aware counter-argument patterns

Usage:
    from ideaclaw.reasoning.counterarguments import CounterArgGenerator
    gen = CounterArgGenerator()
    result = gen.generate(claim, evidence, domain="cs_ml")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["CounterArgGenerator", "CounterArgument", "CounterArgResult"]


@dataclass
class CounterArgument:
    """A single counterargument."""
    argument: str
    strength: str = "medium"      # strong|medium|weak
    type: str = "challenge"       # challenge|alternative|limitation|caveat
    evidence: str = ""            # Supporting evidence for the counter-arg
    rebuttal: str = ""            # Possible rebuttal to the counter-arg
    source: str = ""


@dataclass
class CounterArgResult:
    """Complete counter-argument analysis."""
    claim: str
    counterarguments: List[CounterArgument] = field(default_factory=list)
    steelman: str = ""            # Strongest version of the original claim
    strawman_warning: str = ""    # Warning if claim appears strawmanned
    overall_resilience: float = 0.0  # How well the claim survives counter-args

    def strong_args(self) -> List[CounterArgument]:
        """Get only strong counterarguments."""
        return [ca for ca in self.counterarguments if ca.strength == "strong"]


# Domain-specific challenge patterns
DOMAIN_CHALLENGES: Dict[str, List[Dict[str, str]]] = {
    "cs_ml": [
        {"type": "alternative", "template": "A simpler baseline (e.g., {baseline}) might achieve comparable results with less complexity."},
        {"type": "limitation", "template": "The evaluation only covers {scope} — results may not generalize to {broader_scope}."},
        {"type": "challenge", "template": "The improvement over SOTA is within the margin of error / variance across random seeds."},
        {"type": "caveat", "template": "The computational cost ({cost}) may make this impractical for most researchers."},
        {"type": "challenge", "template": "The claimed novelty overlaps significantly with {related_work}."},
    ],
    "medical": [
        {"type": "limitation", "template": "The sample size (N={n}) may be insufficient for detecting clinically meaningful effects."},
        {"type": "challenge", "template": "Selection bias: the study population may not represent the target clinical population."},
        {"type": "caveat", "template": "The follow-up period ({period}) may be too short to assess long-term safety."},
        {"type": "alternative", "template": "Existing treatment {treatment} has a better risk-benefit profile."},
    ],
    "business": [
        {"type": "challenge", "template": "The market size estimate ({tam}) may be inflated — verify bottom-up."},
        {"type": "limitation", "template": "The analysis assumes {assumption}, which may not hold in a recession/expansion."},
        {"type": "alternative", "template": "Competitors ({competitors}) have first-mover advantage and switching costs."},
        {"type": "caveat", "template": "Regulatory changes in {area} could invalidate the business model."},
    ],
    "general": [
        {"type": "challenge", "template": "The core assumption — that {assumption} — is not well-supported."},
        {"type": "alternative", "template": "An alternative explanation is {alternative}, which hasn't been ruled out."},
        {"type": "limitation", "template": "This analysis doesn't account for {missing_factor}."},
        {"type": "caveat", "template": "The conclusion relies on {dependency}, which may change."},
    ],
}


class CounterArgGenerator:
    """Generate structured counterarguments for claims."""

    def __init__(self, llm_callable: Optional[Callable[[str], str]] = None):
        self.llm = llm_callable

    def generate(
        self,
        claim: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
        domain: str = "general",
        n_args: int = 5,
    ) -> CounterArgResult:
        """Generate counterarguments for a claim.

        Args:
            claim: The claim to challenge.
            evidence: Optional evidence supporting the claim.
            domain: Domain for targeted challenges.
            n_args: Number of counterarguments to generate.

        Returns:
            CounterArgResult with ranked counterarguments.
        """
        if self.llm:
            counter_args = self._llm_generate(claim, evidence or [], domain, n_args)
        else:
            counter_args = self._heuristic_generate(claim, domain, n_args)

        # Steelman the original claim
        steelman = self._build_steelman(claim)

        # Compute resilience
        n_strong = sum(1 for ca in counter_args if ca.strength == "strong")
        resilience = 1.0 - (n_strong / max(len(counter_args), 1))

        result = CounterArgResult(
            claim=claim,
            counterarguments=counter_args[:n_args],
            steelman=steelman,
            overall_resilience=resilience,
        )

        logger.info(
            "Generated %d counter-args for claim, resilience=%.2f",
            len(counter_args), resilience,
        )
        return result

    def generate_rebuttals(
        self, claim: str, counter_args: List[CounterArgument],
    ) -> List[CounterArgument]:
        """Generate rebuttals for each counterargument."""
        for ca in counter_args:
            if self.llm:
                rebuttal_prompt = (
                    f"Original claim: {claim}\n"
                    f"Counterargument: {ca.argument}\n"
                    f"Generate a concise rebuttal that defends the original claim."
                )
                try:
                    ca.rebuttal = self.llm(rebuttal_prompt)
                except Exception:  # noqa: BLE001
                    ca.rebuttal = self._heuristic_rebuttal(ca)
            else:
                ca.rebuttal = self._heuristic_rebuttal(ca)
        return counter_args

    def _llm_generate(
        self, claim: str, evidence: List[Dict[str, Any]],
        domain: str, n_args: int,
    ) -> List[CounterArgument]:
        """Use LLM for counter-argument generation."""
        evidence_str = "\n".join(
            f"- {e.get('claim', '')} ({e.get('source', 'unknown')})"
            for e in evidence[:10]
        )

        prompt = f"""Generate {n_args} counterarguments against the following claim.
Domain: {domain}

CLAIM: {claim}

SUPPORTING EVIDENCE:
{evidence_str or "(none provided)"}

For each counterargument, classify:
- Type: challenge|alternative|limitation|caveat
- Strength: strong|medium|weak
- Evidence: what supports this counter-argument

Format as numbered list:
1. [TYPE: xxx] [STRENGTH: xxx] Argument text. EVIDENCE: supporting evidence.
"""
        try:
            response = self.llm(prompt)
            return self._parse_llm_response(response)
        except Exception as e:
            logger.warning("LLM counter-arg generation failed: %s", e)
            return self._heuristic_generate(claim, domain, n_args)

    def _heuristic_generate(
        self, claim: str, domain: str, n_args: int,
    ) -> List[CounterArgument]:
        """Generate counterarguments using patterns."""
        templates = DOMAIN_CHALLENGES.get(domain, DOMAIN_CHALLENGES["general"])
        args = []

        # Apply domain templates
        for tmpl in templates[:n_args]:
            arg_text = tmpl["template"]
            # Fill in generic placeholders
            arg_text = arg_text.replace("{baseline}", "a linear model or random baseline")
            arg_text = arg_text.replace("{scope}", "the tested benchmarks")
            arg_text = arg_text.replace("{broader_scope}", "real-world deployment")
            arg_text = arg_text.replace("{cost}", "high GPU hours")
            arg_text = arg_text.replace("{related_work}", "recent concurrent work")
            arg_text = arg_text.replace("{n}", "?")
            arg_text = arg_text.replace("{period}", "the study period")
            arg_text = arg_text.replace("{treatment}", "standard care")
            arg_text = arg_text.replace("{tam}", "the claimed TAM")
            arg_text = arg_text.replace("{assumption}", "the stated assumption")
            arg_text = arg_text.replace("{competitors}", "existing competitors")
            arg_text = arg_text.replace("{area}", "the relevant sector")
            arg_text = arg_text.replace("{alternative}", "an alternative interpretation")
            arg_text = arg_text.replace("{missing_factor}", "important confounding factors")
            arg_text = arg_text.replace("{dependency}", "external dependencies")

            args.append(CounterArgument(
                argument=arg_text,
                type=tmpl["type"],
                strength="medium",
            ))

        # Generic counterarguments
        if len(args) < n_args:
            args.append(CounterArgument(
                argument=f"The claim '{claim[:60]}...' may suffer from confirmation bias in evidence selection.",
                type="challenge", strength="medium",
            ))
        if len(args) < n_args:
            args.append(CounterArgument(
                argument="The generalizability of these findings is unclear without replication.",
                type="limitation", strength="medium",
            ))

        return args[:n_args]

    @staticmethod
    def _parse_llm_response(response: str) -> List[CounterArgument]:
        """Parse LLM response into CounterArgument objects."""
        args = []
        for line in response.strip().split("\n"):
            cleaned = re.sub(r"^\s*\d+[\.)\]]\s*", "", line).strip()
            if not cleaned or len(cleaned) < 15:
                continue

            # Extract type and strength
            ca_type = "challenge"
            strength = "medium"
            type_m = re.search(r"\[TYPE:\s*(\w+)\]", cleaned, re.I)
            str_m = re.search(r"\[STRENGTH:\s*(\w+)\]", cleaned, re.I)
            if type_m:
                ca_type = type_m.group(1).lower()
            if str_m:
                strength = str_m.group(1).lower()

            # Clean text
            text = re.sub(r"\[TYPE:\s*\w+\]\s*", "", cleaned)
            text = re.sub(r"\[STRENGTH:\s*\w+\]\s*", "", text).strip()

            # Extract evidence
            evidence = ""
            ev_m = re.search(r"EVIDENCE:\s*(.+)$", text, re.I)
            if ev_m:
                evidence = ev_m.group(1).strip()
                text = text[:ev_m.start()].strip()

            if text:
                args.append(CounterArgument(
                    argument=text, type=ca_type,
                    strength=strength, evidence=evidence,
                ))

        return args

    @staticmethod
    def _build_steelman(claim: str) -> str:
        """Build the strongest version of the claim."""
        return (
            f"The strongest interpretation of this claim is: {claim.strip()}. "
            f"Assuming all supporting evidence is valid and the methodology is sound, "
            f"this represents a meaningful contribution because it addresses "
            f"a genuine need in the field."
        )

    @staticmethod
    def _heuristic_rebuttal(ca: CounterArgument) -> str:
        """Generate a heuristic rebuttal."""
        rebuttals = {
            "challenge": "While this challenge is valid, the evidence presented addresses it by...",
            "alternative": "This alternative has been considered; however, our approach offers advantages in...",
            "limitation": "This limitation is acknowledged; future work will extend to...",
            "caveat": "This caveat is noted; however, the core contribution remains valid because...",
        }
        return rebuttals.get(ca.type, "This point deserves further investigation.")
