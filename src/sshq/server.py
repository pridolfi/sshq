import logging
import flask.cli
from flask import Flask, request, jsonify

from .backends import get_backend

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
        "Do NOT use markdown formatting (like ```bash). Do NOT provide explanations."
    )

    try:
        text = backend(data['prompt'], system_instruction, temperature=0.0)
        return jsonify({"command": text})
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
        text = backend(contents, system_instruction, temperature=0.0)
        return jsonify({"analysis": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def start_server(port):
    global backend
    backend = get_backend()

    app.run(port=port, host='127.0.0.1', debug=False)
