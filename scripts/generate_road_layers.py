#!/usr/bin/env python3
"""
scripts/generate_road_layers.py — Corridor OSM GeoJSON Layer Generator
======================================================================

Generates high-resolution GeoJSON layers for the Dresden-Leipzig highway corridor
(A4/A14/A38) from OpenStreetMap centerline geometry with dual carriageways and ramps.

Both Direction 1 (Dresden -> Leipzig) and Direction 2 (Leipzig -> Dresden) follow real
motorway carriageways and directional interchange ramps (Dreieck Nossen, Dreieck
Parthenaue, AS Leipzig-Süd, etc.) so vehicles respect one-way rules and ramp layouts.

Outputs:
1. configs/road_curves.geojson:
   Continuous OSM highway polylines and macro sections with road metadata.
2. configs/road_segments.geojson:
   Discrete ~150-250 m directional highway sections (FGSV / BASt Homogenitätsabschnitte).
3. configs/road_geometry.json:
   Updated high-resolution centerline coordinate polyline for vehicle kinematics.
"""

import json
import math
import random
import urllib.request
from pathlib import Path
import geopy.distance as gp

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"

def fetch_osm_route(waypoints, name, cache_filename, force_refresh=False):
    """Fetch a driving route from OSRM or load its cached coordinate polyline."""
    cache_path = CONFIGS_DIR / cache_filename
    if cache_path.exists() and not force_refresh:
        try:
            with open(cache_path) as f:
                d = json.load(f)
            coords = d.get('coords', [])
            total_km = d.get('km', 0.0)
            if len(coords) > 1000:
                print(f"Loaded {len(coords)} vertices for {name} from cache ({cache_filename}) [{total_km:.2f} km].")
                return coords, total_km
        except Exception as e:
            print(f"Could not load cache {cache_filename}: {e}, fetching fresh from OSRM...")

    coord_str = ';'.join(f'{p[0]:.6f},{p[1]:.6f}' for p in waypoints)
    url = f'https://router.project-osrm.org/route/v1/driving/{coord_str}?overview=full&geometries=geojson&steps=true'
    print(f"Querying OSRM for {name} ({len(waypoints)} waypoints)...")
    req = urllib.request.Request(url, headers={'User-Agent': 'DigitalTwinRoad-Demonstrator-RoadGeometry/2.0'})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())

    if data.get('code') != 'Ok' or not data.get('routes'):
        raise RuntimeError(f"OSRM routing failed for {name}: {data}")

    route = data['routes'][0]
    raw_coords = route['geometry']['coordinates']
    total_km = route['distance'] / 1000.0
    print(f"Fetched {len(raw_coords)} high-resolution OSM vertices for {name} ({total_km:.2f} km).")

    try:
        with open(cache_path, 'w') as f:
            json.dump({'coords': raw_coords, 'km': total_km}, f)
    except Exception as e:
        print(f"Warning: could not save cache {cache_filename}: {e}")

    return raw_coords, total_km

def interpolate_pt(p1, p2, fraction):
    """Linear interpolation between two [lon, lat] coordinates."""
    return [
        p1[0] + (p2[0] - p1[0]) * fraction,
        p1[1] + (p2[1] - p1[1]) * fraction
    ]

def compute_arc_lengths(coords):
    """Computes cumulative arc distance in km along the polyline."""
    cum_dists = [0.0]
    total = 0.0
    for i in range(1, len(coords)):
        p_prev = (coords[i-1][1], coords[i-1][0])
        p_curr = (coords[i][1], coords[i][0])
        d = gp.distance(p_prev, p_curr).kilometers
        total += d
        cum_dists.append(total)
    return cum_dists, total

def get_point_at_distance(coords, cum_dists, target_dist):
    """Returns the interpolated [lon, lat] coordinate at a given distance (km)."""
    if target_dist <= 0:
        return coords[0]
    if target_dist >= cum_dists[-1]:
        return coords[-1]

    for i in range(1, len(cum_dists)):
        if cum_dists[i] >= target_dist:
            d_span = cum_dists[i] - cum_dists[i-1]
            if d_span < 1e-9:
                return coords[i]
            frac = (target_dist - cum_dists[i-1]) / d_span
            return interpolate_pt(coords[i-1], coords[i], frac)
    return coords[-1]

