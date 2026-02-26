import sys
import os
import subprocess
import threading
import base64
from .server import start_server

Q_SCRIPT = """#!/usr/bin/env python3
import sys
import json
import urllib.request

def main():
    if len(sys.argv) < 2:
        print("Usage: q <your prompt>")
        sys.exit(1)

    prompt = " ".join(sys.argv[1:])
    data = json.dumps({"prompt": prompt}).encode('utf-8')
    req = urllib.request.Request(
        "http://localhost:5000/ask",
        data=data,
        headers={'Content-Type': 'application/json'}
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode())
            print(result.get("error") or result.get("command", "No command returned."))
    except urllib.error.URLError:
        print("Error: Tunnel is down. Did you connect using sshq?")

if __name__ == "__main__":
    main()
"""

def main():
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("Usage: sshq [standard ssh arguments, e.g., user@host]")
        sys.exit(1)

    # Start the Flask server in a background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Base64 encode the script to avoid quoting/newline nightmares in the SSH command
    b64_script = base64.b64encode(Q_SCRIPT.encode('utf-8')).decode('utf-8')

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
    ssh_args = ['ssh', '-t', '-R', '5000:localhost:5000'] + args + [remote_cmd]

    try:
        # Run ssh and hand over terminal control to it
        subprocess.run(ssh_args)
    except KeyboardInterrupt:
        pass
    except FileNotFoundError:
        print("Error: 'ssh' command not found.", file=sys.stderr)
        sys.exit(1)
