"""Lightweight interactive setup wizard for Synapse.

This writes `settings.json` into the data directory and asks for a
few common configuration options. It's intentionally small so it
works when the package is installed via `pip`.
"""
import json
import os
from pathlib import Path
import sys

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent  # project root (synapse-ai/)
DEFAULT_DATA_DIR = Path.home() / ".synapse" / "data"

_raw_data_dir = os.getenv("SYNAPSE_DATA_DIR", str(DEFAULT_DATA_DIR))
if not os.path.isabs(_raw_data_dir):
    DATA_DIR = (ROOT_DIR / _raw_data_dir).resolve()
else:
    DATA_DIR = Path(_raw_data_dir).resolve()

SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "agent_name": "Synapse",
    "model": "",
    "mode": "cloud",
    "openai_key": "",
    "anthropic_key": "",
    "gemini_key": "",
    "google_maps_api_key": "",
    "bedrock_api_key": "",
    "bedrock_inference_profile": "",
    "embedding_model": "",
    "aws_access_key_id": "",
    "aws_secret_access_key": "",
    "aws_session_token": "",
    "aws_region": "us-east-1",
    "sql_connection_string": "",
    "ollama_base_url": "",
    "n8n_url": "http://localhost:5678",
    "n8n_api_key": "",
    "n8n_table_id": "",
    "global_config": {},
    "vault_enabled": True,
    "vault_threshold": 100000,
    "coding_agent_enabled": False,
    "report_agent_enabled": False,
}


def _ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val if val else default


def _ask_yn(prompt, default="n"):
    hint = "(Y/n)" if default.lower() == "y" else "(y/N)"
    val = _ask(f"{prompt} {hint}", default).lower()
    return val in ("y", "yes")


def _ask_choice(prompt, options):
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        raw = _ask(prompt)
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        print(f"Enter a number between 1 and {len(options)}.")


def load_settings():
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE) as f:
            saved = json.load(f)
        return {**DEFAULT_SETTINGS, **saved}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(cfg):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(cfg, f, indent=4)


def run():
    print("\nSynapse — Interactive Setup (lightweight)")
    cfg = load_settings()

    print("\nGeneral")
    cfg["agent_name"] = _ask("Agent name", cfg.get("agent_name", "Synapse"))

    print("\nAgent features")
    cfg["coding_agent_enabled"] = _ask_yn("Enable Coding Agent?", "n")
    cfg["report_agent_enabled"] = _ask_yn("Enable Report Agent?", "n")

    print("\nLLM Provider (you can fill keys later)")
    providers = ["Ollama (local)", "Gemini", "OpenAI", "Claude (Anthropic)", "Bedrock (AWS)", "Skip for now"]
    choice = _ask_choice("Select provider", providers)
    if choice.startswith("Ollama"):
        cfg["mode"] = "local"
        cfg["ollama_base_url"] = _ask("Ollama base URL", cfg.get("ollama_base_url", "http://127.0.0.1:11434"))
        cfg["model"] = _ask("Model name", cfg.get("model", ""))
    elif choice == "Gemini":
        cfg["mode"] = "cloud"
        cfg["gemini_key"] = _ask("Gemini API key", cfg.get("gemini_key", ""))
    elif choice == "OpenAI":
        cfg["mode"] = "cloud"
        cfg["openai_key"] = _ask("OpenAI API key", cfg.get("openai_key", ""))
    elif choice == "Claude (Anthropic)":
        cfg["mode"] = "cloud"
        cfg["anthropic_key"] = _ask("Anthropic API key", cfg.get("anthropic_key", ""))
    elif choice == "Bedrock (AWS)":
        cfg["mode"] = "cloud"
        cfg["bedrock_api_key"] = _ask("Bedrock API key", cfg.get("bedrock_api_key", ""))
        cfg["aws_region"] = _ask("AWS region", cfg.get("aws_region", "us-east-1"))

    print("\nExample data")
    if _ask_yn("Import example data (if available)?", "y"):
        # Look for *.example.json files next to package, and in backend/data
        possible_dirs = [PACKAGE_DIR.parent / "backend" / "data", PACKAGE_DIR.parent / "data", DATA_DIR]
        imported = False
        for d in possible_dirs:
            if not d.exists():
                continue
            for src in d.glob("*.example.json"):
                dest = src.with_name(src.name.replace('.example.json', '.json'))
                if dest.exists():
                    print(f"Skipping (exists): {dest}")
                    continue
                try:
                    with open(src, 'rb') as sf, open(dest, 'wb') as df:
                        df.write(sf.read())
                    print(f"Imported: {dest}")
                    imported = True
                except Exception:
                    pass
        if not imported:
            print("No example files found to import.")

    save_settings(cfg)
    print(f"\nSettings saved to {SETTINGS_FILE}")


if __name__ == "__main__":
    run()
