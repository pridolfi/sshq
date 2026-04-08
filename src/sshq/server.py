import json
import logging
import re
from typing import Optional, Tuple

import flask.cli
from flask import Flask, request, jsonify

from .backends import get_backend


def _extract_json_object(text: str) -> Optional[dict]:
    """Parse a JSON object from model output, optionally inside a markdown code fence."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1)
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(text, start)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    return None


def _format_agentic_history(history: list) -> str:
    if not history:
        return "No commands have been run yet."
    parts = []
    for i, item in enumerate(history, start=1):
        cmd = item.get("command", "")
        code = item.get("exit_code", "")
        out = item.get("stdout", "") or ""
        err = item.get("stderr", "") or ""
        parts.append(
            f"### Step {i}\n"
            f"Command: {cmd}\n"
            f"Exit code: {code}\n"
            f"Stdout:\n{out}\n"
            f"Stderr:\n{err}\n"
        )
    return "\n".join(parts)


def _parse_agentic_response(raw: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Returns (action, command_or_none, answer_or_none).
    action is 'command', 'answer', or 'error'.
    """
    obj = _extract_json_object(raw)
    if not obj or not isinstance(obj, dict):
        return ("error", None, raw.strip() or "Could not parse model response as JSON.")

    typ = (obj.get("type") or "").strip().lower()
    if typ == "answer":
        ans = obj.get("answer")
        if ans is None:
            ans = obj.get("text")
        if not isinstance(ans, str) or not ans.strip():
            return ("error", None, "JSON type 'answer' but missing non-empty 'answer' string.")
        return ("answer", None, ans.strip())

    if typ == "command":
        cmd = obj.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            return ("error", None, "JSON type 'command' but missing non-empty 'command' string.")
        return ("command", cmd.strip(), None)

    return ("error", None, f"Unknown or missing JSON 'type': {typ!r}")


def _extract_command(raw: str) -> str:
    """Extract a single shell command from model output that may include markdown or explanations."""
    text = raw.strip()
    # Prefer content inside first markdown code block (e.g. ```bash\n...\n```)
    match = re.search(r"```(?:bash|sh)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        block = match.group(1).strip()
        first_line = block.split("\n")[0].strip()
        if first_line:
            return first_line
    # Otherwise take first non-empty line that looks like a command (not prose)
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("To ", "The ", "Note:", "Explanation", "Explanation:")):
            continue
        if len(line) > 2:
            return line
    return text.split("\n")[0].strip() if text else ""

# Suppress standard Werkzeug request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Suppress the Flask startup banner
flask.cli.show_server_banner = lambda *args: None

app = Flask(__name__)
backend = None  # Set to generate(prompt, system_instruction, temperature) in start_server


@app.route('/ask', methods=['POST'])
def ask():
    data = request.json
    if not data or 'prompt' not in data:
        return jsonify({"error": "No prompt provided"}), 400

    system_instruction = (
        "You are an expert embedded Linux engineer. "
        "Provide ONLY the exact shell command to achieve the user's request. "
        "Do NOT use markdown formatting (like ```bash). Do NOT provide explanations. "
        "Do NOT use sudo unless the task clearly requires root (e.g. installing system packages); prefer commands that work with the current user's permissions."
    )

    try:
        text = backend(data['prompt'], system_instruction, temperature=0.0, max_tokens=256)
        command = _extract_command(text)
        return jsonify({"command": command or text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/analyze', methods=['POST'])
def analyze():
    data = request.json
    if not data or 'prompt' not in data or 'content' not in data:
        return jsonify({"error": "prompt and content are required"}), 400

    system_instruction = (
        "You are an expert embedded Linux engineer analyzing text and log files. "
        "Answer the user's question about the provided content clearly and concisely. "
        "Do NOT use markdown formatting for the answer, and do NOT use markdown code fences for the content itself. "
        "You can use bullets and numbered lists to format the answer, in plain ASCII."
    )

    contents = f"Content to analyze:\n\n{data['content']}\n\nUser question: {data['prompt']}"

    try:
        text = backend(contents, system_instruction, temperature=0.0, max_tokens=1024)
        return jsonify({"analysis": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/agentic", methods=["POST"])
def agentic():
    data = request.json
    if not data or "goal" not in data:
        return jsonify({"error": "goal is required"}), 400

    goal = (data.get("goal") or "").strip()
    if not goal:
        return jsonify({"error": "goal must be non-empty"}), 400

    history = data.get("history")
    if history is None:
        history = []
    if not isinstance(history, list):
        return jsonify({"error": "history must be a list"}), 400

    system_instruction = (
        "You are an expert embedded Linux engineer helping via a multi-step shell workflow. "
        "The user is on a device reached through SSH; you never run commands yourself—you only "
        "propose one shell command at a time or give a final answer.\n\n"
        "Respond with ONLY one JSON object (no markdown fences, no other text):\n"
        '- To gather more data: {"type": "command", "command": "<single shell command>"}\n'
        '- When the user\'s goal is fully satisfied from the information available (including '
        "outputs in the history): {\"type\": \"answer\", \"answer\": \"<plain text answer>\"}\n\n"
        "Prefer non-destructive, read-only commands unless the goal requires changes. "
        "Do NOT use sudo unless clearly needed. One command per step; avoid compound pipelines "
        "unless necessary. If output was truncated, you may suggest a narrower follow-up command."
    )

    user_message = (
        "## User goal\n"
        f"{goal}\n\n"
        "## Command history and outputs\n"
        f"{_format_agentic_history(history)}\n\n"
        "Decide the next single shell command to run, or answer the goal if you already can."
    )

    try:
        text = backend(user_message, system_instruction, temperature=0.0, max_tokens=2048)
        action, command, answer = _parse_agentic_response(text)
        if action == "error":
            return jsonify({"error": answer or "Invalid agentic response"}), 500
        if action == "answer":
            return jsonify({"action": "answer", "answer": answer})
        return jsonify({"action": "command", "command": command})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def start_server(port):
    global backend
    backend = get_backend()

    app.run(port=port, host='127.0.0.1', debug=False)
