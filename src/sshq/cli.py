import sys
import os
import socket
import subprocess
import threading
import base64
from importlib.metadata import version
from .server import start_server

Q_SCRIPT = """#!/usr/bin/env python3
import sys
import json
import urllib.request
import subprocess

def main():
    if len(sys.argv) < 2:
        print("Usage: q <your prompt>")
        sys.exit(1)

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
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
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
