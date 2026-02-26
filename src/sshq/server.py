import logging
import flask.cli
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

# 1. Suppress standard Werkzeug request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 2. Modern way to suppress the Flask startup banner
flask.cli.show_server_banner = lambda *args: None

app = Flask(__name__)
client = None  # Initialized when the server starts

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
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=data['prompt'],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.0
            )
        )
        return jsonify({"command": response.text.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def start_server():
    global client
    # Client automatically picks up the GEMINI_API_KEY environment variable
    client = genai.Client()

    app.run(port=5000, host='127.0.0.1', debug=False)
