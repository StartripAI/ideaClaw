"""IdeaClaw CLI — main entry point.

Usage:
    ideaclaw run --idea "Your idea" [--profile PROFILE] [--auto-approve] [--config PATH]
    ideaclaw resume --run-id RUN_ID
    ideaclaw status --run-id RUN_ID
    ideaclaw profiles [--domain DOMAIN]
    ideaclaw benchmark --dir PATH [--profile PROFILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

from ideaclaw import __version__
from ideaclaw.config import load_config
from ideaclaw.pipeline.runner import PipelineRunner

console = Console()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ideaclaw",
        description="IdeaClaw — Turn a rough idea into a usable, verifiable pack.",
    )
    parser.add_argument("--version", action="version", version=f"ideaclaw {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    run_p = sub.add_parser("run", help="Run the pipeline on a new idea")
    run_p.add_argument("--idea", type=str, required=True, help="Your rough idea (one sentence)")
    run_p.add_argument(
        "--pack-type",
        type=str,
        default="auto",
        choices=["auto", "decision", "proposal", "comparison", "brief", "study"],
        help="Pack type (default: auto-detect)",
    )
    run_p.add_argument(
        "--profile",
        type=str,
        default="auto",
        help="Quality profile (e.g. cs_ml.icml, medical.rct, general.decision). Default: auto-detect",
    )
    run_p.add_argument("--config", type=Path, default=None, help="Path to config YAML")
    run_p.add_argument("--auto-approve", action="store_true", help="Skip human approval at gate stages")
    run_p.add_argument("--language", type=str, default="en", help="Output language (en/zh/auto)")

    # --- resume ---
    resume_p = sub.add_parser("resume", help="Resume a pipeline run from checkpoint")
    resume_p.add_argument("--run-id", type=str, required=True, help="Run ID to resume")
    resume_p.add_argument("--config", type=Path, default=None)

    # --- status ---
    status_p = sub.add_parser("status", help="Check pipeline run status")
    status_p.add_argument("--run-id", type=str, required=True, help="Run ID to check")

    # --- profiles ---
    profiles_p = sub.add_parser("profiles", help="List available quality profiles")
    profiles_p.add_argument("--domain", type=str, default=None, help="Filter by domain (e.g. cs_ml, medical)")

    # --- benchmark ---
    bench_p = sub.add_parser("benchmark", help="Run quality benchmark on existing packs")
    bench_p.add_argument("--dir", type=Path, required=True, help="Directory containing pack files")
    bench_p.add_argument("--profile", type=str, default=None, help="Override profile for all packs")

    # --- login ---
    sub.add_parser("login", help="Log in to an LLM provider (interactive)")

    # --- logout ---
    logout_p = sub.add_parser("logout", help="Remove stored credentials")
    logout_p.add_argument("--provider", type=str, default=None, help="Provider to remove (default: all)")

    # --- whoami ---
    sub.add_parser("whoami", help="Show current authentication status")

    return parser.parse_args()


def cmd_run(args: argparse.Namespace) -> int:
    """Execute a full pipeline run."""
    from ideaclaw.quality.loader import auto_detect_profile, load_profile

    config = load_config(args.config)

    # Override config with CLI args
    config["idea"]["text"] = args.idea
    config["idea"]["pack_type"] = args.pack_type
    config["idea"]["language"] = args.language
    if args.auto_approve:
        config["security"]["auto_approve"] = True

    # Resolve profile
    profile_id = args.profile
    if profile_id == "auto":
        profile_id = auto_detect_profile(args.idea)
    config["quality"] = {"profile_id": profile_id}

    try:
        profile = load_profile(profile_id)
        profile_name = profile.name
    except FileNotFoundError:
        profile_name = profile_id

    console.print(f"\n[bold blue]🦞 IdeaClaw v{__version__}[/bold blue]")
    console.print(f"[dim]Idea:[/dim]    {args.idea}")
    console.print(f"[dim]Profile:[/dim] {profile_id} ({profile_name})")
    console.print()

    runner = PipelineRunner(config)
    result = runner.run()

    if result.success:
        console.print(f"\n[bold green]✅ Pack complete![/bold green]")
        console.print(f"[dim]Run ID:[/dim]  {result.run_id}")
        console.print(f"[dim]Output:[/dim]  {result.output_dir}")
        console.print(f"[dim]Pack:[/dim]    {result.output_dir / 'pack.md'}")
        return 0
    else:
        console.print(f"\n[bold red]❌ Pipeline failed at stage: {result.failed_stage}[/bold red]")
        console.print(f"[dim]Run ID:[/dim]  {result.run_id}")
        console.print(f"[dim]Reason:[/dim]  {result.error}")
        return 2


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume a pipeline run from checkpoint."""
    config = load_config(args.config)
    runner = PipelineRunner(config)
    result = runner.resume(args.run_id)

    if result.success:
        console.print(f"\n[bold green]✅ Pack complete![/bold green]")
        console.print(f"[dim]Output:[/dim] {result.output_dir}")
        return 0
    else:
        console.print(f"\n[bold red]❌ Resume failed: {result.error}[/bold red]")
        return 2


