"""
LLM provider API callers (OpenAI, Anthropic, Gemini, Bedrock, Ollama, Grok, DeepSeek).
Extracted from server.py to eliminate duplication between chat() and chat_stream().

All cloud providers follow the same failsafe pattern:
  - 5 attempts max
  - Exponential backoff: [5, 10, 20, 40, 80] seconds
  - Raises LLMError on final failure (never returns error strings silently)
"""
import os
import json
import asyncio
import base64
import httpx
import boto3
from botocore.config import Config


# ─── Image helpers ──────────────────────────────────────────────────────────────

def _parse_data_uri(data_uri: str) -> tuple[str, str]:
    """Parse a data URI into (mime_type, raw_base64).

    Accepts:
      - "data:image/png;base64,iVBOR..."
      - plain base64 string (assumes image/png)
    """
    if data_uri.startswith("data:"):
        header, b64 = data_uri.split(",", 1)
        mime = header.split(";")[0].replace("data:", "")
        return mime, b64
    return "image/png", data_uri


def _build_openai_image_content(text: str, images: list[str] | None) -> list[dict] | str:
    """Build OpenAI/Grok multimodal content blocks.

    If images is empty, returns plain text string.
    Otherwise returns a list of content parts (text + image_url blocks).
    """
    if not images:
        return text
    parts: list[dict] = [{"type": "text", "text": text}]
    for img in images[:5]:
        mime, b64 = _parse_data_uri(img)
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        })
    return parts


def _build_anthropic_image_content(text: str, images: list[str] | None) -> list[dict] | str:
    """Build Anthropic multimodal content blocks.

    Returns list of content parts with image + text blocks.
    """
    if not images:
        return text
    parts: list[dict] = []
    for img in images[:5]:
        mime, b64 = _parse_data_uri(img)
        parts.append({
            "type": "image",
            "source": {"type": "base64", "media_type": mime, "data": b64}
        })
    parts.append({"type": "text", "text": text})
    return parts


class LLMError(Exception):
    """Raised when an LLM call fails after all retries.

    This propagates through the orchestration engine so it can stop execution
    instead of silently passing error strings to the next node.
    """
    pass


# Configuration — read at call time so OLLAMA_BASE_URL set after import is respected
def _ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

OLLAMA_MODEL = "llama3"


def detect_mode_from_model(model_name: str) -> str:
    """Detect the provider mode from a model name prefix.

    Returns 'cloud' for OpenAI/Anthropic/Gemini/Grok/DeepSeek models,
    'bedrock' for Bedrock, and 'local' for anything else (assumed to be Ollama).
    """
    if not model_name:
        return "local"
    m = model_name.lower()
    if m.startswith("gpt"):
        return "cloud"
    if m.startswith("claude"):
        return "cloud"
    if m.startswith("gemini") or m.startswith("gemma") or m.startswith("lyria"):
        return "cloud"
    if m.startswith("bedrock"):
        return "bedrock"
    if m.startswith("grok"):
        return "cloud"
    if m.startswith("deepseek"):
        return "cloud"
    return "local"


def detect_provider_from_model(model_name: str) -> str:
    """Detect the provider name from a model name prefix."""
    if not model_name:
        return "ollama"
    m = model_name.lower()
    if m.startswith("gpt"):
        return "openai"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith("gemini") or m.startswith("gemma") or m.startswith("lyria"):
        return "gemini"
    if m.startswith("bedrock"):
        return "bedrock"
    if m.startswith("grok"):
        return "grok"
    if m.startswith("deepseek"):
        return "deepseek"
    return "ollama"



def _make_aws_client(service_name: str, region: str, settings: dict):
    """Create a boto3 client.

    If access/secret are not provided, boto3 will use its default credential chain
    (env vars, AWS_PROFILE, SSO, instance role, etc.).
    """
    # Amazon Bedrock API keys can be provided as a bearer token via this env var.
    # See: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys-use.html
    bedrock_api_key = (settings.get("bedrock_api_key") or "").strip()
    # Users often paste a full header value. Normalize to the raw ABSK... token.
    if bedrock_api_key:
        # Strip surrounding quotes
        if (bedrock_api_key.startswith('"') and bedrock_api_key.endswith('"')) or (
            bedrock_api_key.startswith("'") and bedrock_api_key.endswith("'")
        ):
            bedrock_api_key = bedrock_api_key[1:-1].strip()

        lower = bedrock_api_key.lower()
        if lower.startswith("authorization:"):
            bedrock_api_key = bedrock_api_key.split(":", 1)[1].strip()
            lower = bedrock_api_key.lower()
        if lower.startswith("bearer "):
            bedrock_api_key = bedrock_api_key.split(" ", 1)[1].strip()

    # If a Bedrock API key is provided, prefer it and avoid mixing auth mechanisms.
    if bedrock_api_key:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = bedrock_api_key
        access_key = ""
        secret_key = ""
        session_token = ""
    else:
        # Clear if user removed it in settings
        if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
            os.environ.pop("AWS_BEARER_TOKEN_BEDROCK", None)
        access_key = (settings.get("aws_access_key_id") or "").strip()
        secret_key = (settings.get("aws_secret_access_key") or "").strip()
        session_token = (settings.get("aws_session_token") or "").strip()
    region_name = (region or settings.get("aws_region") or "us-east-1").strip()

    kwargs = {
        "service_name": service_name,
        "region_name": region_name,
    }

    if access_key and secret_key:
        kwargs.update(
            {
                "aws_access_key_id": access_key,
                "aws_secret_access_key": secret_key,
            }
        )
        if session_token:
            kwargs["aws_session_token"] = session_token

    # -------------------------------------------------------------------------
    # RETRY CONFIGURATION (Fix for ServiceUnavailableException / Throttling)
    # -------------------------------------------------------------------------
    # Standard retries are often insufficient for high-concurrency Bedrock usage.
    # Adaptive mode allows standard retry logic to dynamically adjust for
    # optimal request rates.
    retry_config = Config(
        retries={
            'max_attempts': 10,
            'mode': 'adaptive'
        },
        read_timeout=900,
        connect_timeout=900,
    )
    kwargs["config"] = retry_config

    return boto3.client(**kwargs)


