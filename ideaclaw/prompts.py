"""Prompt template engine for IdeaClaw."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


_DEFAULT_PROMPTS_PATH = Path(__file__).resolve().parents[1] / "prompts.default.yaml"


class PromptEngine:
    """Loads and renders per-stage prompts from YAML templates."""

    def __init__(self, custom_file: Optional[str] = None):
        self._prompts = self._load_prompts(custom_file)
        self._blocks = self._prompts.get("blocks", {})
        self._stages = self._prompts.get("stages", {})

    def _load_prompts(self, custom_file: Optional[str]) -> Dict[str, Any]:
        """Load default prompts, optionally overridden by custom file."""
        with open(_DEFAULT_PROMPTS_PATH, "r", encoding="utf-8") as f:
            defaults = yaml.safe_load(f) or {}

        if custom_file:
            custom_path = Path(custom_file).resolve()
            if custom_path.exists():
                with open(custom_path, "r", encoding="utf-8") as f:
                    custom = yaml.safe_load(f) or {}
                # Merge stage-level overrides
                for stage, prompts in custom.get("stages", {}).items():
                    defaults.setdefault("stages", {})[stage] = prompts
        return defaults

    def get_system_prompt(self, stage_name: str) -> str:
        """Get system prompt for a pipeline stage."""
        stage = self._stages.get(stage_name, {})
        return stage.get("system", "You are a helpful assistant.")

    def get_user_prompt(self, stage_name: str, **kwargs: Any) -> str:
        """Get user prompt for a pipeline stage, with variable substitution.

        Variables in the template like {idea_text} are replaced with kwargs.
        Block references like {trust_constraint} are expanded from the blocks section.
        """
        stage = self._stages.get(stage_name, {})
        template = stage.get("user", "")

        # Inject blocks into kwargs
        all_vars = dict(self._blocks)
        all_vars.update(kwargs)

        try:
            return template.format(**all_vars)
        except KeyError:
            # Return template with unfilled variables rather than crashing
            return template

    def get_max_tokens(self, stage_name: str) -> Optional[int]:
        """Get max_tokens for a stage, if specified."""
        stage = self._stages.get(stage_name, {})
        return stage.get("max_tokens")

    def is_json_mode(self, stage_name: str) -> bool:
        """Check if a stage expects JSON output."""
        stage = self._stages.get(stage_name, {})
        return stage.get("json_mode", False)

    @property
    def stage_names(self) -> list[str]:
        """List all defined stage names."""
        return list(self._stages.keys())
