from __future__ import annotations

import asyncio
import json
import math
from typing import Any, Optional, Tuple
import os
from urllib.parse import quote
import sys

import httpx
import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import BaseModel

from core.config import load_settings


app = Server("maps-mcp-server")


class MapDetailsArgs(BaseModel):
    origin_address: Optional[str] = None
    origin_lat: Optional[float] = None
    origin_lng: Optional[float] = None

    destination_address: Optional[str] = None
    destination_lat: Optional[float] = None
    destination_lng: Optional[float] = None

    travel_mode: str = "driving"  # driving|walking|bicycling|transit
    units: str = "metric"  # metric|imperial


def _normalize_point(address: Optional[str], lat: Optional[float], lng: Optional[float]) -> Tuple[str, dict[str, Any]]:
    addr = (address or "").strip()
    has_coords = lat is not None and lng is not None

    if has_coords:
        meta: dict[str, Any] = {"type": "latlng", "location": {"lat": lat, "lng": lng}}
        if addr:
            meta["address"] = addr
        return f"{lat},{lng}", meta

    if addr:
        return addr, {"type": "address", "address": addr}

    raise ValueError("Both origin and destination must be provided as an address or as lat/lng.")


def _build_directions_url(origin: str, destination: str, travel_mode: str) -> str:
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote(origin)}"
        f"&destination={quote(destination)}"
        f"&travelmode={quote(travel_mode)}"
    )

async def _geocode_address(api_key: str, address: str) -> Tuple[float, float, str]:
    """Geocode an address to lat/lng using Google Maps Geocoding API."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": api_key}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Debug Log for User Verification
        masked_key = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
        sys.stderr.write(f"DEBUG: Geocoding via GET {url} | Address: '{address}' | Key: {masked_key}\n")
        
        resp = await client.get(url, params=params)
        
    data = resp.json()
    if data.get("status") != "OK":
        error_msg = data.get("error_message") or data.get("status")
        raise RuntimeError(f"Geocoding failed for '{address}': {error_msg}")

    result = data["results"][0]
    loc = result["geometry"]["location"]
    formatted_address = result.get("formatted_address", address)
    return loc["lat"], loc["lng"], formatted_address


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float, units: str = "metric") -> Tuple[float, str]:
    """Calculate the great circle distance between two points on the earth."""
    R = 6371000  # Radius of Earth in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    distance_meters = R * c

    if units == "imperial":
        # meters to miles
        distance_display = distance_meters * 0.000621371
        unit_label = "mi"
    else:
        # meters to km
        distance_display = distance_meters / 1000.0
        unit_label = "km"
        
    return distance_meters, f"{distance_display:.1f} {unit_label}"


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_map_details",
            description=(
                "Compute approximate straight-line distance between two points (addresses and/or lat/lng) and return a Google Maps directions URL. "
                "Uses Google Geocoding API + Haversine formula."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "origin_address": {"type": "string", "description": "Origin address"},
                    "origin_lat": {"type": "number", "description": "Origin latitude"},
                    "origin_lng": {"type": "number", "description": "Origin longitude"},
                    "destination_address": {"type": "string", "description": "Destination address"},
                    "destination_lat": {"type": "number", "description": "Destination latitude"},
                    "destination_lng": {"type": "number", "description": "Destination longitude"},
                    "travel_mode": {
                        "type": "string",
                        "description": "Travel mode (for directions URL only)",
                        "enum": ["driving", "walking", "bicycling", "transit"],
                    },
                    "units": {
                        "type": "string",
                        "description": "Unit system",
                        "enum": ["metric", "imperial"],
                    },
                },
            },
        )
    ]


@app.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    try:
        sys.stderr.write(f"DEBUG: map_tool called with {arguments}\n")
        if name != "get_map_details":
            raise ValueError(f"Unknown tool: {name}")

        args = MapDetailsArgs(**(arguments or {}))

        settings = load_settings()
        api_key = (settings.get("google_maps_api_key") or os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
        if not api_key:
            raise ValueError("google_maps_api_key is not configured in Settings -> Integrations or environment variables")

        travel_mode = (args.travel_mode or "driving").strip().lower()
        units = (args.units or "metric").strip().lower()

        # 1. Resolve Origin Coordinates
        if args.origin_lat is not None and args.origin_lng is not None:
            origin_lat, origin_lng = args.origin_lat, args.origin_lng
            origin_addr = args.origin_address or f"{origin_lat},{origin_lng}"
        elif args.origin_address:
            origin_lat, origin_lng, origin_addr = await _geocode_address(api_key, args.origin_address)
        else:
             raise ValueError("Origin must be provided (address or lat/lng)")

        # 2. Resolve Destination Coordinates
        if args.destination_lat is not None and args.destination_lng is not None:
            dest_lat, dest_lng = args.destination_lat, args.destination_lng
            dest_addr = args.destination_address or f"{dest_lat},{dest_lng}"
        elif args.destination_address:
            dest_lat, dest_lng, dest_addr = await _geocode_address(api_key, args.destination_address)
        else:
             raise ValueError("Destination must be provided (address or lat/lng)")

        # 3. Calculate Haversine Distance
        dist_meters, dist_text = _haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng, units)

        # 4. Build Response
        # Note: We don't have duration with simple Haversine, so we omit or estimate it? 
        # For now, just omit duration or say "unknown".
        base = {
            "provider": "google_geocoding_haversine",
            "travel_mode": travel_mode,
            "units": units,
            "distance": {
                "meters": dist_meters,
                "text": dist_text + " (linear approximation)",
            },
            "duration": {
               "text": "Check URL for traffic time"
            },
            "origin": {
                "address": origin_addr,
                "location": {"lat": origin_lat, "lng": origin_lng}
            },
            "destination": {
                "address": dest_addr,
                "location": {"lat": dest_lat, "lng": dest_lng}
            },
            "directions_url": _build_directions_url(origin_addr, dest_addr, travel_mode)
        }

        sys.stderr.write(f"DEBUG: base map response: {base}\n")
        
        return [
            types.TextContent(
                type="text",
                text=json.dumps(base, ensure_ascii=False),
            )
        ]
    except Exception as e:
        sys.stderr.write(f"ERROR: map_tool error: {e}\n")
        return [types.TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
