"""
Gemini Vision Bridge — Give vision to any text-only LLM
========================================================
Call Google Gemini 2.5 Flash directly to analyze images.
No pip install needed — pure Python stdlib.

Usage:
    # CLI
    python vision_pipeline.py "image.jpg" "What do you see?"

    # Python
    from vision_pipeline import analyze_image
    result = analyze_image("chart.png", "Extract all numbers")
"""

import os, base64, json, urllib.request
from pathlib import Path

# ── Load secrets ──────────────────────────────────────────────
# Priority:
#   1. GEMINI_API_KEY env var (standalone)
#   2. CUSTOM_PROVIDER_GENERATIVELANGUAGE_GOOGLEAPIS_COM_KEY env var (Hermes)
#   3. .env file in current directory
#   4. ~/.hermes/.env file (Hermes)

# Try local .env first
_local_env = Path.cwd() / ".env"
if _local_env.exists():
    with open(_local_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v

# Try Hermes .env
_hermes_env = Path.home() / ".hermes" / ".env"
if _hermes_env.exists():
    with open(_hermes_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v

GEMINI_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("CUSTOM_PROVIDER_GENERATIVELANGUAGE_GOOGLEAPIS_COM_KEY")
    or ""
)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Allow custom base URL for OAuth token workaround
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "")

MIME_MAP = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
}


# ── Public API ─────────────────────────────────────────────────

def analyze_image(image_input: str, question: str = "Describe this image in detail.") -> str:
    """
    Analyze an image using Gemini 2.5 Flash vision.

    Args:
        image_input: URL (http/https), local file path, or base64 data URL
        question: What to ask about the image

    Returns:
        Text analysis from Gemini, or error message
    """
    if not GEMINI_KEY:
        return (
            "ERROR: No Gemini API key found.\n"
            "Set GEMINI_API_KEY in .env file or as environment variable.\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )

    try:
        img_bytes, mime = _resolve_image(image_input)
    except Exception as e:
        return f"ERROR loading image: {e}"

    b64 = base64.b64encode(img_bytes).decode("ascii")

    payload = {
        "contents": [{
            "parts": [
                {"inlineData": {"mimeType": mime, "data": b64}},
                {"text": question}
            ]
        }]
    }

    if GEMINI_BASE_URL:
        url = f"{GEMINI_BASE_URL.rstrip('/')}/models/{GEMINI_MODEL}:generateContent"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GEMINI_KEY}"
            }
        )
    else:
        url = f"{GEMINI_URL}?key={GEMINI_KEY}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}
        )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            if text:
                return text
            return json.dumps(data, indent=2)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500] if e.fp else ""
        return f"ERROR HTTP {e.code}: {body}"
    except Exception as e:
        return f"ERROR: {e}"


# ── Internal helpers ──────────────────────────────────────────

def _resolve_image(image_input: str) -> tuple[bytes, str]:
    """Resolve image input to (bytes, mime_type)."""
    if image_input.startswith(("http://", "https://")):
        req = urllib.request.Request(
            image_input,
            headers={"User-Agent": "GeminiVisionBridge/1.0"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            img_bytes = resp.read()
        ext = image_input.split("?")[0].rsplit(".", 1)[-1].lower()
        mime = MIME_MAP.get(ext, "image/jpeg")
        return img_bytes, mime

    elif image_input.startswith("data:"):
        header, data = image_input.split(",", 1)
        mime = header.split(":")[1].split(";")[0]
        return base64.b64decode(data), mime

    elif os.path.isfile(image_input):
        ext = Path(image_input).suffix.lower().lstrip(".")
        mime = MIME_MAP.get(ext, "image/png")
        return Path(image_input).read_bytes(), mime

    else:
        raise ValueError(f"Cannot resolve image input: {image_input[:100]}")


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python vision_pipeline.py <image_url_or_path> [question]")
        print()
        print("Examples:")
        print("  python vision_pipeline.py photo.jpg \"What is this?\"")
        print("  python vision_pipeline.py https://example.com/img.png")
        print("  python vision_pipeline.py screenshot.png \"Find bugs in this UI\"")
        sys.exit(1)

    image = sys.argv[1]
    question = sys.argv[2] if len(sys.argv) > 2 else "Describe this image in detail."

    print(analyze_image(image, question))
