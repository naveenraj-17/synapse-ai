"""
DB configuration management endpoints (CRUD + schema refresh).
"""
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from core.models import DBConfig
from core.config import DATA_DIR
from core.json_store import JsonStore

router = APIRouter()

_db_configs_store = JsonStore(os.path.join(DATA_DIR, "db_configs.json"))


def load_db_configs() -> list[dict]:
    return _db_configs_store.load()


def save_db_configs(configs: list[dict]):
    _db_configs_store.save(configs)


@router.get("/api/db-configs")
async def get_db_configs():
    return load_db_configs()


@router.post("/api/db-configs")
async def create_db_config(config: DBConfig):
    configs = load_db_configs()
    for i, c in enumerate(configs):
        if c["id"] == config.id:
            configs[i] = config.dict()
            save_db_configs(configs)
            return config
    configs.append(config.dict())
    save_db_configs(configs)
    return config


@router.delete("/api/db-configs/{config_id}")
async def delete_db_config(config_id: str):
    configs = load_db_configs()
    configs = [c for c in configs if c["id"] != config_id]
    save_db_configs(configs)
    return {"status": "success"}


@router.post("/api/db-configs/{config_id}/refresh-schema")
async def refresh_db_schema(config_id: str):
    configs = load_db_configs()
    config = next((c for c in configs if c["id"] == config_id), None)
    if not config:
        raise HTTPException(status_code=404, detail="DB config not found")

    connection_string = config.get("connection_string", "")
    if not connection_string:
        raise HTTPException(status_code=400, detail="No connection string configured")

    try:
        from sqlalchemy import create_engine, inspect, text

        engine = create_engine(connection_string, connect_args={"connect_timeout": 10})
        inspector = inspect(engine)

        schema_lines = []
        table_names = inspector.get_table_names()

        for table_name in table_names:
            columns = inspector.get_columns(table_name)
            col_defs = ", ".join(
                f"{col['name']} ({str(col['type'])})" for col in columns
            )
            schema_lines.append(f"  {table_name}({col_defs})")

        schema_info = "Tables:\n" + "\n".join(schema_lines) if schema_lines else "No tables found."

        engine.dispose()

        config["schema_info"] = schema_info
        config["status"] = "connected"
        config["error_message"] = None
        config["last_tested"] = datetime.utcnow().isoformat()

        for i, c in enumerate(configs):
            if c["id"] == config_id:
                configs[i] = config
                break
        save_db_configs(configs)

        return {"status": "connected", "schema_info": schema_info}

    except Exception as e:
        config["status"] = "error"
        config["error_message"] = str(e)
        config["last_tested"] = datetime.utcnow().isoformat()

        for i, c in enumerate(configs):
            if c["id"] == config_id:
                configs[i] = config
                break
        save_db_configs(configs)

        raise HTTPException(status_code=400, detail=str(e))
