"""
api/telemetry.py — Weather & 6-Sensor Hardware Telemetry Ingestion Router
=========================================================================

Single-purpose entry point for downstream edge hardware drivers (Raspberry Pi
weather station, Beckhoff EtherCAT / RevPi DAQ, or MQTT/HTTP bridges) pushing
live observations into `DigitalShadow` and `world/sensor_sources.py`.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api.runtime import get_shadow
from world.helpers import get_abbreviated_cardinal_8pt, get_weather_assumption
from world.sensor_sources import SENSOR_MODELS, SensorFrame, get_sensor_stream
import world.weather_sources as ws_data

router = APIRouter(tags=["Telemetry"])


class SensorTelemetryRequest(BaseModel):
    """Windowed telemetry payload for the 6-sensor embedded pavement DAQ stack."""

    timestamp: Optional[str] = None
    strain_ue: Optional[float] = None
    pressure_kpa: Optional[float] = None
    temperature_c: Optional[float] = None
    depth_temperatures_c: Optional[List[float]] = None
    moisture_pct: Optional[float] = None
    geophone_ppv_mms: Optional[float] = None
    accel_rms_g: Optional[float] = None
    accel_peak_g: Optional[float] = None
    source: str = "ingested"


@router.post("/dashboard/weather_data")
async def receive_weather_data_from_pi(request: Request) -> Dict[str, str]:
    """Ingests live meteorological telemetry pushed from a Raspberry Pi weather station."""
    try:
        data = await request.json()
        now = datetime.datetime.now()

        ws_data.pi_timestamps.append(now)
        ws_data.pi_temperatures.append(data.get("temperature"))
        ws_data.pi_humidities.append(data.get("humidity"))
        ws_data.pi_pressures.append(data.get("pressure"))
        ws_data.pi_dewpoints.append(data.get("dewpoint"))
        ws_data.pi_lux_values.append(data.get("lux"))
        ws_data.pi_wind_speeds.append(data.get("wind_speed"))
        ws_data.pi_rain_values.append(data.get("rain"))
        ws_data.pi_wind_directions_deg.append(data.get("wind_direction_degrees"))

        ws_data.pi_last_wind_cardinal_str = get_abbreviated_cardinal_8pt(data.get("wind_direction_degrees"))
        ws_data.pi_weather_assumption_str = get_weather_assumption(
            lux=data.get("lux"),
            rain_rate=data.get("rain"),
            temperature=data.get("temperature"),
            humidity=data.get("humidity"),
            pressure=data.get("pressure"),
            current_dt_object=now,
            dewpoint_val=data.get("dewpoint"),
        )
        return {"status": "success"}
    except Exception as e:
        logging.error(f"Error processing Pi data: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/telemetry/sensors/{station_id}")
def ingest_sensor_telemetry(station_id: str, req: SensorTelemetryRequest) -> Dict[str, Any]:
    """Ingests windowed hardware telemetry (KM-100HAS, KDG-500KPA, PT1000, SMT100, HG-5VHS, 2210-002)."""
    ts = req.timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat()
    frame = SensorFrame(
        station_id=station_id,
        timestamp=ts,
        strain_ue=req.strain_ue,
        pressure_kpa=req.pressure_kpa,
        temperature_c=req.temperature_c,
        depth_temperatures_c=req.depth_temperatures_c,
        moisture_pct=req.moisture_pct,
        geophone_ppv_mms=req.geophone_ppv_mms,
        accel_rms_g=req.accel_rms_g,
        accel_peak_g=req.accel_peak_g,
        source=req.source,
    )
    stored = get_sensor_stream().ingest(frame)

    shadow = get_shadow()
    if shadow is not None and hasattr(shadow, "world"):
        with shadow._lock:
            for rf in shadow.world.roadside_units.get("features", []):
                rprops = rf.get("properties", {})
                if str(rprops.get("id")) == str(station_id):
                    rprops["EmbeddedSensors"] = stored.to_dict()
                    if req.temperature_c is not None:
                        rprops["RoadSurfaceTemperature"] = round(float(req.temperature_c), 2)
                        w_key = rf.get("Weather")
                        w_obj = shadow.world.weather_objects.get(w_key)
                        if w_obj and hasattr(w_obj, "road_temp"):
                            w_obj.road_temp = float(req.temperature_c)
                    break

    return {"status": "success", "station_id": station_id, "frame": stored.to_dict()}


@router.get("/api/telemetry/sensors/{station_id}")
def get_sensor_telemetry(station_id: str, limit: int = 50) -> Dict[str, Any]:
    """Returns the latest frame, bounded history, and hardware metadata for `station_id`."""
    stream = get_sensor_stream()
    latest = stream.get_latest(station_id)
    return {
        "status": "ok",
        "station_id": station_id,
        "latest": latest.to_dict() if latest else None,
        "history": stream.get_history(station_id, limit=limit),
        "hardware_catalog": SENSOR_MODELS,
    }
