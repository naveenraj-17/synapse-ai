import json
import os

from core.config import DATA_DIR

PERSONAL_DETAILS_FILE = os.path.join(DATA_DIR, "personal_details.json")


def default_personal_details() -> dict:
    return {
        "first_name": "",
        "last_name": "",
        "email": "",
        "phone_number": "",
        "address": {
            "address1": "",
            "address2": "",
            "city": "",
            "state": "",
            "zipcode": "",
        },
    }


def load_personal_details() -> dict:
    defaults = default_personal_details()

    if not os.path.exists(PERSONAL_DETAILS_FILE):
        return defaults

    try:
        with open(PERSONAL_DETAILS_FILE, "r") as f:
            data = json.load(f)

        # Merge root
        merged = {**defaults, **(data if isinstance(data, dict) else {})}

        # Merge address
        addr = merged.get("address") if isinstance(merged.get("address"), dict) else {}
        merged["address"] = {**defaults["address"], **addr}

        return merged
    except Exception as e:
        print(f"DEBUG: Error loading personal_details: {e}")
        return defaults


def save_personal_details(details: dict) -> dict:
    # Normalize to our schema with defaults
    defaults = default_personal_details()
    d = details if isinstance(details, dict) else {}

    normalized = {**defaults, **d}
    addr = d.get("address") if isinstance(d.get("address"), dict) else {}
    normalized["address"] = {**defaults["address"], **addr}

    with open(PERSONAL_DETAILS_FILE, "w") as f:
        json.dump(normalized, f, indent=4)

    return normalized
