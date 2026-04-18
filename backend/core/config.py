import os
import json
from pathlib import Path
from urllib.parse import urlparse, urlunparse

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_data_dir_env = os.getenv("SYNAPSE_DATA_DIR", "")
if _data_dir_env:
    _p = Path(_data_dir_env)
    DATA_DIR = str(_p if _p.is_absolute() else _PROJECT_ROOT / _p)
else:
    DATA_DIR = str(Path(__file__).resolve().parent.parent / "data")
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
CREDENTIALS_FILE = os.path.join(DATA_DIR, "credentials.json")
TOKEN_FILE = os.path.join(DATA_DIR, "token.json")

def load_settings():
    default_settings = {
        "agent_name": "System Agent", 
        "model": "mistral",
        "mode": "local",
        "openai_key": "",
        "anthropic_key": "",
        "gemini_key": "",
        "grok_key": "",
        "deepseek_key": "",
        "bedrock_api_key": "",
        "bedrock_inference_profile": "",
        "embedding_model": "",
        "aws_access_key_id": "",
        "aws_secret_access_key": "",
        "aws_session_token": "",
        "aws_region": "us-east-1",
        "sql_connection_string": "",
        "n8n_url": "http://localhost:5678",
        "n8n_api_key": "",
        "n8n_table_id": "",
        "global_config": {},
        "vault_enabled": True,
        "vault_threshold": 100000,
        "allow_db_write": False,
        "coding_agent_enabled": False,
        "report_agent_enabled": True,
        "messaging_enabled": True,
        "embed_code": False,
        "bash_allowed_dirs": [],
    }
    
    if not os.path.exists(SETTINGS_FILE):
        return default_settings
    
    try:
        with open(SETTINGS_FILE, 'r') as f:
            data = json.load(f)
            # Merge defaults
            return {**default_settings, **data}
    except Exception as e:
        print(f"DEBUG: Error loading settings: {e}")
        return default_settings


def sanitize_db_url(raw: str) -> str:
    """Normalize a PostgreSQL URL for use with psycopg (not SQLAlchemy).

    Fixes:
    1. Strips SQLAlchemy dialect suffix (e.g. postgresql+psycopg → postgresql)
    2. Rewrites empty password (user:@host → user@host) which psycopg/libpq cannot parse.
    """
    if not raw:
        return ""
    p = urlparse(raw)
    netloc = p.netloc
    if netloc:
        netloc = netloc.replace(":@", "@")
    scheme = p.scheme.split("+")[0]
    return urlunparse(p._replace(scheme=scheme, netloc=netloc))
