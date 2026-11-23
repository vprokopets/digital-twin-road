"""
world/sensor_sources.py — Embedded Pavement Hardware Sensor Ingestion Contract
==============================================================================

Defines the abstract `BaseSensorStream` interface and thread-safe in-memory
`IngestedSensorStream` buffer for windowed telemetry from the 6-sensor embedded
pavement DAQ stack:
  - Strain: TML KM-100HAS (`strain_ue`, um/m)
  - Pressure: TML KDG-500KPA (`pressure_kpa`, kPa)
  - Temperature: PT1000 (`temperature_c` / `depth_temperatures_c`, degC)
  - Moisture / Humidity: Truebner SMT100 (`moisture_pct`, %)
  - Geophone: HGS HG-5VHS (`geophone_ppv_mms`, mm/s)
  - Accelerometer: Silicon Designs 2210-002 (`accel_rms_g`, `accel_peak_g`, g)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass
import logging
import threading
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger("sensor_sources")

SENSOR_MODELS: Dict[str, Dict[str, str]] = {
    "strain_ue": {"sensor_type": "Strain", "model": "TML KM-100HAS", "unit": "um/m"},
    "pressure_kpa": {"sensor_type": "Pressure", "model": "TML KDG-500KPA", "unit": "kPa"},
    "temperature_c": {"sensor_type": "Temperature", "model": "PT1000", "unit": "degC"},
    "moisture_pct": {"sensor_type": "Humidity", "model": "Truebner SMT100", "unit": "%"},
    "geophone_ppv_mms": {"sensor_type": "Geophone", "model": "HGS HG-5VHS", "unit": "mm/s"},
    "accel_rms_g": {"sensor_type": "Accelerometer", "model": "Silicon Designs 2210-002", "unit": "g"},
    "accel_peak_g": {"sensor_type": "Accelerometer", "model": "Silicon Designs 2210-002", "unit": "g"},
}


@dataclass
class SensorFrame:
    """Windowed telemetry snapshot for a multi-channel pavement sensor station."""

    station_id: str
    timestamp: str
    strain_ue: Optional[float] = None
    pressure_kpa: Optional[float] = None
    temperature_c: Optional[float] = None
    depth_temperatures_c: Optional[List[float]] = None
    moisture_pct: Optional[float] = None
    geophone_ppv_mms: Optional[float] = None
    accel_rms_g: Optional[float] = None
    accel_peak_g: Optional[float] = None
    source: str = "ingested"

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the frame to a JSON-ready dictionary."""
        return asdict(self)


class BaseSensorStream(ABC):
    """Abstract Strategy interface for hardware or replay sensor ingestion backends."""

    @abstractmethod
    def ingest(self, frame: SensorFrame) -> SensorFrame:
        """Persists a new windowed `SensorFrame` and returns the normalized frame."""

    @abstractmethod
    def get_latest(self, station_id: str) -> Optional[SensorFrame]:
        """Returns the most recent `SensorFrame` for `station_id`, or `None`."""

    @abstractmethod
    def get_history(self, station_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns up to `limit` chronological telemetry frames for `station_id`."""

    @abstractmethod
    def list_stations(self) -> List[str]:
        """Returns all station IDs that have recorded telemetry frames."""


class IngestedSensorStream(BaseSensorStream):
    """Thread-safe bounded ring-buffer implementation of `BaseSensorStream`."""

    def __init__(self, maxlen: int = 200, forward_to_broker: bool = True) -> None:
        self._maxlen = maxlen
        self._forward_to_broker = forward_to_broker
        self._lock = threading.RLock()
        self._buffers: Dict[str, Deque[SensorFrame]] = {}

    def ingest(self, frame: SensorFrame) -> SensorFrame:
        """Stores `frame` in the station's bounded ring buffer and forwards to `data_curation`."""
        with self._lock:
            buf = self._buffers.get(frame.station_id)
            if buf is None:
                buf = deque(maxlen=self._maxlen)
                self._buffers[frame.station_id] = buf
            buf.append(frame)

        if self._forward_to_broker:
            self._publish_to_broker(frame)
        return frame

    def _publish_to_broker(self, frame: SensorFrame) -> None:
        """Maps non-null `SensorFrame` channels to FIWARE/data_curation attributes."""
        mapping = {
            "Microstrain": frame.strain_ue,
            "ContactPressure": frame.pressure_kpa,
            "LayerTemperature": frame.temperature_c,
            "Moisture": frame.moisture_pct,
            "PeakParticleVelocity": frame.geophone_ppv_mms,
            "AccelerationRMS": frame.accel_rms_g,
            "AccelerationPeakG": frame.accel_peak_g,
        }
        payload = {k: v for k, v in mapping.items() if v is not None}
        if not payload:
            return
        try:
            from data_curation import send_telemetry

            send_telemetry(frame.station_id, "Embedded_sensor", payload)
        except Exception as exc:
            logger.debug("Broker publish skipped for sensor station %s: %s", frame.station_id, exc)

    def get_latest(self, station_id: str) -> Optional[SensorFrame]:
        """Returns the most recent frame for `station_id` if present."""
        with self._lock:
            buf = self._buffers.get(station_id)
            return buf[-1] if buf else None

    def get_history(self, station_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns the newest `limit` serialized frames for `station_id`."""
        with self._lock:
            buf = self._buffers.get(station_id)
            if not buf:
                return []
            items = list(buf)[-max(1, limit):]
            return [item.to_dict() for item in items]

    def list_stations(self) -> List[str]:
        """Returns sorted IDs of all stations with buffered telemetry."""
        with self._lock:
            return sorted(self._buffers.keys())


_default_sensor_stream: Optional[BaseSensorStream] = None


def get_sensor_stream() -> BaseSensorStream:
    """Returns the active singleton `BaseSensorStream` instance."""
    global _default_sensor_stream
    if _default_sensor_stream is None:
        _default_sensor_stream = IngestedSensorStream()
    return _default_sensor_stream


def set_sensor_stream(stream: BaseSensorStream) -> None:
    """Replaces the active `BaseSensorStream` (for custom DAQ or replay drivers)."""
    global _default_sensor_stream
    _default_sensor_stream = stream
