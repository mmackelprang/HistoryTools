"""
Unified AI client -- provides a common interface for Gemini, OpenAI, and Anthropic.
Scripts call these functions instead of vendor-specific SDKs directly.
"""

import os
import re
import json
import time

try:
    from .config import load_env
    from .cost_tracker import get_tracker
except ImportError:
    from scripts.core.config import load_env  # type: ignore[no-redef]
    from scripts.core.cost_tracker import get_tracker  # type: ignore[no-redef]

RETRYABLE_CODES = {429, 500, 502, 503, 504, 529}
MAX_RETRIES = 3


def get_ai_client(vendor=None, api_key_env=None):
    """Get an AI client for the specified vendor.

    Args:
        vendor: "gemini", "openai", or "anthropic". Auto-detected from available keys if None.
        api_key_env: Override env var name for API key.

    Returns: (client, vendor_name)
    """
    load_env()

    if vendor is None:
        # Auto-detect based on available keys (cloud takes priority if set)
        if os.environ.get("HISTORYTOOLS_API_KEY"):
            vendor = "cloud"
        elif os.environ.get("GEMINI_API_KEY"):
            vendor = "gemini"
        elif os.environ.get("OPENAI_API_KEY"):
            vendor = "openai"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            vendor = "anthropic"
        else:
            raise ValueError("No AI API key found. Set GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, or HISTORYTOOLS_API_KEY in .env")

    if vendor == "gemini":
        key = os.environ.get(api_key_env or "GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY not set in .env")
        try:
            from google import genai
        except ImportError:
            raise ValueError("google-genai package not installed. Run: pip install google-genai")
        return genai.Client(api_key=key), "gemini"

    elif vendor == "openai":
        key = os.environ.get(api_key_env or "OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY not set in .env")
        try:
            import openai
        except ImportError:
            raise ValueError("openai package not installed. Run: pip install openai")
        return openai.OpenAI(api_key=key), "openai"

    elif vendor == "anthropic":
        key = os.environ.get(api_key_env or "ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set in .env")
        try:
            import anthropic
        except ImportError:
            raise ValueError("anthropic package not installed. Run: pip install anthropic")
        return anthropic.Anthropic(api_key=key), "anthropic"

    elif vendor == "cloud":
        key = os.environ.get(api_key_env or "HISTORYTOOLS_API_KEY")
        if not key:
            raise ValueError("HISTORYTOOLS_API_KEY not set in .env")
        # Cloud vendor is a managed AI gateway — coming soon.
        # When available, this will route to https://api.historytools.io
        raise NotImplementedError(
            "HistoryTools Cloud is not yet available. "
            "Use 'gemini', 'openai', or 'anthropic' instead, "
            "or visit https://historytools.io for updates."
        )

    else:
        raise ValueError(f"Unknown vendor: {vendor}. Use 'gemini', 'openai', 'anthropic', or 'cloud'.")


