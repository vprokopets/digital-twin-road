# Data Curation & Context Brokering Subsystem

This package provides a **pluggable context brokering and data curation architecture** for the Road Digital Twin platform via `BaseDataBroker`.

## Architecture Overview

```
                               ┌────────────────────────────────┐
                               │   BaseDataBroker (base.py)     │
                               │  • register_device()           │
                               │  • send_telemetry()            │
                               │  • get_entity() / history()    │
                               └───────────────┬────────────────┘
                                               │
                       ┌───────────────────────┴───────────────────────┐
                       ▼                                               ▼
             ┌───────────────────┐                           ┌───────────────────┐
             │      Native       │                           │      FIWARE       │
             │    (In-Memory)    │                           │  (Open Standards) │
             ├───────────────────┤                           ├───────────────────┤
             │ • 0 Dependencies  │                           │ • Orion (NGSIv2)  │
             │ • In-Memory RLock │                           │ • UltraLight 2.0  │
             │ • Sub-microsecond │                           │ • Cygnus/Postgres │
             │ • Standalone / Dev│                           │ • Service Groups  │
             └───────────────────┘                           └───────────────────┘
```

## Backend Comparison Matrix

| Metric / Dimension | Native (`native/`) | FIWARE (`fiware/`) |
| :--- | :--- | :--- |
| **Primary Use Case** | Local simulation, test execution, standalone RSUs | EU standards compliance, IoT Agent device ingestion |
| **Footprint** | 0 MB (In-process Python) | Orion + IoT Agent UltraLight + MongoDB containers |
| **Latency** | < 0.01 ms | 25 – 100 ms |
| **Active State** | Thread-safe dictionary | Orion Context Broker (MongoDB) |
| **Time-Series Log**| Memory ring buffer | Cygnus / PostgreSQL time-series |
| **Persistence** | None (Transient) | Relational SQL / MongoDB storage |
| **Protocol** | Python API / Direct call | UltraLight 2.0 (HTTP) $\rightarrow$ NGSIv2 |

## Configuration

Select the active backend in `configs/global_config.json`:
```json
{
  "DataBroker": {
    "backend": "native"   // Options: "native" | "fiware"
  }
}
```
Or override dynamically via environment variable:
```bash
export DATA_BROKER_BACKEND="fiware"   # or "native"
```
