#!/usr/bin/env python3
"""
scripts/benchmark_fleet.py — Multi-Vehicle Co-Simulation Scalability Benchmark
==============================================================================

Project: Digital Twin Road Demonstrator (MIT License)

Measures cold startup latency, per-step co-simulation execution time (Heraklit HPN
algebra + FODA dynamic class synthesis + HLA/FOM federation contracts + 1D FEM
thermal conduction + binary-searched road segment wear), SSE delta payload size,
single-core CPU utilization, and resident memory footprint across fleet sizes from
N = 10 to N = 2,000 simultaneous Heavy Goods Vehicles.

Usage:
    python3 scripts/benchmark_fleet.py
    # or via CLI:
    ./manage.sh benchmark
"""

from __future__ import annotations

import copy
import json
import platform
import resource
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import dashboard_backend as db  # noqa: E402
from api.runtime import set_shadow  # noqa: E402
from digital_shadow import DigitalShadow  # noqa: E402


def get_rss_mb() -> float:
    """Returns peak resident set size (RSS) in MiB."""
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if platform.system() == "Darwin":
        return ru / (1024.0 * 1024.0)
    return ru / 1024.0


def run_benchmark() -> None:
    """Execute the multi-vehicle co-simulation scalability and memory benchmark."""
    print("=" * 104)
    print(" Digital Twin Road — Co-Simulation Fleet Scalability & Footprint Benchmark")
    print("=" * 104)

    t0 = time.perf_counter()
    ds = DigitalShadow(fiware_flag=False)
    db.shadow_instance = ds
    set_shadow(ds)
    init_ms = (time.perf_counter() - t0) * 1000.0
    base_rss = get_rss_mb()

    seg_count = len((getattr(ds.world.road, "road_segments", None) or {}).get("features", []))
    rsu_count = len(ds.world.roadside_units.get("features", []))
    print(f"• Cold Startup ({seg_count:,} road segments + {rsu_count} RSUs + 3 warmup vehicles): {init_ms:.1f} ms")
    print(f"• Baseline Process RSS Memory: {base_rss:.1f} MB\n")

    header = (
        f"{'Fleet (N)':>9} | {'5s Tick (ms)':>12} | {'ms / Vehicle':>12} | "
        f"{'HPN+FODA+HLA':>12} | {'1D FEM+Wear':>11} | {'SSE Payload':>11} | "
        f"{'1-Core CPU':>10} | {'RSS Memory':>10}"
    )
    print(header)
    print("-" * len(header))

    fleet_sizes = [10, 50, 100, 250, 500, 1000, 2000]

    for target_n in fleet_sizes:
        ds.traffic_management.parameters["VehicleLimit"] = target_n + 20
        while len(ds.traffic_management.active_vehicles) < target_n:
            v = ds.traffic_management.force_spawn_vehicle()
            if v is None:
                break
            v.position = 50.0
            v.params["StartRoute"] = 0.0
            v.params["EndRoute"] = 100.0
            v.direction = 1
            v.params["Active"] = True

        # Execute 1 full 5.0-second co-simulation step
        t_step0 = time.perf_counter()
        with ds._lock:
            ds.world.update_weather_state("2026-11-02 18:00:00")

            t_u0 = time.perf_counter()
            ds.traffic_management.update_vehicles_state()
            t_upd = (time.perf_counter() - t_u0) * 1000.0

            t_s0 = time.perf_counter()
            for vehicle_id, vehicle_obj in list(ds.traffic_management.active_vehicles.items()):
                ds.simpl.simulation_pipeline(vehicle_id, vehicle_obj)
                ds.world.update_road_state(vehicle_id, vehicle_obj)
                stat_row = {
                    k: copy.deepcopy(val)
                    for k, val in vehicle_obj.params.items()
                    if k not in ("Trajectory", "FederationContract", "HPN", "State")
                }
                vehicle_obj.statistic.append(stat_row)
                if len(vehicle_obj.statistic) > 80:
                    vehicle_obj.statistic = vehicle_obj.statistic[-80:]
            t_fem = (time.perf_counter() - t_s0) * 1000.0

            ds.world.warning_handling()
            ds.world.prepare_geojson()
            ds.update_geojson_snapshots()

        t_total = (time.perf_counter() - t_step0) * 1000.0

        delta_payload, _ = db.get_dynamic_delta_state(0)
        t_j0 = time.perf_counter()
        sse_kb = len(json.dumps(delta_payload).encode("utf-8")) / 1024.0
        t_json = (time.perf_counter() - t_j0) * 1000.0

        # Effective 1-core CPU utilization over a 5.0s simulation tick + 2.0s SSE stream cadence
        cpu_pct = ((t_total + t_json * 2.5) / 5000.0) * 100.0
        cur_rss = get_rss_mb()

        print(
            f"{target_n:9d} | {t_total:10.1f} ms | {t_total / target_n:9.3f} ms | "
            f"{t_upd:9.1f} ms | {t_fem:8.1f} ms | {sse_kb:8.1f} KB | "
            f"{cpu_pct:8.1f} % | {cur_rss:7.1f} MB"
        )

    per_veh_kb = ((get_rss_mb() - base_rss) * 1024.0) / max(1, fleet_sizes[-1])
    print("-" * len(header))
    print(f"• Incremental Resident Memory Footprint per Active Vehicle: ~{per_veh_kb:.1f} KB / vehicle")
    print("=" * 104)


if __name__ == "__main__":
    run_benchmark()