def call_text(client, vendor, prompt, model=None, max_tokens=4096,
              pipeline_step="unknown", file_path=None):
    """Send a text prompt to any AI vendor. Returns response text.

    Args:
        client: AI client from get_ai_client()
        vendor: "gemini", "openai", or "anthropic"
        prompt: Text prompt
        model: Model name override (vendor-specific)
        max_tokens: Max output tokens
        pipeline_step: Name of the pipeline step (for cost tracking)
        file_path: File being processed (for cost tracking)
    """
    defaults = {
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-haiku-4-5-20251001",
    }
    model = model or defaults.get(vendor, "gpt-4o-mini")
    tracker = get_tracker()

    for attempt in range(MAX_RETRIES + 1):
        try:
            if vendor == "gemini":
                response = client.models.generate_content(model=model, contents=[prompt])
                usage = getattr(response, 'usage_metadata', None)
                if usage:
                    tracker.record(vendor, model,
                        getattr(usage, 'prompt_token_count', 0),
                        getattr(usage, 'candidates_token_count', 0),
                        pipeline_step=pipeline_step, file_path=file_path)
                if response.text is None:
                    return ""
                return response.text.strip()

            elif vendor == "openai":
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                )
                if response.usage:
                    tracker.record(vendor, model,
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                        pipeline_step=pipeline_step, file_path=file_path)
                content = response.choices[0].message.content
                return content.strip() if content else ""

            elif vendor == "anthropic":
                # Use streaming for long responses
                text_parts = []
                with client.messages.stream(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                ) as stream:
                    for text in stream.text_stream:
                        text_parts.append(text)
                    final_message = stream.get_final_message()
                if final_message and hasattr(final_message, 'usage') and final_message.usage:
                    tracker.record(vendor, model,
                        final_message.usage.input_tokens,
                        final_message.usage.output_tokens,
                        pipeline_step=pipeline_step, file_path=file_path)
                return "".join(text_parts)

            else:
                raise ValueError(f"Unsupported vendor for call_text: {vendor}")

        except Exception as e:
            err_str = str(e)
            is_retryable = any(str(code) in err_str for code in RETRYABLE_CODES)
            if is_retryable and attempt < MAX_RETRIES:
                wait = 2 ** attempt * 5
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after {wait}s ({err_str[:60]}...)")
                time.sleep(wait)
                continue
            raise


def call_vision(client, vendor, prompt, image_bytes, model=None, max_tokens=4096,
                pipeline_step="unknown", file_path=None):
    """Send a text prompt with an image to any AI vendor with vision support. Returns response text.

    Args:
        client: AI client from get_ai_client()
        vendor: "gemini" or "openai" (anthropic vision not yet supported)
        prompt: Text prompt
        image_bytes: Image as bytes (PNG or JPEG)
        model: Model name override
        max_tokens: Max output tokens
        pipeline_step: Name of the pipeline step (for cost tracking)
        file_path: File being processed (for cost tracking)
    """
    import base64

    defaults = {
        "gemini": "gemini-2.5-flash",
        "openai": "gpt-4o",
    }
    model = model or defaults.get(vendor, "gpt-4o")
    tracker = get_tracker()

    # Detect MIME type
    mime_type = "image/jpeg" if image_bytes[:2] == b'\xff\xd8' else "image/png"

    for attempt in range(MAX_RETRIES + 1):
        try:
            if vendor == "gemini":
                from google.genai import types
                image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                response = client.models.generate_content(model=model, contents=[prompt, image_part])
                usage = getattr(response, 'usage_metadata', None)
                if usage:
                    tracker.record(vendor, model,
                        getattr(usage, 'prompt_token_count', 0),
                        getattr(usage, 'candidates_token_count', 0),
                        pipeline_step=pipeline_step, file_path=file_path)
                if response.text is None:
                    return "[Page appears blank or illegible]"
                return response.text.strip()

            elif vendor == "openai":
                b64_image = base64.b64encode(image_bytes).decode("utf-8")
                response = client.chat.completions.create(
                    model=model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {
                                "url": f"data:{mime_type};base64,{b64_image}"
                            }},
                        ],
                    }],
                    max_tokens=max_tokens,
                )
                if response.usage:
                    tracker.record(vendor, model,
                        response.usage.prompt_tokens,
                        response.usage.completion_tokens,
                        pipeline_step=pipeline_step, file_path=file_path)
                content = response.choices[0].message.content
                return content.strip() if content else "[Page appears blank or illegible]"

            else:
                raise ValueError(f"Vision not supported for vendor: {vendor}. Use 'gemini' or 'openai'.")

        except Exception as e:
            err_str = str(e)
            is_retryable = any(str(code) in err_str for code in RETRYABLE_CODES)
            if is_retryable and attempt < MAX_RETRIES:
                wait = 2 ** attempt * 5
                print(f"    Retry {attempt + 1}/{MAX_RETRIES} after {wait}s ({err_str[:60]}...)")
                time.sleep(wait)
                continue
            raise


def parse_json_response(text):
    """Parse a JSON response from any AI vendor, handling code fences."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None
