"""Quick Nova API diagnostic — run with: python check.py"""
import os, sys
from pathlib import Path

# Load .env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not key:
    print("ERROR: No GEMINI_API_KEY found in .env")
    sys.exit(1)

os.environ["GOOGLE_API_KEY"] = key
os.environ.pop("GEMINI_API_KEY", None)

print(f"Key found: {key[:8]}...{key[-4:]}")

try:
    from google import genai
    from google.genai import types
    client = genai.Client()

    for model in ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"]:
        print(f"\nTesting {model}...", end=" ", flush=True)
        try:
            resp = client.models.generate_content(
                model=model,
                contents="Reply with just: OK",
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            print(f"OK -> '{resp.text.strip()}'")
            break
        except Exception as e:
            print(f"FAIL -> {str(e)[:120]}")
except ImportError as e:
    print(f"Import error: {e}")