def cmd_status(args: argparse.Namespace) -> int:
    """Check pipeline run status."""
    # TODO: implement status check from manifest
    console.print(f"[dim]Checking status for run: {args.run_id}[/dim]")
    console.print("[yellow]Status check not yet implemented.[/yellow]")
    return 0


def cmd_profiles(args: argparse.Namespace) -> int:
    """List available quality profiles."""
    from ideaclaw.quality.loader import list_profiles

    profiles = list_profiles(domain=args.domain)
    if not profiles:
        console.print("[yellow]No profiles found.[/yellow]")
        return 1

    console.print(f"\n[bold]Available profiles ({len(profiles)}):[/bold]\n")
    current_domain = ""
    for pid, name in profiles:
        domain = pid.split(".")[0]
        if domain != current_domain:
            current_domain = domain
            console.print(f"  [bold cyan]{domain}/[/bold cyan]")
        console.print(f"    {pid:<35s}  {name}")
    console.print()
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Run quality benchmark on existing pack files."""
    from ideaclaw.quality.benchmark import BenchmarkRunner
    from ideaclaw.quality.report import format_report
    import json

    runner = BenchmarkRunner()
    pack_dir = Path(args.dir)

    if not pack_dir.exists():
        console.print(f"[red]Directory not found: {pack_dir}[/red]")
        return 2

    # Find pack.md files
    pack_files = list(pack_dir.rglob("pack.md"))
    if not pack_files:
        console.print(f"[yellow]No pack.md files found in {pack_dir}[/yellow]")
        return 1

    console.print(f"\n[bold]Running benchmark on {len(pack_files)} packs...[/bold]\n")
    for pf in sorted(pack_files):
        content = pf.read_text(encoding="utf-8")
        # Try to get profile from manifest
        manifest_path = pf.parent / "manifest.json"
        profile_id = args.profile or "general.decision"
        idea = ""
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                idea = manifest.get("idea", {}).get("text", "")
                profile_id = args.profile or manifest.get("quality", {}).get("profile_id", profile_id)
            except Exception:
                pass
        runner.add_pack(content, idea=idea, profile_id=profile_id, pack_path=str(pf))
        console.print(f"  ✓ {pf.parent.name}")

    report = runner.generate_report()
    console.print()
    console.print(format_report(report))
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    """Interactive login to an LLM provider."""
    from ideaclaw.llm.auth import interactive_login
    result = interactive_login()
    return 0 if result else 1


def cmd_logout(args: argparse.Namespace) -> int:
    """Remove stored credentials."""
    from ideaclaw.llm.auth import remove_stored_key, list_stored_providers, CREDENTIALS_FILE

    if args.provider:
        if remove_stored_key(args.provider):
            console.print(f"[green]✅ Removed credentials for {args.provider}[/green]")
        else:
            console.print(f"[yellow]No stored credentials for {args.provider}[/yellow]")
    else:
        providers = list_stored_providers()
        if not providers:
            console.print("[yellow]No stored credentials.[/yellow]")
            return 0
        for p in providers:
            remove_stored_key(p["provider"])
        console.print(f"[green]✅ Removed all {len(providers)} stored credentials[/green]")
    return 0


def cmd_whoami(args: argparse.Namespace) -> int:
    """Show current authentication status."""
    from ideaclaw.llm.auth import resolve_credentials, list_stored_providers

    config = load_config(None)
    creds = resolve_credentials(config)

    console.print(f"\n[bold blue]🦞 IdeaClaw Auth Status[/bold blue]\n")

    if creds.source == "none":
        console.print("[yellow]Not authenticated. Run: ideaclaw login[/yellow]")
        return 1

    console.print(f"  Provider:  [bold]{creds.provider}[/bold]")
    console.print(f"  Source:    {creds.source}")
    console.print(f"  Base URL:  {creds.base_url}")
    console.print(f"  Model:     {creds.primary_model}")
    console.print(f"  Key:       {creds.api_key[:8]}...")
    console.print()

    stored = list_stored_providers()
    if stored:
        console.print(f"  Stored providers ({len(stored)}):")
        for p in stored:
            console.print(f"    {p['provider']:<15s}  {p['key_preview']:<15s}  {p['model']}")
    console.print()
    return 0


def main() -> int:
    """CLI entry point."""
    args = _parse_args()

    commands = {
        "run": cmd_run,
        "resume": cmd_resume,
        "status": cmd_status,
        "profiles": cmd_profiles,
        "benchmark": cmd_benchmark,
        "login": cmd_login,
        "logout": cmd_logout,
        "whoami": cmd_whoami,
    }

    handler = commands.get(args.command)
    if handler is None:
        console.print(f"[red]Unknown command: {args.command}[/red]")
        return 2

    try:
        return handler(args)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        return 130
    except Exception as exc:
        console.print(f"\n[bold red]Error:[/bold red] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
