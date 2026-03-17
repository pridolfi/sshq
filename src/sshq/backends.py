"""AI provider backends for sshq. Each backend implements generate(prompt, system_instruction, temperature)."""
import os


def _gemini_generate(prompt, system_instruction, temperature=0.0):
    from google import genai
    from google.genai import types

    client = genai.Client()
    model = os.environ.get("SSHQ_GEMINI_MODEL", "gemini-2.5-flash")
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=temperature,
        ),
    )
    return response.text.strip()


def _groq_generate(prompt, system_instruction, temperature=0.0):
    from openai import OpenAI

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY"),
    )
    model = os.environ.get("SSHQ_GROQ_MODEL", "llama-3.3-70b-versatile")
    # Groq converts temperature=0 to 1e-8; use a tiny value for deterministic output
    t = max(1e-8, temperature)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        temperature=t,
    )
    return (response.choices[0].message.content or "").strip()


def get_backend():
    """Return the active backend function (prompt, system_instruction, temperature=0.0) -> str.
    Uses Groq if GROQ_API_KEY is set, otherwise Gemini (requires GEMINI_API_KEY).
    """
    if os.environ.get("GROQ_API_KEY"):
        return _groq_generate
    if os.environ.get("GEMINI_API_KEY"):
        return _gemini_generate
    raise ValueError("Set GROQ_API_KEY or GEMINI_API_KEY.")
