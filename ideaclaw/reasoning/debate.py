"""Multi-agent debate — structured argumentation protocol.

Implements ARC-style multi-agent debate where different "agents"
(personas/roles) argue for/against claims, critique each other,
and converge toward consensus through multiple rounds.

Design:
  - Each agent is a persona with a system prompt + role
  - Debate runs in rounds: propose → critique → rebut → vote
  - LLM calls are made through ideaclaw's unified llm/client
  - Works with any OpenAI-compatible provider (BYOK)

Protocol:
  1. PROPOSE: Each agent states their position on the claim
  2. CRITIQUE: Each agent critiques other agents' positions
  3. REBUT: Agents respond to critiques
  4. VOTE: Each agent votes SUPPORT / OPPOSE / ABSTAIN
  5. SYNTHESIZE: Moderator synthesizes final consensus
"""

from __future__ import annotations
import logging

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["AgentPersona", "DebateMessage", "DebateResult", "STANDARD_DEBATE_TEAM", "DebateOrchestrator"]


@dataclass
class AgentPersona:
    """A debate participant with a defined role and perspective."""
    name: str
    role: str  # e.g., "domain_expert", "devil_advocate", "methodologist"
    system_prompt: str
    perspective: str = ""  # brief description of their stance/bias


@dataclass
class DebateMessage:
    """A single message in the debate."""
    agent_name: str
    phase: str  # propose | critique | rebut | vote | synthesize
    round_num: int
    content: str
    vote: str = ""  # SUPPORT | OPPOSE | ABSTAIN (only for vote phase)
    confidence: float = 0.0  # 0.0 - 1.0


@dataclass
class DebateResult:
    """Final result of a multi-agent debate."""
    claim: str
    rounds: int
    messages: List[DebateMessage]
    final_verdict: str  # CONSENSUS_SUPPORT | CONSENSUS_OPPOSE | NO_CONSENSUS
    consensus_strength: float  # 0.0 - 1.0
    synthesis: str  # final synthesized position
    vote_tally: Dict[str, int] = field(default_factory=dict)


# Pre-built agent personas
STANDARD_DEBATE_TEAM = [
    AgentPersona(
        name="Domain Expert",
        role="domain_expert",
        system_prompt=(
            "You are a senior domain expert. Evaluate claims based on "
            "established knowledge, empirical evidence, and field consensus. "
            "Be precise and cite specific evidence when possible."
        ),
        perspective="Evaluates factual accuracy and domain relevance",
    ),
    AgentPersona(
        name="Devil's Advocate",
        role="devil_advocate",
        system_prompt=(
            "You are a rigorous devil's advocate. Your job is to find weaknesses, "
            "logical fallacies, missing evidence, potential biases, and unexamined "
            "assumptions. Challenge every claim constructively."
        ),
        perspective="Identifies weaknesses and counter-evidence",
    ),
    AgentPersona(
        name="Methodologist",
        role="methodologist",
        system_prompt=(
            "You are a research methodologist. Evaluate the quality of evidence, "
            "statistical rigor, experimental design, reproducibility, and "
            "generalizability of claims. Focus on HOW conclusions were reached."
        ),
        perspective="Assesses evidence quality and methodology",
    ),
    AgentPersona(
        name="Practitioner",
        role="practitioner",
        system_prompt=(
            "You are a practical implementer. Evaluate claims from a real-world "
            "applicability standpoint: feasibility, cost, scalability, risks, "
            "and unintended consequences. Focus on the 'so what' question."
        ),
        perspective="Evaluates practical applicability and risks",
    ),
]


