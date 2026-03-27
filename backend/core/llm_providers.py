"""
LLM provider API callers (OpenAI, Anthropic, Gemini, Bedrock, Ollama).
Extracted from server.py to eliminate duplication between chat() and chat_stream().
"""
import os
import json
import asyncio
import httpx
import boto3
from botocore.config import Config


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

    Returns 'cloud' for OpenAI/Anthropic/Gemini models, 'bedrock' for Bedrock,
    and 'local' for anything else (assumed to be Ollama).
    """
    if not model_name:
        return "local"
    m = model_name.lower()
    if m.startswith("gpt"):
        return "cloud"
    if m.startswith("claude"):
        return "cloud"
    if m.startswith("gemini"):
        return "cloud"
    if m.startswith("bedrock"):
        return "bedrock"
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
    if m.startswith("gemini"):
        return "gemini"
    if m.startswith("bedrock"):
        return "bedrock"
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


async def call_openai(model, messages, api_key):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages},
            timeout=180.0
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

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


async def call_anthropic(model, messages, system, api_key, tools=None):
    """Call Anthropic using the official SDK with native tool calling.

    Args:
        model: Claude model name (e.g. 'claude-sonnet-4-20250514')
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts
        system: System instruction text
        api_key: Anthropic API key
        tools: Ollama-format tool list (converted to Anthropic tool definitions)
    """
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
            return _extract_anthropic_response(response)
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


def _convert_messages_for_gemini(messages: list[dict]):
    """Convert OpenAI-style messages to Gemini Content objects.

    Maps roles: 'user' → 'user', 'assistant' → 'model', 'system' → skip (handled separately).
    """
    from google.genai import types

    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        text = msg.get("content", "")
        if not text or role == "system":
            continue
        gemini_role = "model" if role == "assistant" else "user"
        contents.append(types.Content(
            role=gemini_role,
            parts=[types.Part.from_text(text=text)]
        ))
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


async def call_gemini(model, messages, system, api_key, tools=None):
    """Call Gemini using the google-genai SDK with native function calling.

    Args:
        model: Gemini model name (e.g. 'gemini-2.0-flash')
        messages: List of {"role": "user"/"assistant", "content": "..."} dicts
        system: System instruction text
        api_key: Gemini API key
        tools: Ollama-format tool list (converted to Gemini FunctionDeclarations)
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

    contents = _convert_messages_for_gemini(messages)
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

            return result

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

