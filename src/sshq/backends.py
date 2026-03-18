"""AI provider backends for sshq. Each backend implements generate(prompt, system_instruction, temperature, max_tokens)."""
import os


def _gemini_generate(prompt, system_instruction, temperature=0.0, max_tokens=None):
    from google import genai
    from google.genai import types

    client = genai.Client()
    model = os.environ.get("SSHQ_GEMINI_MODEL", "gemini-2.5-flash")
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
    )
    if max_tokens is not None:
        config.max_output_tokens = max_tokens
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    return response.text.strip()


def _groq_generate(prompt, system_instruction, temperature=0.0, max_tokens=None):
    from openai import OpenAI

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=os.environ.get("GROQ_API_KEY"),
    )
    model = os.environ.get("SSHQ_GROQ_MODEL", "llama-3.3-70b-versatile")
    # Groq converts temperature=0 to 1e-8; use a tiny value for deterministic output
    t = max(1e-8, temperature)
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": t,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def _local_generate(prompt, system_instruction, temperature=0.0, max_tokens=None):
    """OpenAI-compatible local server (e.g. RamaLama, Ollama, llama.cpp)."""
    from openai import OpenAI

    base_url = os.environ.get("SSHQ_LOCAL_BASE_URL", "http://127.0.0.1:8080/v1")
    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"
    model = os.environ.get("SSHQ_LOCAL_MODEL", "llama3.2:1b")
    # Many local servers treat 0 as deterministic; use small value if needed
    t = max(1e-8, temperature)
    client = OpenAI(base_url=base_url, api_key=os.environ.get("SSHQ_LOCAL_API_KEY") or "not-used")
    kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": t,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def get_backend():
    """Return the active backend function (prompt, system_instruction, temperature=0.0) -> str.
    Priority: SSHQ_USE_LOCAL (RamaLama/Ollama/etc) > GROQ_API_KEY > GEMINI_API_KEY.
    """
    if os.environ.get("SSHQ_USE_LOCAL", "").lower() in ("1", "true", "yes"):
        return _local_generate
    if os.environ.get("GROQ_API_KEY"):
        return _groq_generate
    if os.environ.get("GEMINI_API_KEY"):
        return _gemini_generate
    raise ValueError(
        "Set SSHQ_USE_LOCAL=1 for local (RamaLama/Ollama), or GROQ_API_KEY, or GEMINI_API_KEY."
    )