class DebateOrchestrator:
    """Orchestrate multi-agent debates on research claims.

    Usage:
        # With LLM
        orchestrator = DebateOrchestrator(
            llm_call=my_llm_function,
            agents=STANDARD_DEBATE_TEAM,
        )
        result = orchestrator.debate("AI will replace all programmers by 2030")

        # Without LLM (heuristic mode)
        result = orchestrator.debate_heuristic("Claim text", evidence=[...])
    """

    def __init__(
        self,
        agents: Optional[List[AgentPersona]] = None,
        llm_call: Optional[Callable] = None,
        max_rounds: int = 3,
        consensus_threshold: float = 0.75,
    ):
        self.agents = agents or STANDARD_DEBATE_TEAM
        self.llm_call = llm_call
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold

    def debate(
        self,
        claim: str,
        context: str = "",
        evidence: Optional[List[Dict[str, str]]] = None,
    ) -> DebateResult:
        """Run a full multi-agent debate on a claim.

        Requires llm_call to be set. Falls back to heuristic mode if not.

        Args:
            claim: The claim to debate.
            context: Additional context for the debate.
            evidence: Optional list of evidence dicts.

        Returns:
            DebateResult with messages, votes, and consensus.
        """
        if self.llm_call is None:
            return self.debate_heuristic(claim, context, evidence)

        messages: List[DebateMessage] = []
        evidence_text = self._format_evidence(evidence) if evidence else ""

        for round_num in range(1, self.max_rounds + 1):
            # Phase 1: PROPOSE (round 1 only) or REBUT (subsequent rounds)
            phase = "propose" if round_num == 1 else "rebut"

            for agent in self.agents:
                prompt = self._build_prompt(
                    agent, claim, context, evidence_text,
                    phase, round_num, messages,
                )
                response = self.llm_call(
                    system_prompt=agent.system_prompt,
                    user_prompt=prompt,
                )
                messages.append(DebateMessage(
                    agent_name=agent.name,
                    phase=phase,
                    round_num=round_num,
                    content=response,
                ))

            # Phase 2: CRITIQUE (every round)
            for agent in self.agents:
                others = [m for m in messages
                          if m.round_num == round_num
                          and m.agent_name != agent.name]
                critique_prompt = self._build_critique_prompt(
                    agent, claim, others,
                )
                response = self.llm_call(
                    system_prompt=agent.system_prompt,
                    user_prompt=critique_prompt,
                )
                messages.append(DebateMessage(
                    agent_name=agent.name,
                    phase="critique",
                    round_num=round_num,
                    content=response,
                ))

        # Phase 3: VOTE
        vote_tally: Dict[str, int] = {"SUPPORT": 0, "OPPOSE": 0, "ABSTAIN": 0}
        for agent in self.agents:
            vote_prompt = self._build_vote_prompt(agent, claim, messages)
            response = self.llm_call(
                system_prompt=agent.system_prompt,
                user_prompt=vote_prompt,
            )
            vote = self._parse_vote(response)
            vote_tally[vote] = vote_tally.get(vote, 0) + 1
            messages.append(DebateMessage(
                agent_name=agent.name,
                phase="vote",
                round_num=self.max_rounds,
                content=response,
                vote=vote,
            ))

        # Phase 4: SYNTHESIZE
        synthesis = self._synthesize(claim, messages, vote_tally)

        # Determine consensus
        total = len(self.agents)
        support_pct = vote_tally.get("SUPPORT", 0) / total if total else 0
        oppose_pct = vote_tally.get("OPPOSE", 0) / total if total else 0

        if support_pct >= self.consensus_threshold:
            verdict = "CONSENSUS_SUPPORT"
            strength = support_pct
        elif oppose_pct >= self.consensus_threshold:
            verdict = "CONSENSUS_OPPOSE"
            strength = oppose_pct
        else:
            verdict = "NO_CONSENSUS"
            strength = max(support_pct, oppose_pct)

        return DebateResult(
            claim=claim,
            rounds=self.max_rounds,
            messages=messages,
            final_verdict=verdict,
            consensus_strength=round(strength, 3),
            synthesis=synthesis,
            vote_tally=vote_tally,
        )

    def debate_heuristic(
        self,
        claim: str,
        context: str = "",
        evidence: Optional[List[Dict[str, str]]] = None,
    ) -> DebateResult:
        """Run a heuristic debate without LLM (for testing / offline mode).

        Generates structured positions based on agent roles and keyword analysis.
        """
        messages: List[DebateMessage] = []
        evidence = evidence or []
        claim_lower = claim.lower()

        # Heuristic position generation based on role
        positions = {
            "domain_expert": self._heuristic_expert(claim_lower, evidence),
            "devil_advocate": self._heuristic_devil(claim_lower, evidence),
            "methodologist": self._heuristic_method(claim_lower, evidence),
            "practitioner": self._heuristic_practical(claim_lower, evidence),
        }

        for agent in self.agents:
            pos = positions.get(agent.role, ("Insufficient data for analysis.", "ABSTAIN"))
            messages.append(DebateMessage(
                agent_name=agent.name,
                phase="propose",
                round_num=1,
                content=pos[0],
            ))
            messages.append(DebateMessage(
                agent_name=agent.name,
                phase="vote",
                round_num=1,
                content=pos[0],
                vote=pos[1],
            ))

        vote_tally: Dict[str, int] = {"SUPPORT": 0, "OPPOSE": 0, "ABSTAIN": 0}
        for m in messages:
            if m.phase == "vote" and m.vote:
                vote_tally[m.vote] = vote_tally.get(m.vote, 0) + 1

        total = len(self.agents)
        support_pct = vote_tally.get("SUPPORT", 0) / total if total else 0
        oppose_pct = vote_tally.get("OPPOSE", 0) / total if total else 0

        if support_pct >= self.consensus_threshold:
            verdict = "CONSENSUS_SUPPORT"
            strength = support_pct
        elif oppose_pct >= self.consensus_threshold:
            verdict = "CONSENSUS_OPPOSE"
            strength = oppose_pct
        else:
            verdict = "NO_CONSENSUS"
            strength = max(support_pct, oppose_pct)

        synthesis = (
            f"Claim: {claim}\n"
            f"Verdict: {verdict} (strength={strength:.0%})\n"
            f"Votes: {vote_tally}\n"
        )

        return DebateResult(
            claim=claim,
            rounds=1,
            messages=messages,
            final_verdict=verdict,
            consensus_strength=round(strength, 3),
            synthesis=synthesis,
            vote_tally=vote_tally,
        )

    # ---- Heuristic position generators ----

    def _heuristic_expert(self, claim: str, evidence: list) -> tuple:
        has_evidence = len(evidence) >= 2
        has_quant = any(c.isdigit() for c in claim)
        if has_evidence and has_quant:
            return ("Evidence supports quantitative claims with multiple sources.", "SUPPORT")
        elif has_evidence:
            return ("Partial evidence available but claims need stronger quantification.", "ABSTAIN")
        else:
            return ("Insufficient evidence to validate domain claims.", "OPPOSE")

    def _heuristic_devil(self, claim: str, evidence: list) -> tuple:
        risk_words = ["always", "never", "all", "every", "guaranteed", "impossible", "certainly"]
        has_absolute = any(w in claim for w in risk_words)
        if has_absolute:
            return ("Claim uses absolute language — no empirical assertion is truly absolute.", "OPPOSE")
        return ("Claim is appropriately hedged, but sources should be independently verified.", "ABSTAIN")

    def _heuristic_method(self, claim: str, evidence: list) -> tuple:
        if len(evidence) >= 3:
            return ("Multiple independent sources provide methodological robustness.", "SUPPORT")
        elif len(evidence) >= 1:
            return ("Single-source evidence lacks cross-validation.", "ABSTAIN")
        return ("No evidence sources provided — methodologically unverifiable.", "OPPOSE")

    def _heuristic_practical(self, claim: str, evidence: list) -> tuple:
        risk_terms = ["cost", "budget", "risk", "scale", "feasib", "implement", "deploy"]
        addresses_practical = any(t in claim for t in risk_terms)
        if addresses_practical:
            return ("Claim addresses practical concerns and is actionable.", "SUPPORT")
        return ("Claim lacks practical implementation context.", "ABSTAIN")

    # ---- Prompt builders ----

    def _build_prompt(
        self, agent: AgentPersona, claim: str, context: str,
        evidence: str, phase: str, round_num: int,
        history: List[DebateMessage],
    ) -> str:
        parts = [f"## Debate Round {round_num} — {phase.upper()}"]
        parts.append(f"\n**Claim under debate:** {claim}")
        if context:
            parts.append(f"\n**Context:** {context}")
        if evidence:
            parts.append(f"\n**Evidence:**\n{evidence}")
        if history:
            parts.append("\n**Previous discussion:**")
            for m in history[-6:]:  # last 6 messages for context
                parts.append(f"- [{m.agent_name}] ({m.phase}): {m.content[:300]}")
        parts.append(f"\nAs {agent.name} ({agent.role}), state your position on this claim.")
        return "\n".join(parts)

    def _build_critique_prompt(
        self, agent: AgentPersona, claim: str,
        others: List[DebateMessage],
    ) -> str:
        parts = [f"## Critique Phase"]
        parts.append(f"\n**Claim:** {claim}")
        parts.append("\n**Other agents' positions:**")
        for m in others:
            parts.append(f"- [{m.agent_name}]: {m.content[:400]}")
        parts.append(f"\nAs {agent.name}, critique the other agents' positions. "
                      "Identify logical gaps, unsupported assumptions, or missed evidence.")
        return "\n".join(parts)

    def _build_vote_prompt(
        self, agent: AgentPersona, claim: str,
        history: List[DebateMessage],
    ) -> str:
        parts = ["## Final Vote"]
        parts.append(f"\n**Claim:** {claim}")
        parts.append("\n**Full debate summary:**")
        for m in history[-12:]:
            parts.append(f"- [{m.agent_name}] ({m.phase} R{m.round_num}): {m.content[:200]}")
        parts.append(
            f"\nAs {agent.name}, cast your final vote.\n"
            "Reply with exactly one of: SUPPORT, OPPOSE, or ABSTAIN.\n"
            "Then briefly explain your reasoning (1-2 sentences)."
        )
        return "\n".join(parts)

    def _parse_vote(self, response: str) -> str:
        upper = response.strip().upper()
        for vote in ("SUPPORT", "OPPOSE", "ABSTAIN"):
            if vote in upper:
                return vote
        return "ABSTAIN"

    def _synthesize(self, claim: str, messages: List[DebateMessage], tally: Dict[str, int]) -> str:
        if self.llm_call:
            prompt = (
                f"Synthesize the following multi-agent debate on the claim: {claim}\n\n"
                f"Vote tally: {tally}\n\n"
                "Key positions:\n"
            )
            for m in messages:
                if m.phase in ("propose", "vote"):
                    prompt += f"- [{m.agent_name}] ({m.vote or m.phase}): {m.content[:200]}\n"
            prompt += "\nProvide a balanced 2-3 paragraph synthesis."
            return self.llm_call(
                system_prompt="You are a neutral debate moderator synthesizing positions.",
                user_prompt=prompt,
            )
        # Heuristic fallback
        return (
            f"Debate on: {claim}\n"
            f"Vote tally: Support={tally.get('SUPPORT', 0)}, "
            f"Oppose={tally.get('OPPOSE', 0)}, "
            f"Abstain={tally.get('ABSTAIN', 0)}\n"
            f"Total agents: {len(self.agents)}"
        )

    def _format_evidence(self, evidence: List[Dict[str, str]]) -> str:
        lines = []
        for i, e in enumerate(evidence, 1):
            title = e.get("title", "")
            source = e.get("source", "")
            text = e.get("text", e.get("claim", ""))
            lines.append(f"{i}. [{source}] {title}: {text[:200]}")
        return "\n".join(lines)

    def build_debate_prompt_for_external_llm(
        self,
        claim: str,
        agents: Optional[List[AgentPersona]] = None,
    ) -> str:
        """Generate a single prompt that simulates multi-agent debate.

        For use when you want to run the debate in a single LLM call
        (e.g., Claude, GPT-4) rather than multiple calls.
        """
        agents = agents or self.agents
        roles = "\n".join(
            f"- **{a.name}** ({a.role}): {a.perspective}" for a in agents
        )
        return (
            f"# Multi-Agent Debate Simulation\n\n"
            f"**Claim:** {claim}\n\n"
            f"## Participants\n{roles}\n\n"
            f"## Instructions\n"
            f"Simulate a {self.max_rounds}-round structured debate:\n"
            f"1. **Round 1 — Propose**: Each agent states their initial position\n"
            f"2. **Rounds 2-{self.max_rounds} — Critique & Rebut**: "
            f"Agents challenge each other and defend positions\n"
            f"3. **Final Vote**: Each agent votes SUPPORT/OPPOSE/ABSTAIN\n"
            f"4. **Synthesis**: Neutral moderator summarizes consensus\n\n"
            f"For each agent, stay true to their role and perspective.\n"
            f"End with a vote tally and final synthesis paragraph."
        )