def get_subline(coords, cum_dists, start_d, end_d):
    """Extracts all polyline vertices between start_d and end_d, including interpolated endpoints."""
    pt_start = get_point_at_distance(coords, cum_dists, start_d)
    pt_end = get_point_at_distance(coords, cum_dists, end_d)

    sub_coords = [pt_start]
    for i in range(len(coords)):
        if start_d < cum_dists[i] < end_d:
            sub_coords.append(coords[i])
    sub_coords.append(pt_end)
    return sub_coords

def determine_road_structure(dist_km, structure_splits):
    """Maps cumulative distance in km to road structure ID and metadata."""
    for split_km, struct_id, name, lanes, is_highway in structure_splits:
        if dist_km <= split_km:
            return struct_id, name, lanes, is_highway
    last = structure_splits[-1]
    return last[1], last[2], last[3], last[4]

def main():
    """Build and write directional corridor GeoJSON and centerline geometry files."""
    print("=== GENERATING DUAL CARRIAGEWAY ROAD LAYERS WITH REAL INTERCHANGE GEOMETRY ===")

    # 1. High-resolution directional waypoints
    # Direction 1: Dresden-Neustadt -> Leipziger Str -> Lommatzscher Str -> AS Dresden-Neustadt on-ramp (A4) -> A4 westbound -> Dreieck Nossen flyover (A14) -> A14 westbound -> Dreieck Parthenaue trumpet loop (A38) -> A38 westbound -> Kreuz Leipzig-Süd direct connector flyover (red arrow) -> B2 Wundtstraße -> Leipzig Center (Goerdelerring)
    wps_dir1 = [
        (13.736757, 51.063404),
        (13.454568, 51.060718),
        (12.54022, 51.29967),
        (12.387442, 51.252386),
        (12.370681, 51.343992)
    ]

    # Direction 2: Leipzig Center (Goerdelerring) -> B2 Wundtstraße southbound -> B2/A72 bridge over A38 -> Kreuz Leipzig-Süd southwest cloverleaf loop (black arrow) -> A38 eastbound -> Dreieck Parthenaue direct connector ramp (A14) -> A14 eastbound -> Dreieck Nossen connector loop around drone hub (A4) -> A4 eastbound -> AS Dresden-Neustadt off-ramp / Washingtonstraße -> Lommatzscher Str (straight past Elbepark) -> Leipziger Str -> Dresden-Neustadt Station
    wps_dir2 = [
        (12.370681, 51.343992),
        (12.376294, 51.299216),
        (12.420222, 51.248320),
        (13.3712, 51.0535),
        (13.7000, 51.0822),
        (13.736757, 51.063404)
    ]

    coords_dir1, total_km_dir1 = fetch_osm_route(wps_dir1, "Direction 1 (Dresden -> Leipzig)", "raw_route_dir1.json", force_refresh=True)
    coords_dir2_raw, total_km_dir2 = fetch_osm_route(wps_dir2, "Direction 2 (Leipzig -> Dresden)", "raw_route_dir2.json", force_refresh=True)

    # For consistent stationing (km 0 at Dresden, km 124 at Leipzig), Direction 2 vertices are reversed for distance indexing
    coords_dir2_dresden_to_leipzig = list(reversed(coords_dir2_raw))

    cum_dists_dir1, total_km_dir1 = compute_arc_lengths(coords_dir1)
    cum_dists_dir2, total_km_dir2 = compute_arc_lengths(coords_dir2_dresden_to_leipzig)

    print(f"Direction 1: {total_km_dir1:.3f} km, {len(coords_dir1)} vertices")
    print(f"Direction 2: {total_km_dir2:.3f} km, {len(coords_dir2_dresden_to_leipzig)} vertices")

    with open(CONFIGS_DIR / "road_water_sources.json") as f:
        water_geojson = json.load(f)
    with open(CONFIGS_DIR / "road_roadside_units.json") as f:
        ru_geojson = json.load(f)

    # Highway structure boundaries along corridor:
    # (split_km, struct_id, name, lanes, is_highway)
    structure_splits_dir1 = [
        (4.24, "RoadStructure_0", "DD (Dresden Urban)", 2, False),
        (27.90, "RoadStructure_1", "A4 Motorway", 3, True),
        (97.49, "RoadStructure_2", "A14 Motorway", 3, True),
        (110.08, "RoadStructure_3", "A38 Motorway", 3, True),
        (total_km_dir1 + 1.0, "RoadStructure_4", "L (Leipzig Urban)", 2, False)
    ]

    structure_splits_dir2 = [
        (4.23, "RoadStructure_0", "DD (Dresden Urban)", 2, False),
        (27.60, "RoadStructure_1", "A4 Motorway", 3, True),
        (95.81, "RoadStructure_2", "A14 Motorway", 3, True),
        (108.48, "RoadStructure_3", "A38 Motorway", 3, True),
        (total_km_dir2 + 1.0, "RoadStructure_4", "L (Leipzig Urban)", 2, False)
    ]

    # Compute physical median / corridor centerline
    # Slices sample points along Direction 1 and finds the corresponding median point
    centerline_coords = []
    num_centerline_samples = max(len(coords_dir1), len(coords_dir2_dresden_to_leipzig))
    for i in range(num_centerline_samples):
        frac = i / (num_centerline_samples - 1)
        d1 = frac * total_km_dir1
        d2 = frac * total_km_dir2
        p1 = get_point_at_distance(coords_dir1, cum_dists_dir1, d1)
        p2 = get_point_at_distance(coords_dir2_dresden_to_leipzig, cum_dists_dir2, d2)
        dist_between_m = gp.distance((p1[1], p1[0]), (p2[1], p2[0])).meters
        # If running parallel on motorway, use exact median midpoint; at divergent interchanges, track primary path
        if dist_between_m < 80.0:
            mid = [round((p1[0] + p2[0]) / 2.0, 6), round((p1[1] + p2[1]) / 2.0, 6)]
        else:
            mid = [round(p1[0], 6), round(p1[1], 6)]
        centerline_coords.append(mid)

    # 1. GENERATE configs/road_curves.geojson
    print("\n--- Generating configs/road_curves.geojson ---")
    macro_features = []

    # Corridor Centerline (runs down the central median strip)
    macro_features.append({
        "type": "Feature",
        "properties": {
            "id": "corridor_dresden_leipzig",
            "name": "Dresden - Leipzig Highway Corridor (Centerline / Median)",
            "length_km": round((total_km_dir1 + total_km_dir2) / 2.0, 3),
            "total_vertices": len(centerline_coords),
            "structures": ["DD", "A4", "A14", "A38", "L"],
            "type": "centerline"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": centerline_coords
        }
    })

    # Carriageway 1 (Direction 1: Dresden -> Leipzig)
    macro_features.append({
        "type": "Feature",
        "properties": {
            "id": "carriageway_dir_1",
            "name": "Direction 1: Dresden → Leipzig (Richtungsfahrbahn Ost)",
            "direction": 1,
            "length_km": round(total_km_dir1, 3),
            "type": "carriageway"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords_dir1
        }
    })

    # Carriageway 2 (Direction 2: Leipzig -> Dresden)
    macro_features.append({
        "type": "Feature",
        "properties": {
            "id": "carriageway_dir_2",
            "name": "Direction 2: Leipzig → Dresden (Richtungsfahrbahn West)",
            "direction": -1,
            "length_km": round(total_km_dir2, 3),
            "type": "carriageway"
        },
        "geometry": {
            "type": "LineString",
            "coordinates": coords_dir2_raw
        }
    })

    # Macro highway sections for Direction 1
    prev_split = 0.0
    for split_km, struct_id, name, lanes, _is_hwy in structure_splits_dir1:
        end_split = min(split_km, total_km_dir1)
        sec_dir1 = get_subline(coords_dir1, cum_dists_dir1, prev_split, end_split)
        sec_len = end_split - prev_split

        macro_features.append({
            "type": "Feature",
            "properties": {
                "id": f"curve_{struct_id}_dir1",
                "road": struct_id,
                "name": f"{name} [Dresden → Leipzig]",
                "direction": 1,
                "lanes": lanes,
                "station_start_km": round(prev_split, 3),
                "station_end_km": round(end_split, 3),
                "length_km": round(sec_len, 3)
            },
            "geometry": {
                "type": "LineString",
                "coordinates": sec_dir1
            }
        })
        prev_split = end_split

    # Macro highway sections for Direction 2
    prev_split = 0.0
    for split_km, struct_id, name, lanes, _is_hwy in structure_splits_dir2:
        end_split = min(split_km, total_km_dir2)
        sec_dir2 = get_subline(coords_dir2_dresden_to_leipzig, cum_dists_dir2, prev_split, end_split)
        sec_len = end_split - prev_split

        macro_features.append({
            "type": "Feature",
            "properties": {
                "id": f"curve_{struct_id}_dir2",
                "road": struct_id,
                "name": f"{name} [Leipzig → Dresden]",
                "direction": -1,
                "lanes": lanes,
                "station_start_km": round(prev_split, 3),
                "station_end_km": round(end_split, 3),
                "length_km": round(sec_len, 3)
            },
            "geometry": {
                "type": "LineString",
                "coordinates": sec_dir2
            }
        })
        prev_split = end_split

    curves_geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "description": "High-resolution OpenStreetMap dual carriageway highway curves for Dresden-Leipzig corridor with real directional ramps",
            "source": "OpenStreetMap / OSRM",
            "crs": "EPSG:4326 (WGS84)"
        },
        "features": macro_features
    }

    with open(CONFIGS_DIR / "road_curves.geojson", "w") as f:
        json.dump(curves_geojson, f, indent=2)
    print(f"Saved {CONFIGS_DIR / 'road_curves.geojson'} with {len(macro_features)} curve features.")

    # 2. GENERATE configs/road_segments.geojson FOR BOTH CARRIAGEWAYS (~200m each)
    SEGMENT_STEP_KM = 0.200 # 200 meters nominal length
    num_segments_dir1 = math.ceil(total_km_dir1 / SEGMENT_STEP_KM)
    num_segments_dir2 = math.ceil(total_km_dir2 / SEGMENT_STEP_KM)
    print(f"\n--- Generating configs/road_segments.geojson ({num_segments_dir1} dir1 sections, {num_segments_dir2} dir2 sections) ---")

    segment_features = []

    # Direction 1 segments (Dresden -> Leipzig)
    for k in range(num_segments_dir1):
        s_start = k * SEGMENT_STEP_KM
        s_end = min((k + 1) * SEGMENT_STEP_KM, total_km_dir1)
        s_mid = (s_start + s_end) / 2.0
        seg_len_m = (s_end - s_start) * 1000.0

        sub_coords = get_subline(coords_dir1, cum_dists_dir1, s_start, s_end)
        mid_pt = get_point_at_distance(coords_dir1, cum_dists_dir1, s_mid)
        struct_id, struct_name, lanes, _ = determine_road_structure(s_mid, structure_splits_dir1)

        # Proximity to water sources
        closest_water_km = min(
            gp.distance((mid_pt[1], mid_pt[0]), (w['geometry']['coordinates'][1], w['geometry']['coordinates'][0])).kilometers
            for w in water_geojson['features']
        )
        # Proximity to roadside units
        closest_ru_km = min(
            gp.distance((mid_pt[1], mid_pt[0]), (ru['geometry']['coordinates'][1], ru['geometry']['coordinates'][0])).kilometers
            for ru in ru_geojson['features']
        )

        rng1 = random.Random(1337 + k)
        base_state = 78 + 14 * math.sin(s_mid * 1.8)
        island_effect = 16 * math.sin(s_mid / 1.1)
        noise1 = rng1.uniform(-4, 4)
        health_state_dir1 = int(max(15, min(99, round(base_state + island_effect + noise1))))

        segment_features.append({
            "type": "Feature",
            "properties": {
                "id": f"road_seg_dir1_{k}",
                "point_id": f"road_pt_dir1_{k}",
                "name": f"Section {k} ({s_start:.2f}-{s_end:.2f} km) [Dresden → Leipzig]",
                "direction": 1,
                "carriageway": "Dresden → Leipzig",
                "station_start_km": round(s_start, 3),
                "station_end_km": round(s_end, 3),
                "station_mid_km": round(s_mid, 3),
                "length_m": round(seg_len_m, 1),
                "road": struct_id,
                "road_name": struct_name,
                "lanes": lanes,
                "state": health_state_dir1,
                "ClosestWater": round(closest_water_km, 3),
                "ClosestRU": round(closest_ru_km, 3)
            },
            "geometry": {
                "type": "LineString",
                "coordinates": sub_coords
            }
        })

    # Direction 2 segments (Leipzig -> Dresden)
    # Using real OSM Direction 2 geometry (sampled along coords_dir2_dresden_to_leipzig so coords[0] is towards Dresden and coords[-1] is towards Leipzig)
    for k in range(num_segments_dir2):
        s_start = k * SEGMENT_STEP_KM
        s_end = min((k + 1) * SEGMENT_STEP_KM, total_km_dir2)
        s_mid = (s_start + s_end) / 2.0
        seg_len_m = (s_end - s_start) * 1000.0

        sub_coords = get_subline(coords_dir2_dresden_to_leipzig, cum_dists_dir2, s_start, s_end)
        mid_pt = get_point_at_distance(coords_dir2_dresden_to_leipzig, cum_dists_dir2, s_mid)
        struct_id, struct_name, lanes, _ = determine_road_structure(s_mid, structure_splits_dir2)

        closest_water_km = min(
            gp.distance((mid_pt[1], mid_pt[0]), (w['geometry']['coordinates'][1], w['geometry']['coordinates'][0])).kilometers
            for w in water_geojson['features']
        )
        closest_ru_km = min(
            gp.distance((mid_pt[1], mid_pt[0]), (ru['geometry']['coordinates'][1], ru['geometry']['coordinates'][0])).kilometers
            for ru in ru_geojson['features']
        )

        rng2 = random.Random(9999 + k)
        base_state = 78 + 14 * math.sin(s_mid * 1.8)
        island_effect = 16 * math.sin(s_mid / 1.1)
        noise2 = rng2.uniform(-6, 3)
        health_state_dir2 = int(max(15, min(99, round(base_state + island_effect + noise2))))

        segment_features.append({
            "type": "Feature",
            "properties": {
                "id": f"road_seg_dir2_{k}",
                "point_id": f"road_pt_dir2_{k}",
                "name": f"Section {k} ({s_start:.2f}-{s_end:.2f} km) [Leipzig → Dresden]",
                "direction": -1,
                "carriageway": "Leipzig → Dresden",
                "station_start_km": round(s_start, 3),
                "station_end_km": round(s_end, 3),
                "station_mid_km": round(s_mid, 3),
                "length_m": round(seg_len_m, 1),
                "road": struct_id,
                "road_name": struct_name,
                "lanes": lanes,
                "state": health_state_dir2,
                "ClosestWater": round(closest_water_km, 3),
                "ClosestRU": round(closest_ru_km, 3)
            },
            "geometry": {
                "type": "LineString",
                "coordinates": sub_coords
            }
        })

    segments_geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "description": "Dual carriageway discrete 200m highway sections with real OSM directional interchange ramps for pavement condition assessment and FEM continuum cells",
            "segment_count": len(segment_features),
            "nominal_length_m": SEGMENT_STEP_KM * 1000,
            "corridor_length_km_dir1": round(total_km_dir1, 3),
            "corridor_length_km_dir2": round(total_km_dir2, 3),
            "carriageways": ["Direction 1 (Dresden -> Leipzig)", "Direction 2 (Leipzig -> Dresden)"],
            "standard": "FGSV / BASt PMS Homogenitätsabschnitte"
        },
        "features": segment_features
    }

    with open(CONFIGS_DIR / "road_segments.geojson", "w") as f:
        json.dump(segments_geojson, f, indent=2)
    print(f"Saved {CONFIGS_DIR / 'road_segments.geojson'} with {len(segment_features)} dual-carriageway highway sections.")

    # 3. UPDATE configs/road_geometry.json
    print("\n--- Updating configs/road_geometry.json ---")
    road_geometry = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "name": "Dresden-Leipzig Highway Corridor Centerline",
                    "source": "OpenStreetMap",
                    "points_count": len(centerline_coords),
                    "length_km": round((total_km_dir1 + total_km_dir2) / 2.0, 3)
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": centerline_coords
                }
            }
        ]
    }
    with open(CONFIGS_DIR / "road_geometry.json", "w") as f:
        json.dump(road_geometry, f, indent=2)
    print(f"Saved {CONFIGS_DIR / 'road_geometry.json'} with {len(centerline_coords)} high-resolution OSM centerline points.")

    print("\n=== DUAL CARRIAGEWAY LAYER GENERATION COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