async def call_openai(model, messages, api_key, tools=None, images=None):
    """Call OpenAI with 5-attempt exponential backoff retry loop.

    Args:
        model: GPT model name (e.g. 'gpt-4o')
        messages: List of {"role": ..., "content": ...} dicts
        api_key: OpenAI API key
        tools: Ollama-format tool list (forwarded as OpenAI function definitions)
        images: List of base64 data-URI image strings to attach to the last user message

    Returns:
        (response_text, input_tokens, output_tokens)
    """
    # Inject images into the last user message
    if images:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                messages[i] = dict(messages[i])  # shallow copy
                messages[i]["content"] = _build_openai_image_content(
                    str(messages[i].get("content", "")), images
                )
                break
    OPENAI_TIMEOUT = 180.0
    MAX_RETRIES = 5
    BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]

    payload: dict = {"model": model, "messages": messages}
    if tools:
        # OpenAI uses the same format as our internal Ollama tool spec
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        backoff = BACKOFF_SCHEDULE[attempt - 1]
        try:
            print(f"DEBUG: 🔄 OpenAI call start (attempt {attempt}/{MAX_RETRIES})", flush=True)
            async with httpx.AsyncClient(timeout=OPENAI_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            if resp.status_code in (429, 499, 500, 502, 503, 529):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                print(f"DEBUG: ⏳ OpenAI {resp.status_code} on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    continue
            resp.raise_for_status()
            data = resp.json()
            # Extract actual token usage from the API response
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            # Handle tool_calls response
            choice = data["choices"][0]
            msg = choice.get("message", {})
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                text = json.dumps({
                    "tool": tc["function"]["name"],
                    "arguments": json.loads(tc["function"].get("arguments", "{}"))
                })
                return text, input_tokens, output_tokens
            print(f"DEBUG: ✅ OpenAI call complete (attempt {attempt})", flush=True)
            return msg.get("content", ""), input_tokens, output_tokens
        except httpx.TimeoutException:
            last_error = f"Request timed out ({OPENAI_TIMEOUT}s)"
            print(f"DEBUG: ⏱️ OpenAI timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {str(e)[:200]}"
            print(f"DEBUG: ❌ OpenAI HTTP error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES and e.response.status_code in (429, 499, 500, 502, 503, 529):
                await asyncio.sleep(backoff)
                continue
            break
        except Exception as e:
            last_error = str(e)
            print(f"DEBUG: ⚠️ OpenAI error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue

    error_msg = f"OpenAI LLM Error: All {MAX_RETRIES} attempts failed. Last error: {last_error}"
    print(f"DEBUG: ❌ {error_msg}", flush=True)
    raise LLMError(error_msg)

def _convert_tools_for_anthropic(ollama_tools: list[dict] | None) -> list[dict] | None:
    """Convert Ollama-format tool list to Anthropic tool format.

    Ollama format:
      [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
    Anthropic format:
      [{"name": ..., "description": ..., "input_schema": ...}]
    """
    if not ollama_tools:
        return None

    tools = []
    for t in ollama_tools:
        func = t.get("function", {})
        name = func.get("name", "")
        if not name:
            continue
        tool_def = {
            "name": name,
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
        }
        tools.append(tool_def)

    return tools if tools else None


def _extract_anthropic_response(response) -> str:
    """Extract text or tool call from an Anthropic SDK response.

    Checks for tool_use content blocks first (native tool calling),
    then falls back to text blocks.
    """
    if not response.content:
        return "Error: Empty Anthropic response."

    # Check for tool_use blocks first (native tool calling)
    for block in response.content:
        if block.type == "tool_use":
            return json.dumps({"tool": block.name, "arguments": block.input or {}})

    # Collect text blocks
    text_parts = [block.text for block in response.content if block.type == "text" and block.text]
    if text_parts:
        return "\n".join(text_parts)

    return "Error: Anthropic returned no usable content."


async def call_anthropic(model, messages, system, api_key, tools=None, images=None):
    """Call Anthropic using the official SDK with native tool calling.

    Args:
        model: Claude model name (e.g. 'claude-sonnet-4-20250514')
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts
        system: System instruction text
        api_key: Anthropic API key
        tools: Ollama-format tool list (converted to Anthropic tool definitions)
        images: List of base64 data-URI image strings to attach to the last user message

    Returns:
        (response_text, input_tokens, output_tokens)
    """
    # Inject images into the last user message
    if images:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                messages[i] = dict(messages[i])  # shallow copy
                messages[i]["content"] = _build_anthropic_image_content(
                    str(messages[i].get("content", "")), images
                )
                break
    import anthropic

    ANTHROPIC_TIMEOUT = 180.0  # seconds per attempt (Claude can take >60s for complex prompts)
    MAX_RETRIES = 5

    # --- Input validation to prevent 400 errors ---
    # 1. Filter out messages with empty content
    clean_messages = [
        m for m in (messages or [])
        if m.get("content") and str(m["content"]).strip()
    ]
    # 2. Ensure messages start with "user" role (Claude requirement)
    while clean_messages and clean_messages[0].get("role") != "user":
        clean_messages.pop(0)
    # 3. If no valid messages remain, create a minimal one
    if not clean_messages:
        clean_messages = [{"role": "user", "content": "Hello"}]

    # Convert tools
    anthropic_tools = _convert_tools_for_anthropic(tools)

    # Build kwargs
    kwargs = {
        "model": model,
        "messages": clean_messages,
        "max_tokens": 4096,
    }
    if system and str(system).strip():
        kwargs["system"] = str(system).strip()
    if anthropic_tools:
        kwargs["tools"] = anthropic_tools

    client = anthropic.AsyncAnthropic(
        api_key=api_key,
        timeout=ANTHROPIC_TIMEOUT,
        max_retries=0,  # Disable SDK internal retries — we handle retries ourselves
    )

    BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]  # seconds between retries
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        backoff = BACKOFF_SCHEDULE[attempt - 1]
        try:
            print(f"DEBUG: 🔄 Anthropic call start (attempt {attempt}/{MAX_RETRIES})", flush=True)
            response = await client.messages.create(**kwargs)
            print(f"DEBUG: ✅ Anthropic call complete (attempt {attempt})", flush=True)
            # Extract actual token usage from the SDK response object
            input_tokens = getattr(getattr(response, 'usage', None), 'input_tokens', 0) or 0
            output_tokens = getattr(getattr(response, 'usage', None), 'output_tokens', 0) or 0
            return _extract_anthropic_response(response), input_tokens, output_tokens
        except anthropic.APITimeoutError:
            last_error = f"Request timed out ({ANTHROPIC_TIMEOUT}s)"
            print(f"DEBUG: ⏱️ Anthropic timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue
        except anthropic.APIStatusError as e:
            last_error = f"API error {e.status_code}: {str(e)[:200]}"
            print(f"DEBUG: ❌ Anthropic API error {e.status_code} on attempt {attempt}/{MAX_RETRIES}: {str(e)[:500]}", flush=True)
            # Retry on transient/rate-limit errors (429 rate limit, 499 client disconnect, 5xx server errors, 529 overloaded)
            if attempt < MAX_RETRIES and e.status_code in (429, 499, 500, 502, 503, 529):
                print(f"DEBUG: ⏳ Retrying in {backoff}s...", flush=True)
                await asyncio.sleep(backoff)
                continue
            # Non-retryable error (400, 401, 403, etc.) or last attempt
            break
        except Exception as e:
            last_error = str(e)
            print(f"DEBUG: ⚠️ Anthropic error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue

    error_msg = f"Claude LLM Error: All {MAX_RETRIES} attempts failed. Last error: {last_error}"
    print(f"DEBUG: ❌ {error_msg}", flush=True)
    raise LLMError(error_msg)

def _convert_tools_for_gemini(ollama_tools: list[dict] | None):
    """Convert Ollama-format tool list to Gemini FunctionDeclaration list.

    Ollama format:
      [{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}]
    Gemini format:
      types.Tool(function_declarations=[FunctionDeclaration(...)])
    """
    from google.genai import types

    if not ollama_tools:
        return None

    declarations = []
    for t in ollama_tools:
        func = t.get("function", {})
        name = func.get("name", "")
        if not name:
            continue
        # Clean up the parameters schema — Gemini doesn't accept 'default' in properties
        params = func.get("parameters", {})
        cleaned_params = _clean_schema_for_gemini(params) if params else None
        declarations.append(types.FunctionDeclaration(
            name=name,
            description=func.get("description", ""),
            parameters=cleaned_params,
        ))

    if not declarations:
        return None
    return [types.Tool(function_declarations=declarations)]


def _clean_schema_for_gemini(schema: dict) -> dict:
    """Remove fields from JSON schema that Gemini doesn't support."""
    UNSUPPORTED_KEYS = {"default", "$schema", "additionalProperties"}
    if not isinstance(schema, dict):
        return schema
    cleaned = {}
    for k, v in schema.items():
        if k in UNSUPPORTED_KEYS:
            continue
        if isinstance(v, dict):
            cleaned[k] = _clean_schema_for_gemini(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_schema_for_gemini(i) if isinstance(i, dict) else i for i in v]
        else:
            cleaned[k] = v
    return cleaned


def _convert_messages_for_gemini(messages: list[dict], images: list[str] | None = None):
    """Convert OpenAI-style messages to Gemini Content objects.

    Maps roles: 'user' → 'user', 'assistant' → 'model', 'system' → skip (handled separately).
    If images are provided, they are attached to the last user message.
    """
    from google.genai import types

    contents = []
    # Find the index of the last user message for image injection
    last_user_idx = -1
    filtered = [(msg, idx) for idx, msg in enumerate(messages) if msg.get("role") != "system" and msg.get("content")]
    if images:
        for i, (msg, _) in enumerate(filtered):
            if msg.get("role") == "user":
                last_user_idx = i

    for i, (msg, _) in enumerate(filtered):
        role = msg.get("role", "user")
        text = msg.get("content", "")
        gemini_role = "model" if role == "assistant" else "user"
        parts = [types.Part.from_text(text=text)]

        # Attach images to the last user message
        if images and i == last_user_idx:
            for img in images[:5]:
                mime, b64 = _parse_data_uri(img)
                parts.append(types.Part.from_bytes(
                    data=base64.b64decode(b64),
                    mime_type=mime,
                ))

        contents.append(types.Content(role=gemini_role, parts=parts))
    return contents


def _extract_gemini_response(response) -> str:
    """Extract text or function call from a Gemini response."""
    if not response.candidates:
        return "Error: No response candidates from Gemini."

    candidate = response.candidates[0]

    if candidate.finish_reason and candidate.finish_reason.name == "SAFETY":
        return "Error: Response blocked by Gemini safety filters."

    if not candidate.content or not candidate.content.parts:
        reason = candidate.finish_reason.name if candidate.finish_reason else "UNKNOWN"
        return f"Error: Empty Gemini response. Finish Reason: {reason}"

    # Check for function calls first (native tool calling)
    function_calls = []
    for p in candidate.content.parts:
        if p.function_call:
            fc = p.function_call
            args = dict(fc.args) if fc.args else {}
            function_calls.append({"tool": fc.name, "arguments": args})

    if function_calls:
        # Return the first function call (ReAct loop processes one at a time)
        if len(function_calls) > 1:
            names = [fc["tool"] for fc in function_calls]
            print(f"DEBUG: ⚠️ Gemini returned {len(function_calls)} function calls: {names}. Using first: {names[0]}")
        return json.dumps(function_calls[0])

    # Collect text parts
    text_parts = [p.text for p in candidate.content.parts if p.text]
    if text_parts:
        return "\n".join(text_parts)

    return "Error: Gemini returned no usable content."

# Global singleton Gemini client — reuses connection pool, prevents socket exhaustion
_gemini_client = None


async def call_gemini(model, messages, system, api_key, tools=None, images=None):
    """Call Gemini using the google-genai SDK with native function calling.

    Args:
        model: Gemini model name (e.g. 'gemini-2.0-flash')
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts
        system: System instruction text
        api_key: Gemini API key
        tools: Ollama-format tool list (converted to Gemini FunctionDeclarations)
        images: List of base64 data-URI image strings to attach to the last user message

    Returns:
        (response_text, input_tokens, output_tokens)
    """
    global _gemini_client
    from google import genai
    from google.genai import types

    GEMINI_TIMEOUT = 180.0   # seconds per attempt
    MAX_RETRIES = 5

    if _gemini_client is None:
        _gemini_client = genai.Client(
            api_key=api_key,
            # HTTP timeout 5s above wait_for so wait_for fires first for clean handling
            http_options=types.HttpOptions(timeout=int((GEMINI_TIMEOUT+5) * 1000)),  # seconds
        )

    contents = _convert_messages_for_gemini(messages, images=images)
    gemini_tools = _convert_tools_for_gemini(tools)

    config = types.GenerateContentConfig(
        system_instruction=system,
    )
    if gemini_tools:
        config.tools = gemini_tools

    async def _call(cfg, attempt_label=""):
        print(f"DEBUG: 🔄 Gemini _call start ({attempt_label})", flush=True)
        result = await asyncio.to_thread(
            _gemini_client.models.generate_content,
            model=model,
            contents=contents,
            config=cfg,
        )
        print(f"DEBUG: ✅ Gemini _call complete ({attempt_label})", flush=True)
        return result

    BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]  # seconds between retries
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        backoff = BACKOFF_SCHEDULE[attempt - 1]
        try:
            response = await _call(config, f"attempt {attempt}")
            result = _extract_gemini_response(response)

            # If MALFORMED_FUNCTION_CALL, retry once without tools (forces text response)
            if "MALFORMED_FUNCTION_CALL" in result and gemini_tools:
                print("DEBUG: Gemini MALFORMED_FUNCTION_CALL — retrying without tools")
                config_no_tools = types.GenerateContentConfig(
                    system_instruction=system,
                )
                response = await _call(config_no_tools, "no-tools retry")
                result = _extract_gemini_response(response)

            # Extract actual token usage from Gemini response metadata
            input_tokens = 0
            output_tokens = 0
            try:
                um = getattr(response, 'usage_metadata', None)
                if um:
                    input_tokens = getattr(um, 'prompt_token_count', 0) or 0
                    output_tokens = getattr(um, 'candidates_token_count', 0) or 0
            except Exception:
                pass
            return result, input_tokens, output_tokens

        # except asyncio.TimeoutError:
        #     last_error = f"Request timed out ({GEMINI_TIMEOUT}s)"
        #     print(f"DEBUG: ⚠️ Gemini timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...")
        #     if attempt < MAX_RETRIES:
        #         await asyncio.sleep(backoff)
        #         continue
        except Exception as e:
            last_error = str(e)
            print(f"DEBUG: ⚠️ Unexpected {type(e).__name__}: {vars(e) if hasattr(e, '__dict__') else e}", flush=True)
            print(f"DEBUG: ⚠️ Gemini error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                print(f"DEBUG: ⏳ Retrying in {backoff}s...", flush=True)
                await asyncio.sleep(backoff)
                continue

    error_msg = f"Gemini LLM Error: All {MAX_RETRIES} attempts failed. Last error: {last_error}"
    print(f"DEBUG: ❌ {error_msg}", flush=True)
    raise LLMError(error_msg)

async def call_grok(model, messages, system, api_key, tools=None, images=None):
    """Call xAI Grok via its OpenAI-compatible API with 5-attempt exponential backoff.

    Args:
        model: Grok model name (e.g. 'grok-3', 'grok-3-mini')
        messages: List of {"role": ..., "content": ...} dicts
        system: System instruction text
        api_key: xAI API key (starts with 'xai-')
        tools: Ollama-format tool list (Grok is OpenAI-compatible for function calling)
        images: List of base64 data-URI image strings to attach to the last user message

    Returns:
        (response_text, input_tokens, output_tokens)
    """
    GROK_TIMEOUT = 180.0
    MAX_RETRIES = 5
    BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]

    # Build full messages list with system prompt
    full_messages = []
    if system and str(system).strip():
        full_messages.append({"role": "system", "content": str(system).strip()})
    full_messages.extend(messages or [])

    # Inject images into the last user message (Grok is OpenAI-compatible)
    if images:
        for i in range(len(full_messages) - 1, -1, -1):
            if full_messages[i].get("role") == "user":
                full_messages[i] = dict(full_messages[i])
                full_messages[i]["content"] = _build_openai_image_content(
                    str(full_messages[i].get("content", "")), images
                )
                break

    payload: dict = {"model": model, "messages": full_messages, "max_tokens": 4096}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        backoff = BACKOFF_SCHEDULE[attempt - 1]
        try:
            print(f"DEBUG: 🔄 Grok call start (attempt {attempt}/{MAX_RETRIES})", flush=True)
            async with httpx.AsyncClient(timeout=GROK_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            if resp.status_code in (429, 499, 500, 502, 503, 529):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                print(f"DEBUG: ⏳ Grok {resp.status_code} on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    continue
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            choice = data["choices"][0]
            msg = choice.get("message", {})
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                text = json.dumps({
                    "tool": tc["function"]["name"],
                    "arguments": json.loads(tc["function"].get("arguments", "{}"))
                })
                return text, input_tokens, output_tokens
            print(f"DEBUG: ✅ Grok call complete (attempt {attempt})", flush=True)
            return msg.get("content", ""), input_tokens, output_tokens
        except httpx.TimeoutException:
            last_error = f"Request timed out ({GROK_TIMEOUT}s)"
            print(f"DEBUG: ⏱️ Grok timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {str(e)[:200]}"
            print(f"DEBUG: ❌ Grok HTTP error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES and e.response.status_code in (429, 499, 500, 502, 503, 529):
                await asyncio.sleep(backoff)
                continue
            break
        except Exception as e:
            last_error = str(e)
            print(f"DEBUG: ⚠️ Grok error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue

    error_msg = f"Grok LLM Error: All {MAX_RETRIES} attempts failed. Last error: {last_error}"
    print(f"DEBUG: ❌ {error_msg}", flush=True)
    raise LLMError(error_msg)


async def call_deepseek(model, messages, system, api_key, tools=None, images=None):
    """Call DeepSeek via its OpenAI-compatible API with 5-attempt exponential backoff.

    Args:
        model: DeepSeek model name (e.g. 'deepseek-chat', 'deepseek-reasoner')
        messages: List of {"role": ..., "content": ...} dicts
        system: System instruction text
        api_key: DeepSeek API key
        tools: Ollama-format tool list (deepseek-chat supports function calling;
               deepseek-reasoner does NOT — tools are silently dropped for it)
        images: List of base64 data-URI image strings (NOT SUPPORTED — silently dropped)

    Returns:
        (response_text, input_tokens, output_tokens)
    """
    # DeepSeek does not support vision — drop images with a warning
    if images:
        print(f"DEBUG: ⚠️ DeepSeek does not support images. {len(images)} image(s) will be dropped.", flush=True)
    DEEPSEEK_TIMEOUT = 180.0
    MAX_RETRIES = 5
    BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]

    # Build full messages list with system prompt
    full_messages = []
    if system and str(system).strip():
        full_messages.append({"role": "system", "content": str(system).strip()})
    full_messages.extend(messages or [])

    payload: dict = {"model": model, "messages": full_messages, "max_tokens": 4096}
    # DeepSeek-Reasoner does not support function calling
    if tools and "reasoner" not in model.lower():
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        backoff = BACKOFF_SCHEDULE[attempt - 1]
        try:
            print(f"DEBUG: 🔄 DeepSeek call start (attempt {attempt}/{MAX_RETRIES})", flush=True)
            async with httpx.AsyncClient(timeout=DEEPSEEK_TIMEOUT) as client:
                resp = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
            if resp.status_code in (429, 499, 500, 502, 503, 529):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                print(f"DEBUG: ⏳ DeepSeek {resp.status_code} on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    continue
            resp.raise_for_status()
            data = resp.json()
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            choice = data["choices"][0]
            msg = choice.get("message", {})
            if msg.get("tool_calls"):
                tc = msg["tool_calls"][0]
                text = json.dumps({
                    "tool": tc["function"]["name"],
                    "arguments": json.loads(tc["function"].get("arguments", "{}"))
                })
                return text, input_tokens, output_tokens
            print(f"DEBUG: ✅ DeepSeek call complete (attempt {attempt})", flush=True)
            return msg.get("content", ""), input_tokens, output_tokens
        except httpx.TimeoutException:
            last_error = f"Request timed out ({DEEPSEEK_TIMEOUT}s)"
            print(f"DEBUG: ⏱️ DeepSeek timeout on attempt {attempt}/{MAX_RETRIES}. Retrying in {backoff}s...", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}: {str(e)[:200]}"
            print(f"DEBUG: ❌ DeepSeek HTTP error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES and e.response.status_code in (429, 499, 500, 502, 503, 529):
                await asyncio.sleep(backoff)
                continue
            break
        except Exception as e:
            last_error = str(e)
            print(f"DEBUG: ⚠️ DeepSeek error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
                continue

    error_msg = f"DeepSeek LLM Error: All {MAX_RETRIES} attempts failed. Last error: {last_error}"
    print(f"DEBUG: ❌ {error_msg}", flush=True)
    raise LLMError(error_msg)


async def call_bedrock(model_id, messages, system, region, settings, images=None):
    """Call AWS Bedrock with 5-attempt exponential backoff retry loop.

    Prefers the Converse API (standardized); falls back to InvokeModel for older models.
    Raises LLMError on final failure after all retries.
    """
    MAX_RETRIES = 5
    BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]

    # Bedrock requires the exact model ID (e.g., anthropic.claude-3-5-sonnet-20240620-v1:0)
    # We strip the 'bedrock.' prefix if present
    real_model_id = model_id.replace("bedrock.", "")

    # Some Bedrock models require an inference profile (no on-demand throughput).
    invocation_model_id = real_model_id
    inference_profile = (settings.get("bedrock_inference_profile") or "").strip()
    if inference_profile:
        if inference_profile.startswith("bedrock."):
            inference_profile = inference_profile.replace("bedrock.", "", 1)
        invocation_model_id = inference_profile

    bedrock = _make_aws_client("bedrock-runtime", region, settings)

    # Normalize messages to Bedrock Converse content-block format
    normalized_messages = []
    # Find the last user message index for image injection
    all_msgs = [m for m in (messages or []) if m.get("role") in ("user", "assistant")]
    last_user_idx = -1
    if images:
        for idx_m, m in enumerate(all_msgs):
            if m.get("role") == "user":
                last_user_idx = idx_m

    for idx_m, m in enumerate(all_msgs):
        role = m.get("role")
        content = m.get("content")
        blocks = []
        if isinstance(content, str):
            blocks.append({"text": content})
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and "text" in b:
                    blocks.append({"text": str(b.get("text"))})
                elif isinstance(b, dict) and b.get("type") == "text" and "text" in b:
                    blocks.append({"text": str(b.get("text"))})
                else:
                    blocks.append({"text": str(b)})
        else:
            blocks.append({"text": str(content)})

        # Inject images into the last user message
        if images and idx_m == last_user_idx:
            for img in images[:5]:
                mime, b64 = _parse_data_uri(img)
                # Map MIME to Bedrock format name
                fmt_map = {"image/png": "png", "image/jpeg": "jpeg", "image/gif": "gif", "image/webp": "webp"}
                fmt = fmt_map.get(mime, "png")
                blocks.append({"image": {"format": fmt, "source": {"bytes": base64.b64decode(b64)}}})

        normalized_messages.append({"role": role, "content": blocks})

    system_blocks = []
    if system and str(system).strip():
        system_blocks = [{"text": str(system)}]

    async def _converse_call():
        def _run():
            return bedrock.converse(
                modelId=invocation_model_id,
                messages=normalized_messages,
                system=system_blocks,
                inferenceConfig={"maxTokens": 4096},
            )
        return await asyncio.to_thread(_run)

    async def _invoke_model_call():
        anthropic_messages = []
        for m in normalized_messages:
            anthropic_messages.append({
                "role": m["role"],
                "content": [{"type": "text", "text": b.get("text", "")} for b in (m.get("content") or [])],
            })
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "system": str(system or ""),
            "messages": anthropic_messages,
        }
        def _run():
            return bedrock.invoke_model(
                body=json.dumps(payload).encode("utf-8"),
                modelId=invocation_model_id,
                accept="application/json",
                contentType="application/json",
            )
        return await asyncio.to_thread(_run)

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        backoff = BACKOFF_SCHEDULE[attempt - 1]
        try:
            print(f"DEBUG: 🔄 Bedrock call start (attempt {attempt}/{MAX_RETRIES})", flush=True)
            if hasattr(bedrock, "converse"):
                try:
                    resp = await _converse_call()
                    msg = (((resp or {}).get("output") or {}).get("message") or {})
                    content = msg.get("content") or []
                    if content and isinstance(content, list) and isinstance(content[0], dict):
                        print(f"DEBUG: ✅ Bedrock (converse) complete (attempt {attempt})", flush=True)
                        return content[0].get("text", "")
                    return ""
                except Exception as converse_err:
                    msg_str = str(converse_err)
                    if "on-demand throughput isn't supported" in msg_str:
                        raise LLMError(
                            "Bedrock model requires an inference profile (no on-demand throughput). "
                            "Set Bedrock Inference Profile in settings, or pick a different model."
                        )
                    print(f"DEBUG: Bedrock converse failed (attempt {attempt}), falling back to invoke_model: {converse_err}")
                    # Fall through to InvokeModel
                    resp = await _invoke_model_call()
                    response_body = json.loads(resp.get("body").read()) if resp and resp.get("body") else {}
                    content = response_body.get("content") or []
                    if content and isinstance(content, list) and isinstance(content[0], dict):
                        print(f"DEBUG: ✅ Bedrock (invoke_model) complete (attempt {attempt})", flush=True)
                        return content[0].get("text", "")
                    return ""
            else:
                resp = await _invoke_model_call()
                response_body = json.loads(resp.get("body").read()) if resp and resp.get("body") else {}
                content = response_body.get("content") or []
                if content and isinstance(content, list) and isinstance(content[0], dict):
                    print(f"DEBUG: ✅ Bedrock (invoke_model) complete (attempt {attempt})", flush=True)
                    return content[0].get("text", "")
                return ""
        except LLMError:
            raise  # Non-retryable (config error)
        except Exception as e:
            last_error = str(e)
            print(f"DEBUG: ⚠️ Bedrock error on attempt {attempt}/{MAX_RETRIES}: {e}", flush=True)
            if attempt < MAX_RETRIES:
                print(f"DEBUG: ⏳ Retrying Bedrock in {backoff}s...", flush=True)
                await asyncio.sleep(backoff)
                continue

    error_msg = f"Bedrock LLM Error: All {MAX_RETRIES} attempts failed. Last error: {last_error}"
    print(f"DEBUG: ❌ {error_msg}", flush=True)
    raise LLMError(error_msg)


def _messages_to_transcript(messages: list[dict] | None) -> str:
    """Lossy conversion of role/content messages to plain text for providers that only accept a single prompt."""
    if not messages:
        return ""
    lines: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        role = (m.get("role") or "").strip().lower()
        content = m.get("content")
        if isinstance(content, list):
            # Best-effort concatenate any text blocks
            parts: list[str] = []
            for p in content:
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    parts.append(p["text"])
            text = "\n".join(parts).strip()
        else:
            text = (content or "").strip() if isinstance(content, str) else ""

        if not text:
            continue

        if role == "user":
            label = "User"
        elif role == "assistant":
            label = "Assistant"
        elif role:
            label = role.title()
        else:
            label = "Message"
        lines.append(f"{label}: {text}")
    return "\n".join(lines)


async def generate_response(
    prompt_msg,
    sys_prompt,
    mode,
    current_model,
    current_settings,
    tools=None,
    history_messages=None,
    memory_context_text: str = "",
    # Usage tracking context — passed by react_engine & orchestration steps
    session_id: str | None = None,
    agent_id: str | None = None,
    source: str = "chat",
    run_id: str | None = None,
    tool_name: str | None = None,
    images: list[str] | None = None,
):
    """
    Unified LLM dispatch function. Routes to the appropriate provider
    based on mode and current_model. Logs token usage and cost after
    every successful call via usage_tracker.
    """
    import time as _time
    from core import usage_tracker

    augmented_system = (sys_prompt or "").strip()
    if memory_context_text and memory_context_text.strip():
        augmented_system = f"{augmented_system}\n\n{memory_context_text.strip()}".strip()

    # Build the full context string for char-count tracking
    _all_msgs = []
    if history_messages:
        _all_msgs.extend(history_messages)
    _all_msgs.append({"role": "user", "content": prompt_msg})
    context_chars = sum(len(str(m.get("content", ""))) for m in _all_msgs) + len(augmented_system)

    _t0 = _time.time()
    result_text = ""
    input_tokens = 0
    output_tokens = 0

    if mode in ["cloud", "bedrock"]:
        try:
            # Construct messages list for cloud providers that support it
            messages = []
            if history_messages:
                messages.extend(history_messages)
            messages.append({"role": "user", "content": prompt_msg})

            if current_model.startswith("gpt"):
                result_text, input_tokens, output_tokens = await call_openai(
                    current_model,
                    [{"role": "system", "content": augmented_system}] + messages,
                    current_settings.get("openai_key"),
                    tools=tools,
                    images=images,
                )
            elif current_model.startswith("claude"):
                result_text, input_tokens, output_tokens = await call_anthropic(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("anthropic_key"),
                    tools=tools,
                    images=images,
                )
            elif current_model.startswith("gemini") or current_model.startswith("gemma") or current_model.startswith("lyria"):
                result_text, input_tokens, output_tokens = await call_gemini(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("gemini_key"),
                    tools=tools,
                    images=images,
                )
            elif current_model.startswith("bedrock"):
                result_text = await call_bedrock(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("aws_region"),
                    current_settings,
                    images=images,
                )
                # Bedrock does not surface token counts the same way — fall back to heuristic
                input_tokens = usage_tracker.estimate_tokens_from_text(
                    augmented_system + " ".join(str(m.get("content", "")) for m in messages)
                )
                output_tokens = usage_tracker.estimate_tokens_from_text(result_text)
            elif current_model.startswith("grok"):
                result_text, input_tokens, output_tokens = await call_grok(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("grok_key"),
                    tools=tools,
                    images=images,
                )
            elif current_model.startswith("deepseek"):
                result_text, input_tokens, output_tokens = await call_deepseek(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("deepseek_key"),
                    tools=tools,
                    images=images,
                )
            else:
                return "Error: Unknown cloud model selected."
        except LLMError:
            # LLM errors must propagate — do NOT swallow them.
            # Orchestration engine will catch this and stop execution.
            raise
        except Exception as e:
            return f"Cloud API Error: {str(e)}"
    
    else:
        # Local Ollama
        async with httpx.AsyncClient() as client:
            try:
                # Try specific Ollama Tool Call format if tools are provided
                if tools:
                    print(f"DEBUG: Calling Ollama /api/chat with tools...", flush=True)

                    # Construct full message history
                    # 1. System Prompt
                    messages = [{"role": "system", "content": augmented_system}]

                    # 2. History (if available)
                    if history_messages:
                        messages.extend(history_messages)

                    # 3. Current User Message
                    user_msg: dict = {"role": "user", "content": prompt_msg}
                    # Ollama supports images as base64 strings (no data URI prefix)
                    if images:
                        user_msg["images"] = [_parse_data_uri(img)[1] for img in images[:5]]
                    messages.append(user_msg)

                    response = await client.post(
                        f"{_ollama_base_url()}/api/chat",
                        json={
                            "model": current_model,
                            "messages": messages,
                            "tools": tools,
                            "stream": False
                        },
                        timeout=180.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    msg = data.get("message", {})

                    # Check for native tool calls
                    if "tool_calls" in msg and msg["tool_calls"]:
                        # Convert Ollama native tool call to our internal JSON format
                        tc = msg["tool_calls"][0]
                        print(f"DEBUG: Native Tool Call received: {tc['function']['name']}", flush=True)
                        result_text = json.dumps({
                            "tool": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        })
                    else:
                        result_text = msg.get("content", "")

                    # Ollama eval_count / prompt_eval_count (available when stream=False)
                    input_tokens = data.get("prompt_eval_count", 0) or usage_tracker.estimate_tokens_from_text(prompt_msg)
                    output_tokens = data.get("eval_count", 0) or usage_tracker.estimate_tokens_from_text(result_text)

                else:
                    # Fallback to generate if no tools or tools failed (Old behavior)
                    print(f"DEBUG: Calling Ollama /api/generate (Legacy Mode)...", flush=True)

                    prompt_for_generate = prompt_msg
                    if history_messages:
                        prior = _messages_to_transcript(history_messages)
                        if prior:
                            prompt_for_generate = f"Conversation so far:\n{prior}\n\nUser: {prompt_msg}".strip()

                    response = await client.post(
                        f"{_ollama_base_url()}/api/generate",
                        json={
                            "model": current_model,
                            "prompt": prompt_for_generate,
                            "system": augmented_system,
                            "stream": False
                        },
                        timeout=180.0
                    )
                    response.raise_for_status()
                    data = response.json()
                    result_text = data.get("response", "")
                    input_tokens = data.get("prompt_eval_count", 0) or usage_tracker.estimate_tokens_from_text(prompt_for_generate)
                    output_tokens = data.get("eval_count", 0) or usage_tracker.estimate_tokens_from_text(result_text)

            except Exception as e:
                return f"Local Agent Error: {e}"

    # ── Log usage (fire-and-forget, never raises) ────────────────────────────
    try:
        provider = detect_provider_from_model(current_model)
        usage_tracker.log_usage(
            model=current_model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            context_chars=context_chars,
            session_id=session_id,
            agent_id=agent_id,
            source=source,
            run_id=run_id,
            tool_name=tool_name,
            latency_seconds=_time.time() - _t0,
        )
    except Exception as _track_err:
        print(f"DEBUG usage_tracker: log_usage failed (non-fatal): {_track_err}", flush=True)

    return result_text


# ─── Embedding Helpers ──────────────────────────────────────────────────────

async def embed_batch(texts: list[str], model: str, settings: dict) -> list[list[float]]:
    """Unified embedding function that routes to the appropriate provider.

    Optional settings key ``__embed_output_dim`` (int) is forwarded to
    providers that support dimensionality control (currently Gemini).
    """
    provider = detect_provider_from_model(model)
    output_dim: int | None = settings.get("__embed_output_dim")

    if provider == "openai":
        return await _embed_openai(texts, model, settings.get("openai_key", ""))
    elif provider == "gemini":
        kwargs = {} if output_dim is None else {"output_dim": output_dim}
        return await _embed_gemini(texts, model, settings.get("gemini_key", ""), **kwargs)
    elif provider == "bedrock":
        return await _embed_bedrock(texts, model, settings)
    elif provider == "ollama":
        return await _embed_ollama(texts, model)
    else:
        print(f"DEBUG: Unknown provider '{provider}' for embedding model '{model}'")
        return [[0.0] * 768 for _ in range(len(texts))]


async def _embed_openai(texts: list[str], model: str, api_key: str) -> list[list[float]]:
    if not api_key:
        return [[0.0] * 1536 for _ in range(len(texts))]
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            # OpenAI returns embeddings in the same order as input
            return [item["embedding"] for item in data["data"]]
    except Exception as e:
        print(f"ERROR: OpenAI embedding failed: {e}")
        return [[0.0] * 1536 for _ in range(len(texts))]


async def _embed_gemini(
    texts: list[str], model: str, api_key: str, output_dim: int = 768
) -> list[list[float]]:
    if not api_key:
        return [[0.0] * output_dim for _ in range(len(texts))]

    from google import genai
    from google.genai import types

    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=api_key)

    try:
        # Specify output_dimensionality so Gemini returns exactly `output_dim` dims
        # (uses Matryoshka truncation — the first N dims are the best N-dim representation).
        # Without this, the API returns the full 3072-dim vector which exceeds
        # pgvector's 2000-dim HNSW limit.
        result = await asyncio.to_thread(
            _gemini_client.models.embed_content,
            model=model,
            contents=texts,
            config=types.EmbedContentConfig(output_dimensionality=output_dim),
        )
        if not result.embeddings:
            return [[0.0] * output_dim for _ in range(len(texts))]
        return [list(em.values) for em in result.embeddings]
    except Exception as e:
        print(f"ERROR: Gemini embedding failed: {e}")
        return [[0.0] * output_dim for _ in range(len(texts))]


async def _embed_bedrock(texts: list[str], model: str, settings: dict) -> list[list[float]]:
    region = settings.get("aws_region", "us-east-1")
    bedrock = _make_aws_client("bedrock-runtime", region, settings)
    # Strip the 'bedrock.' UI prefix to get the raw Bedrock model ID
    real_model_id = model.replace("bedrock.", "", 1)

    embeddings = []
    for text in texts:
        try:
            if "titan" in real_model_id:
                # Titan Embed v1 and v2 both use inputText; v2 also supports
                # embeddingTypes but the default (float) is fine here.
                payload = json.dumps({"inputText": text})
            elif "cohere" in real_model_id:
                # Cohere Embed v3 via Bedrock expects a texts array + input_type
                payload = json.dumps({
                    "texts": [text[:2048]],
                    "input_type": "search_document",
                    "truncate": "END",
                })
            else:
                # Generic fallback — try the Titan-style inputText payload
                payload = json.dumps({"inputText": text})

            def _run(pid=real_model_id, body=payload):
                return bedrock.invoke_model(
                    body=body,
                    modelId=pid,
                    accept="application/json",
                    contentType="application/json",
                )

            resp = await asyncio.to_thread(_run)
            body_parsed = json.loads(resp.get("body").read())

            if "titan" in real_model_id:
                # Titan v2 may wrap embeddings under embeddingsByType; fall back to
                # top-level 'embedding' key used by v1.
                emb = body_parsed.get("embedding") or []
                embeddings.append(emb)
            elif "cohere" in real_model_id:
                # Cohere returns {"embeddings": [[...]]}
                embs = body_parsed.get("embeddings", [[]])
                embeddings.append(embs[0] if embs else [])
            else:
                embeddings.append(body_parsed.get("embedding", []))

        except Exception as e:
            err_str = str(e)
            if "unknown model" in err_str.lower() or "resourcenotfound" in err_str.lower():
                print(
                    f"ERROR: Bedrock embedding — model '{real_model_id}' not found in "
                    f"region '{region}'. Ensure the model is enabled in the AWS console "
                    f"and, if it requires on-demand throughput via an inference profile, "
                    f"set 'Bedrock Inference Profile' in Settings.\nOriginal error: {e}"
                )
            else:
                print(f"ERROR: Bedrock embedding failed for '{real_model_id}': {e}")
            embeddings.append([])

    return embeddings


async def _embed_ollama(texts: list[str], model: str) -> list[list[float]]:
    url = f"{_ollama_base_url()}/api/embed"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json={"model": model, "input": texts})
            if resp.status_code != 200:
                # Fallback for older Ollama versions
                url_legacy = f"{_ollama_base_url()}/api/embeddings"
                embeddings = []
                for t in texts:
                    r = await client.post(url_legacy, json={"model": model, "prompt": t})
                    embeddings.append(r.json().get("embedding", []))
                return embeddings
            
            data = resp.json()
            return data.get("embeddings", [])
    except Exception as e:
        print(f"ERROR: Ollama embedding failed: {e}")
        return [[0.0] * 768 for _ in range(len(texts))]
