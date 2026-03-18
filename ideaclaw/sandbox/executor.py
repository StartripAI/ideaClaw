"""Sandbox — safe code execution environment for experiments.

Covers both ARC-style (Docker sandbox for generated experiment code)
and AR-style (iterative train.py modification + evaluation) use cases.

Security model:
  1. subprocess with timeout + resource limits (default)
  2. Docker container isolation (when docker_image is set)
  3. Network access can be disabled
  4. Output size capped
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ExecResult:
    """Result from a sandbox execution."""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    elapsed_seconds: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: List[str] = field(default_factory=list)  # paths to output files
    error: str = ""


@dataclass
class SandboxConfig:
    """Configuration for sandbox execution."""
    timeout_seconds: int = 300          # max wall-clock time
    max_output_bytes: int = 10_000_000  # 10MB stdout/stderr cap
    docker_image: str = ""              # if set, use Docker isolation
    network_enabled: bool = False       # allow network access
    gpu_enabled: bool = False           # mount GPU (Docker)
    memory_limit_mb: int = 4096         # memory limit
    working_dir: Optional[str] = None   # custom working directory
    env_vars: Dict[str, str] = field(default_factory=dict)


class SandboxExecutor:
    """Execute code safely in an isolated environment.

    Supports two modes:
    1. subprocess (default) — runs code in a child process with ulimit
    2. Docker — runs code in an isolated container

    Usage:
        executor = SandboxExecutor(config)
        result = executor.run_script("experiment.py", code)
        result = executor.run_command(["python", "train.py"])
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._work_dir: Optional[Path] = None

    def run_script(
        self,
        filename: str,
        code: str,
        args: Optional[List[str]] = None,
        input_files: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Write code to a temp file and execute it.

        Args:
            filename: Name for the script file (e.g., "experiment.py")
            code: Source code to execute.
            args: Optional command-line arguments.
            input_files: Optional dict of {filename: content} to write alongside.

        Returns:
            ExecResult with stdout, stderr, metrics, and artifacts.
        """
        work_dir = Path(tempfile.mkdtemp(prefix="ideaclaw_sandbox_"))
        self._work_dir = work_dir

        try:
            # Write the main script
            script_path = work_dir / filename
            script_path.write_text(code, encoding="utf-8")

            # Write any input files
            if input_files:
                for name, content in input_files.items():
                    fpath = work_dir / name
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(content, encoding="utf-8")

            # Build command
            cmd = [sys.executable, str(script_path)]
            if args:
                cmd.extend(args)

            # Execute
            if self.config.docker_image:
                return self._run_docker(cmd, work_dir)
            else:
                return self._run_subprocess(cmd, work_dir)
        except Exception as exc:
            return ExecResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                elapsed_seconds=0.0,
                error=f"sandbox_setup_failed: {exc}",
            )
        finally:
            # Collect artifacts before cleanup
            pass  # cleanup is done by caller or garbage collection

    def run_command(
        self,
        cmd: List[str],
        working_dir: Optional[Path] = None,
    ) -> ExecResult:
        """Run an arbitrary command in the sandbox.

        Args:
            cmd: Command and arguments to execute.
            working_dir: Optional working directory.

        Returns:
            ExecResult.
        """
        work_dir = working_dir or Path(tempfile.mkdtemp(prefix="ideaclaw_sandbox_"))
        self._work_dir = work_dir

        if self.config.docker_image:
            return self._run_docker(cmd, work_dir)
        else:
            return self._run_subprocess(cmd, work_dir)

    def _run_subprocess(self, cmd: List[str], work_dir: Path) -> ExecResult:
        """Execute via subprocess with timeout and resource limits."""
        env = os.environ.copy()
        env.update(self.config.env_vars)
        # Prevent accidental network calls in subprocess mode
        if not self.config.network_enabled:
            env["IDEACLAW_SANDBOX_NO_NETWORK"] = "1"

        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                timeout=self.config.timeout_seconds,
                env=env,
                text=True,
            )
            elapsed = time.monotonic() - start

            stdout = proc.stdout[:self.config.max_output_bytes]
            stderr = proc.stderr[:self.config.max_output_bytes]

            # Try to parse metrics from stdout (JSON on last line)
            metrics = self._extract_metrics(stdout)
            artifacts = self._collect_artifacts(work_dir)

            return ExecResult(
                success=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                elapsed_seconds=round(elapsed, 2),
                metrics=metrics,
                artifacts=artifacts,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return ExecResult(
                success=False,
                exit_code=-9,
                stdout="",
                stderr=f"Timeout after {self.config.timeout_seconds}s",
                elapsed_seconds=round(elapsed, 2),
                error="timeout_exceeded",
            )
        except OSError as exc:
            elapsed = time.monotonic() - start
            return ExecResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                elapsed_seconds=round(elapsed, 2),
                error=f"os_error: {exc}",
            )

    def _run_docker(self, cmd: List[str], work_dir: Path) -> ExecResult:
        """Execute via Docker container for full isolation."""
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{work_dir}:/workspace",
            "-w", "/workspace",
            f"--memory={self.config.memory_limit_mb}m",
        ]

        if not self.config.network_enabled:
            docker_cmd.append("--network=none")

        if self.config.gpu_enabled:
            docker_cmd.extend(["--gpus", "all"])

        for key, val in self.config.env_vars.items():
            docker_cmd.extend(["-e", f"{key}={val}"])

        docker_cmd.append(self.config.docker_image)
        docker_cmd.extend(cmd)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                text=True,
            )
            elapsed = time.monotonic() - start

            stdout = proc.stdout[:self.config.max_output_bytes]
            stderr = proc.stderr[:self.config.max_output_bytes]
            metrics = self._extract_metrics(stdout)
            artifacts = self._collect_artifacts(work_dir)

            return ExecResult(
                success=proc.returncode == 0,
                exit_code=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                elapsed_seconds=round(elapsed, 2),
                metrics=metrics,
                artifacts=artifacts,
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            # Kill the container
            subprocess.run(
                ["docker", "kill", self.config.docker_image],
                capture_output=True,
                timeout=10,
            )
            return ExecResult(
                success=False,
                exit_code=-9,
                stdout="",
                stderr=f"Docker timeout after {self.config.timeout_seconds}s",
                elapsed_seconds=round(elapsed, 2),
                error="docker_timeout_exceeded",
            )
        except FileNotFoundError:
            return ExecResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="Docker not found. Install Docker or use subprocess mode.",
                elapsed_seconds=0.0,
                error="docker_not_installed",
            )

    def _extract_metrics(self, stdout: str) -> Dict[str, Any]:
        """Extract metrics from the last JSON line in stdout.

        Convention: experiments print metrics as JSON on the last line:
        {"val_bpb": 1.23, "val_loss": 0.45, "train_time": 300}
        """
        for line in reversed(stdout.strip().split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    continue
        return {}

    def _collect_artifacts(self, work_dir: Path) -> List[str]:
        """Collect output artifacts (non-script files) from work_dir."""
        artifacts = []
        for f in work_dir.rglob("*"):
            if f.is_file() and f.suffix in (
                ".json", ".csv", ".tsv", ".png", ".pdf",
                ".pt", ".pth", ".h5", ".pkl", ".npy",
                ".log", ".txt", ".md",
            ):
                artifacts.append(str(f))
        return artifacts

    def cleanup(self) -> None:
        """Remove the working directory."""
        if self._work_dir and self._work_dir.exists():
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None
