"""IdeaClaw configuration — typed dataclasses + validation.

Ported from ARC's config.py (15 frozen dataclasses, dotted-key validation,
search order, required fields, mode/backend/experiment enums) with
IdeaClaw-specific additions (orchestrator profiles, library, memory).

Config resolution order:
  1. Explicit --config path
  2. config.ideaclaw.yaml in current directory
  3. config.yaml in current directory
  4. DEFAULTS (built-in)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_SEARCH_ORDER = ("config.ideaclaw.yaml", "config.yaml")

REQUIRED_FIELDS = (
    "project.name",
    "llm.provider",
)

PROJECT_MODES = {"auto", "semi-auto", "manual", "docs-first"}
KB_BACKENDS = {"markdown", "obsidian", "json"}
EXPERIMENT_MODES = {"simulated", "sandbox", "docker", "ssh_remote", "colab_drive"}
CITATION_STYLES = {"natbib", "apa", "mla", "chicago", "ieee"}
EXPORT_FORMATS = {"markdown", "docx", "latex", "pdf", "html"}


# ---------------------------------------------------------------------------
# Typed config dataclasses (frozen for immutability)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProjectConfig:
    name: str = "ideaclaw-run"
    mode: str = "auto"
    output_dir: str = "./output"


@dataclass(frozen=True)
class IdeaConfig:
    text: str = ""
    pack_type: str = "auto"
    language: str = "en"
    domains: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeConfig:
    timezone: str = "UTC"
    max_parallel_tasks: int = 1
    approval_timeout_hours: int = 12
    retry_limit: int = 2
    log_level: str = "INFO"


@dataclass(frozen=True)
class NotificationsConfig:
    channel: str = "console"    # console | slack | discord | webhook
    target: str = ""
    on_stage_start: bool = False
    on_stage_fail: bool = False
    on_gate_required: bool = True


@dataclass(frozen=True)
class KnowledgeBaseConfig:
    backend: str = "markdown"   # markdown | obsidian | json
    root: str = "docs/kb"
    obsidian_vault: str = ""


@dataclass(frozen=True)
class LlmConfig:
    provider: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""
    primary_model: str = "gpt-4o"
    fallback_models: Tuple[str, ...] = ("gpt-4o-mini",)
    s2_api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    notes: str = ""


@dataclass(frozen=True)
class SourceConfig:
    search_engines: Tuple[str, ...] = ("google", "bing")
    academic_apis: Tuple[str, ...] = ("openalex", "semantic_scholar")
    local_paths: Tuple[str, ...] = ()
    quality_threshold: float = 4.0
    daily_source_count: int = 10
    cache_ttl_hours: int = 24
    max_results_per_api: int = 50


@dataclass(frozen=True)
class EvidenceConfig:
    profile: str = "fulltext-preferred"
    gate_mode: str = "strict"   # strict | lenient | skip
    ocr_mode: str = "auto"      # auto | force | skip
    min_confidence: float = 0.7


@dataclass(frozen=True)
class ExportConfig:
    formats: Tuple[str, ...] = ("markdown", "docx")
    include_audit: bool = True
    include_sources: bool = True
    template_dir: str = ""
    output_dir: str = "./output"


@dataclass(frozen=True)
class SecurityConfig:
    hitl_required_stages: Tuple[int, ...] = (5, 7, 14)
    auto_approve: bool = False
    allow_publish_without_approval: bool = False
    redact_sensitive_logs: bool = True


@dataclass(frozen=True)
class SandboxConfig:
    python_path: str = ".venv/bin/python3"
    gpu_required: bool = False
    allowed_imports: Tuple[str, ...] = (
        "math", "random", "json", "csv", "numpy", "torch", "sklearn",
    )
    max_memory_mb: int = 4096
    timeout_seconds: int = 300


@dataclass(frozen=True)
class SshRemoteConfig:
    host: str = ""
    user: str = ""
    port: int = 22
    key_path: str = ""
    gpu_ids: Tuple[int, ...] = ()
    remote_workdir: str = "/tmp/ideaclaw_experiments"
    remote_python: str = "python3"
    setup_commands: Tuple[str, ...] = ()
    use_docker: bool = False
    docker_image: str = "ideaclaw/experiment:latest"
    docker_network_policy: str = "none"
    docker_memory_limit_mb: int = 8192
    docker_shm_size_mb: int = 2048


@dataclass(frozen=True)
class OrchestratorConfig:
    """AR-style orchestrator settings."""
    profiles_dir: str = "orchestrator/profiles"
    default_profile: str = "icml_2025"
    max_concurrent_loops: int = 1
    runs_dir: str = "~/.ideaclaw/runs"


@dataclass(frozen=True)
class MemoryConfig:
    """Memory + Library system settings."""
    enabled: bool = True
    store_dir: str = "~/.ideaclaw/memory"
    max_skills: int = 100
    preference_decay_days: int = 90


@dataclass(frozen=True)
class LibraryConfig:
    """Personal library (RAG) settings."""
    enabled: bool = True
    store_dir: str = "~/.ideaclaw/library"
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_backend: str = "sentence-transformers"  # sentence-transformers | tfidf
    embedding_model: str = "all-MiniLM-L6-v2"
    max_documents: int = 1000


@dataclass(frozen=True)
class PromptsConfig:
    custom_file: str = ""
    prompts_dir: str = ""


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IdeaClawConfig:
    """Complete IdeaClaw configuration — all typed."""
    project: ProjectConfig = field(default_factory=ProjectConfig)
    idea: IdeaConfig = field(default_factory=IdeaConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    notifications: NotificationsConfig = field(default_factory=NotificationsConfig)
    knowledge_base: KnowledgeBaseConfig = field(default_factory=KnowledgeBaseConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    evidence: EvidenceConfig = field(default_factory=EvidenceConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    ssh_remote: SshRemoteConfig = field(default_factory=SshRemoteConfig)
    orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    library: LibraryConfig = field(default_factory=LibraryConfig)
    prompts: PromptsConfig = field(default_factory=PromptsConfig)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


def _get_by_path(data: dict, dotted_key: str) -> Any:
    """Get value from nested dict using dotted key notation."""
    cur = data
    for part in dotted_key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_config(data: Dict[str, Any]) -> ValidationResult:
    """Validate raw config dict against constraints."""
    errors: List[str] = []
    warnings: List[str] = []

    # Required fields
    for field_path in REQUIRED_FIELDS:
        val = _get_by_path(data, field_path)
        if _is_blank(val):
            errors.append(f"Required field '{field_path}' is missing or blank")

    # Mode validation
    mode = _get_by_path(data, "project.mode")
    if mode and mode not in PROJECT_MODES:
        errors.append(f"project.mode '{mode}' not in {PROJECT_MODES}")

    kb_backend = _get_by_path(data, "knowledge_base.backend")
    if kb_backend and kb_backend not in KB_BACKENDS:
        errors.append(f"knowledge_base.backend '{kb_backend}' not in {KB_BACKENDS}")

    # Warnings
    api_key = _get_by_path(data, "llm.api_key")
    api_key_env = _get_by_path(data, "llm.api_key_env")
    if not api_key and not api_key_env:
        warnings.append("No LLM API key configured (llm.api_key or llm.api_key_env)")

    return ValidationResult(
        ok=len(errors) == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def resolve_config_path(explicit: Optional[str] = None) -> Optional[Path]:
    """Return first existing config from search order, or explicit path."""
    if explicit is not None:
        return Path(explicit)
    for name in CONFIG_SEARCH_ORDER:
        candidate = Path(name)
        if candidate.exists():
            return candidate
    return None


def _to_tuple(val: Any) -> Any:
    """Convert lists to tuples for frozen dataclass compatibility."""
    if isinstance(val, list):
        return tuple(val)
    return val


def _parse_section(cls, data: dict) -> Any:
    """Parse a dict into a frozen dataclass, converting lists to tuples."""
    if not data:
        return cls()
    kwargs = {}
    for f_name in cls.__dataclass_fields__:
        if f_name in data:
            kwargs[f_name] = _to_tuple(data[f_name])
    return cls(**kwargs)


def load_config(config_path: Optional[Path] = None) -> IdeaClawConfig:
    """Load configuration from YAML file.

    Args:
        config_path: Path to config YAML. If None, searches default locations.

    Returns:
        Fully typed IdeaClawConfig.
    """
    data: Dict[str, Any] = {}

    path = resolve_config_path(str(config_path) if config_path else None)
    if path is not None and path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

    # Validate
    result = validate_config(data)
    if not result.ok:
        import logging
        for err in result.errors:
            logging.getLogger(__name__).warning("Config error: %s", err)

    # Parse sections
    return IdeaClawConfig(
        project=_parse_section(ProjectConfig, data.get("project", {})),
        idea=_parse_section(IdeaConfig, data.get("idea", {})),
        runtime=_parse_section(RuntimeConfig, data.get("runtime", {})),
        notifications=_parse_section(NotificationsConfig, data.get("notifications", {})),
        knowledge_base=_parse_section(KnowledgeBaseConfig, data.get("knowledge_base", {})),
        llm=_parse_section(LlmConfig, data.get("llm", {})),
        source=_parse_section(SourceConfig, data.get("source", {})),
        evidence=_parse_section(EvidenceConfig, data.get("evidence", {})),
        export=_parse_section(ExportConfig, data.get("export", {})),
        security=_parse_section(SecurityConfig, data.get("security", {})),
        sandbox=_parse_section(SandboxConfig, data.get("sandbox", {})),
        ssh_remote=_parse_section(SshRemoteConfig, data.get("ssh_remote", {})),
        orchestrator=_parse_section(OrchestratorConfig, data.get("orchestrator", {})),
        memory=_parse_section(MemoryConfig, data.get("memory", {})),
        library=_parse_section(LibraryConfig, data.get("library", {})),
        prompts=_parse_section(PromptsConfig, data.get("prompts", {})),
    )
