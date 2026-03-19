"""Remote sandbox — execute experiments on Colab, SSH, or cloud VMs.

Surpasses ARC's colab_sandbox.py + ssh_sandbox.py by unifying into
a single interface with pluggable backends.
"""
from __future__ import annotations
import logging
import json, subprocess, time, tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from ideaclaw.sandbox.executor import ExecResult

logger = logging.getLogger(__name__)

__all__ = ['RemoteConfig', 'RemoteSandbox']


@dataclass
class RemoteConfig:
    """Configuration for remote execution."""
    backend: str = "ssh"         # ssh | docker_remote | cloud_api
    host: str = ""               # SSH hostname or API endpoint
    port: int = 22
    username: str = ""
    key_file: str = ""           # SSH private key path
    docker_image: str = ""       # For docker_remote backend
    gpu_type: str = ""           # e.g. "A100", "T4"
    timeout_seconds: int = 3600  # 1 hour default for remote
    working_dir: str = "/tmp/ideaclaw"
    env_vars: Dict[str, str] = field(default_factory=dict)


class RemoteSandbox:
    """Execute code on remote machines via SSH, Docker, or cloud API.

    Usage:
        remote = RemoteSandbox(RemoteConfig(
            backend="ssh", host="gpu-server.lab.org",
            username="researcher", key_file="~/.ssh/id_rsa",
        ))
        result = remote.run_script("train.py", code, input_files={"data.csv": csv_data})
    """

    def __init__(self, config: RemoteConfig):
        self.config = config

    def run_script(self, filename: str, code: str,
                   args: Optional[List[str]] = None,
                   input_files: Optional[Dict[str, str]] = None) -> ExecResult:
        """Upload and execute a script on the remote machine."""
        if self.config.backend == "ssh":
            return self._run_ssh(filename, code, args, input_files)
        elif self.config.backend == "docker_remote":
            return self._run_docker_remote(filename, code, args, input_files)
        elif self.config.backend == "cloud_api":
            return self._run_cloud_api(filename, code, args, input_files)
        else:
            return ExecResult(success=False, exit_code=-1, stdout="", stderr=f"Unknown backend: {self.config.backend}",
                              elapsed_seconds=0, error="unsupported_backend")

    def _run_ssh(self, filename: str, code: str,
                 args: Optional[List[str]] = None,
                 input_files: Optional[Dict[str, str]] = None) -> ExecResult:
        """Execute via SSH: upload files → run → download results."""
        c = self.config
        ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
        if c.key_file:
            ssh_opts.extend(["-i", c.key_file])
        target = f"{c.username}@{c.host}" if c.username else c.host
        remote_dir = c.working_dir

        start = time.monotonic()
        try:
            # 1. Create remote directory + upload script
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                local_script = f.name

            subprocess.run(["ssh"] + ssh_opts + ["-p", str(c.port), target,
                            f"mkdir -p {remote_dir}"],
                           capture_output=True, timeout=30)

            subprocess.run(["scp"] + ssh_opts + ["-P", str(c.port),
                            local_script, f"{target}:{remote_dir}/{filename}"],
                           capture_output=True, timeout=60)

            # Upload input files
            if input_files:
                for name, content in input_files.items():
                    with tempfile.NamedTemporaryFile(mode="w", suffix="", delete=False) as f:
                        f.write(content)
                        tmp = f.name
                    subprocess.run(["scp"] + ssh_opts + ["-P", str(c.port),
                                    tmp, f"{target}:{remote_dir}/{name}"],
                                   capture_output=True, timeout=60)

            # 2. Execute remotely
            env_str = " ".join(f"{k}={v}" for k, v in c.env_vars.items())
            cmd = f"cd {remote_dir} && {env_str} python3 {filename}"
            if args:
                cmd += " " + " ".join(args)

            proc = subprocess.run(
                ["ssh"] + ssh_opts + ["-p", str(c.port), target, cmd],
                capture_output=True, text=True,
                timeout=c.timeout_seconds,
            )
            elapsed = time.monotonic() - start

            # 3. Extract metrics from stdout
            metrics = {}
            for line in reversed(proc.stdout.strip().split("\n")):
                if line.strip().startswith("{"):
                    try:
                        metrics = json.loads(line.strip())
                        break
                    except json.JSONDecodeError:
                        continue

            return ExecResult(
                success=proc.returncode == 0, exit_code=proc.returncode,
                stdout=proc.stdout[:100000], stderr=proc.stderr[:100000],
                elapsed_seconds=round(elapsed, 2), metrics=metrics,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(success=False, exit_code=-9, stdout="", stderr=f"SSH timeout after {c.timeout_seconds}s",
                              elapsed_seconds=round(time.monotonic() - start, 2), error="ssh_timeout")
        except FileNotFoundError:
            return ExecResult(success=False, exit_code=-1, stdout="", stderr="SSH client not found",
                              elapsed_seconds=0, error="ssh_not_installed")

    def _run_docker_remote(self, filename: str, code: str,
                           args: Optional[List[str]] = None,
                           input_files: Optional[Dict[str, str]] = None) -> ExecResult:
        """Execute via docker on a remote host (SSH + docker run)."""
        c = self.config
        # First upload via SSH, then docker run on remote
        ssh_result = self._run_ssh(filename, code, args, input_files)
        if not ssh_result.success and c.docker_image:
            # Fallback: try docker context
            return ExecResult(success=False, exit_code=-1, stdout="",
                              stderr="Docker remote requires SSH access first",
                              elapsed_seconds=0, error="docker_remote_needs_ssh")
        return ssh_result

    def _run_cloud_api(self, filename: str, code: str,
                       args: Optional[List[str]] = None,
                       input_files: Optional[Dict[str, str]] = None) -> ExecResult:
        """Execute via cloud API (placeholder for Modal/Lambda/RunPod)."""
        return ExecResult(
            success=False, exit_code=-1, stdout="",
            stderr="Cloud API backend not yet configured. Set config.host to your API endpoint.",
            elapsed_seconds=0, error="cloud_api_not_configured",
        )

    def check_connection(self) -> bool:
        """Test if remote host is reachable."""
        if self.config.backend != "ssh":
            return False
        c = self.config
        ssh_opts = ["-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5"]
        if c.key_file:
            ssh_opts.extend(["-i", c.key_file])
        target = f"{c.username}@{c.host}" if c.username else c.host
        try:
            proc = subprocess.run(
                ["ssh"] + ssh_opts + ["-p", str(c.port), target, "echo ok"],
                capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
