"""Functional test: aarch64 Ubuntu container, sshq tunnel, run q and expect output."""
import base64
import socket
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# Expected analysis output (key lines we assert on)
EXPECTED_CPU_FEATURES = """The CPU features listed are:
* fp: floating point instructions
* asimd: advanced simd instructions
* evtstrm: event stream instructions
* aes: advanced encryption standard instructions
* pmull: polynomial multiplication instructions
* sha1: secure hash algorithm 1 instructions
* sha2: secure hash algorithm 2 instructions
* crc32: cyclic redundancy check 32 instructions
* atomics: atomic operations instructions
* fphp: floating point and half precision instructions
* asimdhp: advanced simd half precision instructions
* cpuid: cpu identification instructions
* asimdrdm: advanced simd random number generation instructions
* lrcpc: load and store register pair instructions
* dcpop: data cache pop instructions
* asimddp: advanced simd dot product instructions
* uscat: user space cache instructions
* ilrcpc: integer load and store register pair instructions
* flagm: flag manipulation instructions
* paca: pointer authentication code instructions
* pacg: pointer authentication code generation instructions"""


def _podman_available():
    if not __import__("shutil").which("podman"):
        return False
    r = subprocess.run(
        ["podman", "info"],
        capture_output=True,
        timeout=10,
    )
    return r.returncode == 0


def _mock_backend(prompt, system_instruction, temperature=0.0, max_tokens=None):
    if "replace foo by bar" in prompt:
        return "sed -i 's/foo/bar/g' test.txt"
    if "show cpu features" in prompt or "cpuinfo" in prompt.lower():
        return EXPECTED_CPU_FEATURES
    return ""


@pytest.mark.functional
@pytest.mark.skipif(not _podman_available(), reason="Podman not available or not running")
def test_sshq_into_aarch64_ubuntu_run_q_commands(tmp_path):
    """Spin up aarch64 Ubuntu container, run sshq tunnel + q, assert command and analyze output."""
    from sshq.cli import Q_SCRIPT
    from sshq.server import start_server

    # 1) SSH key for container
    key_path = tmp_path / "id_rsa"
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        check=True,
        capture_output=True,
    )
    pubkey = key_path.with_suffix(".pub").read_text()

    # 2) Build image with our public key baked in (avoids bind-mount ownership issues with rootless Podman)
    repo_root = Path(__file__).resolve().parents[1]
    dockerfile_dir = repo_root / "tests" / "docker"
    build_dir = tmp_path / "docker_build"
    build_dir.mkdir()
    (build_dir / "authorized_keys").write_text(pubkey)
    dockerfile_src = (dockerfile_dir / "Dockerfile").read_text()
    (build_dir / "Dockerfile").write_text(
        dockerfile_src.rstrip()
        + "\nCOPY authorized_keys /root/.ssh/authorized_keys\n"
        + "RUN chmod 600 /root/.ssh/authorized_keys\n"
    )
    image_name = "sshq-test-aarch64"
    build = subprocess.run(
        ["podman", "build", "--platform", "linux/arm64", "-t", image_name, "."],
        cwd=build_dir,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if build.returncode != 0:
        pytest.skip(f"Could not build aarch64 image (emulation?): {build.stderr!r}")

    # 3) Free port for our server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # 4) Mock backend and start server in background
    with patch("sshq.server.get_backend", return_value=_mock_backend):
        server_thread = threading.Thread(
            target=start_server,
            kwargs={"port": port},
            daemon=True,
        )
        server_thread.start()
    time.sleep(0.5)

    q_script = Q_SCRIPT.format(port=port)
    b64_script = base64.b64encode(q_script.encode("utf-8")).decode("utf-8")

    install_q = (
        "python3 -c \"import base64, os; "
        "d=os.path.expanduser('~/.local/bin'); os.makedirs(d, exist_ok=True); "
        "p=os.path.join(d, 'q'); "
        "f=open(p, 'wb'); f.write(base64.b64decode('" + b64_script + "')); f.close(); "
        "os.chmod(p, 0o755)\""
    )
    run_q1 = "echo y | /root/.local/bin/q 'replace foo by bar in test.txt'"
    run_q2 = "/root/.local/bin/q --analyze /proc/cpuinfo 'show cpu features, briefly explain them'"
    remote_cmd = f"{install_q} && {run_q1} && {run_q2}"

    # 5) Run container with SSH, port 2222
    container_id = None
    try:
        run_result = subprocess.run(
            [
                "podman", "run", "-d", "--rm",
                "--platform", "linux/arm64",
                "-p", "127.0.0.1:2222:22",
                image_name,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if run_result.returncode != 0:
            pytest.skip(f"Could not run aarch64 container: {run_result.stderr!r}")
        container_id = run_result.stdout.strip()

        # Wait for SSH (under emulation sshd can take 30+ seconds to start)
        time.sleep(5)
        last_r = None
        for _ in range(90):
            r = subprocess.run(
                [
                    "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                    "-o", "ConnectTimeout=3", "-i", str(key_path), "-p", "2222",
                    "root@127.0.0.1", "true",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            last_r = r
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            msg = "SSH did not become ready in time"
            if last_r is not None:
                msg += f". Last attempt: stdout={last_r.stdout!r} stderr={last_r.stderr!r}"
            pytest.fail(msg)

        # 6) SSH with reverse tunnel and run q commands
        result = subprocess.run(
            [
                "ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-i", str(key_path), "-p", "2222",
                "-R", f"{port}:127.0.0.1:{port}",
                "root@127.0.0.1", remote_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        out, err = result.stdout, result.stderr
    finally:
        if container_id:
            subprocess.run(["podman", "stop", "-t", "2", container_id], capture_output=True, timeout=5)

    assert result.returncode == 0, f"ssh failed: stdout={out!r} stderr={err!r}"

    # 7) Assert expected output
    combined = out + "\n" + err
    assert "sed -i 's/foo/bar/g' test.txt" in combined, f"Expected sed command in: {combined!r}"
    assert "The CPU features listed are" in combined, f"Expected CPU features header in: {combined!r}"
    assert "fp: floating point instructions" in combined
    assert "asimd: advanced simd instructions" in combined
    assert "aes: advanced encryption standard instructions" in combined
