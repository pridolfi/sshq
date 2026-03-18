import logging
import re
import flask.cli
from flask import Flask, request, jsonify

from .backends import get_backend


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


def start_server(port):
    global backend
    backend = get_backend()

    app.run(port=port, host='127.0.0.1', debug=False)