async def call_bedrock(model_id, messages, system, region, settings):
    # Bedrock requires the exact model ID (e.g., anthropic.claude-3-5-sonnet-20240620-v1:0)
    # We strip the 'bedrock.' prefix if present
    real_model_id = model_id.replace("bedrock.", "")

    # Some Bedrock models require an inference profile (no on-demand throughput).
    # If provided, we invoke using the inference profile ID/ARN as modelId.
    invocation_model_id = real_model_id
    inference_profile = (settings.get("bedrock_inference_profile") or "").strip()
    if inference_profile:
        # Users may paste it with a bedrock. prefix from the UI list.
        if inference_profile.startswith("bedrock."):
            inference_profile = inference_profile.replace("bedrock.", "", 1)
        invocation_model_id = inference_profile
    
    # Convert messages to Bedrock Converse API format or InvokeModel
    # Using Converse API (standardized) is preferred for newer models
    
    bedrock = _make_aws_client("bedrock-runtime", region, settings)

    # Normalize messages to a content-block list.
    # For Bedrock Converse, content blocks are like: {"text": "..."}
    # For Anthropic InvokeModel, blocks are like: {"type": "text", "text": "..."}
    normalized_messages = []
    for m in (messages or []):
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, str):
            normalized_messages.append({"role": role, "content": [{"text": content}]})
        elif isinstance(content, list):
            # Best effort: if caller already provided blocks, keep them but coerce to Converse schema
            blocks = []
            for b in content:
                if isinstance(b, dict) and "text" in b:
                    blocks.append({"text": str(b.get("text"))})
                elif isinstance(b, dict) and b.get("type") == "text" and "text" in b:
                    blocks.append({"text": str(b.get("text"))})
                else:
                    blocks.append({"text": str(b)})
            normalized_messages.append({"role": role, "content": blocks})
        else:
            normalized_messages.append({"role": role, "content": [{"text": str(content)}]})

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
        # InvokeModel using Anthropic Messages schema
        anthropic_messages = []
        for m in normalized_messages:
            anthropic_messages.append(
                {
                    "role": m["role"],
                    "content": [{"type": "text", "text": b.get("text", "")} for b in (m.get("content") or [])],
                }
            )

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

    # Prefer Converse if available; it avoids many per-model JSON schema mismatches.
    try:
        if hasattr(bedrock, "converse"):
            resp = await _converse_call()
            msg = (((resp or {}).get("output") or {}).get("message") or {})
            content = msg.get("content") or []
            if content and isinstance(content, list) and isinstance(content[0], dict):
                return content[0].get("text", "")
            return ""
    except Exception as e:
        message = str(e)
        if "on-demand throughput isn't supported" in message or "on-demand throughput isn't supported" in message:
            raise RuntimeError(
                "Bedrock model requires an inference profile (no on-demand throughput). "
                "Set settings.bedrock_inference_profile to an inference profile ID/ARN that includes this model, "
                "or pick a different Bedrock model that supports on-demand throughput."
            )
        # Fall back to InvokeModel; keep original exception in server logs.
        print(f"Bedrock converse failed, falling back to invoke_model: {e}")

    try:
        resp = await _invoke_model_call()
        response_body = json.loads(resp.get("body").read()) if resp and resp.get("body") else {}
        content = response_body.get("content") or []
        if content and isinstance(content, list) and isinstance(content[0], dict):
            return content[0].get("text", "")
        return ""
    except Exception as e:
        message = str(e)
        if "on-demand throughput isn't supported" in message or "on-demand throughput isn't supported" in message:
            raise RuntimeError(
                "Bedrock model requires an inference profile (no on-demand throughput). "
                "Set settings.bedrock_inference_profile to an inference profile ID/ARN that includes this model, "
                "or pick a different Bedrock model that supports on-demand throughput."
            )
        raise


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
):
    """
    Unified LLM dispatch function. Routes to the appropriate provider
    based on mode and current_model.
    """
    augmented_system = (sys_prompt or "").strip()
    if memory_context_text and memory_context_text.strip():
        augmented_system = f"{augmented_system}\n\n{memory_context_text.strip()}".strip()

    if mode in ["cloud", "bedrock"]:
        try:
            # Construct messages list for cloud providers that support it
            messages = []
            if history_messages:
                messages.extend(history_messages)
            messages.append({"role": "user", "content": prompt_msg})

            if current_model.startswith("gpt"):
                return await call_openai(
                    current_model,
                    [{"role": "system", "content": augmented_system}] + messages,
                    current_settings.get("openai_key"),
                )
            elif current_model.startswith("claude"):
                return await call_anthropic(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("anthropic_key"),
                    tools=tools,
                )
            elif current_model.startswith("gemini"):
                return await call_gemini(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("gemini_key"),
                    tools=tools,
                )
            elif current_model.startswith("bedrock"):
                return await call_bedrock(
                    current_model,
                    messages,
                    augmented_system,
                    current_settings.get("aws_region"),
                    current_settings,
                )
            else:
                return "Error: Unknown cloud model selected."
        except LLMError:
            # LLM errors must propagate — do NOT swallow them.
            # Orchestration engine will catch this and stop execution.
            raise
        except Exception as e:
            return f"Cloud API Error: {str(e)}"
    
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
                messages.append({"role": "user", "content": prompt_msg})

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
                    return json.dumps({
                        "tool": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"]
                    })

                return msg.get("content", "")

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
            return response.json().get("response", "")
        except Exception as e:
            return f"Local Agent Error: {e}"
