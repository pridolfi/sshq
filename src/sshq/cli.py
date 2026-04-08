import sys
import os
import socket
import subprocess
import threading
import base64
import time
from importlib.metadata import version
from .server import start_server

# Container name for sshq-managed RamaLama (so we can stop it on exit)
RAMALAMA_CONTAINER_NAME = "sshq-ramalama"


def _is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(0.5)
            s.connect((host, port))
            return True
        except (OSError, socket.error):
            return False


def _wait_for_port(host: str, port: int, timeout_sec: float = 120, interval_sec: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if _is_port_in_use(host, port):
            return True
        time.sleep(interval_sec)
    return False


def _start_ramalama(port: int, model: str) -> bool:
    """Start RamaLama serve in the background. Return True if we started it, False if port was in use."""
    if _is_port_in_use("127.0.0.1", port):
        return False
    try:
        subprocess.run(
            ["ramalama", "serve", "-d", "-p", str(port), "--name", RAMALAMA_CONTAINER_NAME, model],
            check=True,
            capture_output=True,
            timeout=300,
        )
    except FileNotFoundError:
        print("Error: 'ramalama' not found. Install it from https://ramalama.ai/ or set SSHQ_LOCAL_BASE_URL to an existing server.", file=sys.stderr)
        print("To install RamaLama, run: curl -fsSL https://ramalama.ai/install.sh | bash", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error: ramalama serve failed: {e.stderr.decode() if e.stderr else e}", file=sys.stderr)
        sys.exit(1)
    if not _wait_for_port("127.0.0.1", port):
        print("Error: RamaLama server did not become ready in time. Try running 'ramalama serve -d -p {} {}' manually.".format(port, model), file=sys.stderr)
        subprocess.run(["ramalama", "stop", RAMALAMA_CONTAINER_NAME], capture_output=True)
        sys.exit(1)
    return True


def _stop_ramalama() -> None:
    subprocess.run(["ramalama", "stop", RAMALAMA_CONTAINER_NAME], capture_output=True, timeout=10)

Q_SCRIPT = """#!/usr/bin/env python3
import sys
import json
import urllib.request
import subprocess
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: q <your prompt>")
        print("       q --analyze <file> <prompt>")
        print("       q --agentic <goal>   # multi-step commands until the goal is answered")
        sys.exit(1)

    # q --analyze <file> <prompt>
    if len(sys.argv) >= 3 and sys.argv[1] == "--analyze":
        filepath = sys.argv[2]
        prompt = " ".join(sys.argv[3:]).strip()
        if not prompt:
            print("Usage: q --analyze <file> <prompt>")
            sys.exit(1)
        try:
            with open(filepath, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            print(f"Error: cannot read {{filepath}}: {{e}}")
            sys.exit(1)

        data = json.dumps({{"prompt": prompt, "content": content}}).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:{port}/analyze",
            data=data,
            headers={{'Content-Type': 'application/json'}},
        )
        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode())
                if "error" in result:
                    print(f"Error: {{result['error']}}")
                    sys.exit(1)
                print(result.get("analysis", ""))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode()
                res = json.loads(body)
                msg = res.get("error", body or e.reason)
            except Exception:
                msg = e.reason or str(e)
            print(f"Error: {{msg}}")
            sys.exit(1)
        except urllib.error.URLError as e:
            print("Error: Tunnel is down. Did you connect using sshq?")
            if e.reason:
                print(f"  ({{e.reason}})")
            sys.exit(1)
        return

    # q --agentic <goal> -> multi-step agent loop
    if len(sys.argv) >= 2 and sys.argv[1] == "--agentic":
        goal = " ".join(sys.argv[2:]).strip()
        if not goal:
            print("Usage: q --agentic <your goal or question>")
            sys.exit(1)

        def _truncate_field(text, max_len):
            text = text or ""
            if len(text) <= max_len:
                return text
            return text[: max(0, max_len - 40)] + "\\n[... truncated ...]\\n"

        try:
            max_steps = int(os.environ.get("SSHQ_AGENTIC_MAX_STEPS", "25"))
        except ValueError:
            max_steps = 25
        try:
            max_chars = int(os.environ.get("SSHQ_AGENTIC_MAX_OUTPUT_CHARS", "32000"))
        except ValueError:
            max_chars = 32000
        half = max(1000, max_chars // 2)

        history = []
        for step in range(1, max_steps + 1):
            payload = json.dumps({{"goal": goal, "history": history}}).encode("utf-8")
            req = urllib.request.Request(
                "http://localhost:{port}/agentic",
                data=payload,
                headers={{"Content-Type": "application/json"}},
            )
            try:
                with urllib.request.urlopen(req) as response:
                    result = json.loads(response.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode()
                    res = json.loads(body)
                    msg = res.get("error", body or e.reason)
                except Exception:
                    msg = e.reason or str(e)
                print(f"Error: {{msg}}")
                sys.exit(1)
            except urllib.error.URLError as e:
                print("Error: Tunnel is down. Did you connect using sshq?")
                if e.reason:
                    print(f"  ({{e.reason}})")
                sys.exit(1)

            if "error" in result and result.get("error"):
                print(f"Error: {{result['error']}}")
                sys.exit(1)

            action = result.get("action")
            if action == "answer":
                print()
                print(f"✅ {{result.get('answer', '')}}")
                return

            if action != "command":
                print("Error: Unexpected response from server.")
                sys.exit(1)

            command = result.get("command")
            if not command:
                print("Error: No command returned.")
                sys.exit(1)

            print()
            print(f"\\033[1;90m[agentic step {{step}}/{{max_steps}}]\\033[0m")
            print(f"\\033[1;36m{{command}}\\033[0m")
            print()
            choice = input("Run this command? [Y/n] ").strip().lower()
            if choice == "n":
                print("Aborted.")
                sys.exit(0)

            print()
            completed = subprocess.run(command, shell=True, capture_output=True, text=True)
            if completed.stdout:
                sys.stdout.write(completed.stdout)
            if completed.stderr:
                sys.stderr.write(completed.stderr)
            out = _truncate_field(completed.stdout, half)
            err = _truncate_field(completed.stderr, half)
            history.append({{
                "command": command,
                "stdout": out,
                "stderr": err,
                "exit_code": completed.returncode,
            }})

        print(f"Stopped after {{max_steps}} steps (SSHQ_AGENTIC_MAX_STEPS). Increase the limit or narrow the goal.")
        sys.exit(1)

    # q <prompt> -> suggest command
    prompt = " ".join(sys.argv[1:])
    data = json.dumps({{"prompt": prompt}}).encode('utf-8')
    req = urllib.request.Request(
        "http://localhost:{port}/ask",
        data=data,
        headers={{'Content-Type': 'application/json'}}
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())

            if "error" in result:
                print(f"Error: {{result['error']}}")
                sys.exit(1)

            command = result.get("command")
            if not command:
                print("No command returned.")
                sys.exit(1)

            # Print the suggested command clearly
            print(f"\\n\\033[1;36m{{command}}\\033[0m\\n")

            # Prompt the user
            choice = input("Do you want to execute this command? [y/N] ").strip().lower()
            if choice == 'y':
                print() # Add a blank line for readability before execution
                subprocess.run(command, shell=True)

    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            result = json.loads(body)
            msg = result.get("error", body or e.reason)
        except Exception:
            msg = e.reason or str(e)
        print(f"Error: {{msg}}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print("Error: Tunnel is down. Did you connect using sshq?")
        if e.reason:
            print(f"  ({{e.reason}})")
        sys.exit(1)

if __name__ == "__main__":
    main()
"""

def main():
    use_local = os.environ.get("SSHQ_USE_LOCAL", "").lower() in ("1", "true", "yes", "y")
    if not use_local and not os.environ.get("GROQ_API_KEY") and not os.environ.get("GEMINI_API_KEY"):
        print("Error: Set SSHQ_USE_LOCAL=1 for local (RamaLama), or GROQ_API_KEY, or GEMINI_API_KEY.", file=sys.stderr)
        sys.exit(1)

    prog = os.path.basename(sys.argv[0])
    args = sys.argv[1:]
    if not args:
        print(f"Usage: {prog} [standard ssh arguments, e.g., user@host]")
        sys.exit(1)
    if args in (["--version"], ["-V"]):
        print(version(__package__ or "sshq"))
        sys.exit(0)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # When using local (RamaLama), start the model server if not already running
    we_started_ramalama = False
    if use_local and not os.environ.get("SSHQ_LOCAL_BASE_URL"):
        ramalama_port = int(os.environ.get("SSHQ_RAMALAMA_PORT", "8080"))
        model = os.environ.get("SSHQ_LOCAL_MODEL", "llama3.2:1b")
        if _start_ramalama(ramalama_port, model):
            we_started_ramalama = True
        os.environ["SSHQ_LOCAL_BASE_URL"] = f"http://127.0.0.1:{ramalama_port}/v1"

    # Build the q script with the configured port
    q_script = Q_SCRIPT.format(port=port)

    # Start the Flask server in a background thread
    server_thread = threading.Thread(target=start_server, kwargs={"port": port}, daemon=True)
    server_thread.start()

    # Base64 encode the script to avoid quoting/newline nightmares in the SSH command
    b64_script = base64.b64encode(q_script.encode('utf-8')).decode('utf-8')

    # The magic payload:
    # 1. Uses Python on the board to decode and save the script to ~/.local/bin/q
    # 2. Makes it executable
    # 3. Uses `exec` to replace the current process with the user's default shell
    remote_cmd = (
        f"python3 -c \"import base64, os; "
        f"d=os.path.expanduser('~/.local/bin'); os.makedirs(d, exist_ok=True); "
        f"p=os.path.join(d, 'q'); "
        f"f=open(p, 'wb'); f.write(base64.b64decode('{b64_script}')); f.close(); "
        f"os.chmod(p, 0o755)\" && "
        f"exec ${{SHELL:-/bin/sh}} -l"
    )

    # We add '-t' to force TTY allocation so the interactive shell works properly
    ssh_args = ['ssh', '-t', '-R', f'{port}:localhost:{port}'] + args + [remote_cmd]

    try:
        # Run ssh and hand over terminal control to it
        subprocess.run(ssh_args)
    except KeyboardInterrupt:
        pass
    except FileNotFoundError:
        print("Error: 'ssh' command not found.", file=sys.stderr)
        sys.exit(1)
    finally:
        if we_started_ramalama:
            _stop_ramalama()
