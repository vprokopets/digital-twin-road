"""
world/road.py — Highway Corridor Geometry, Centerline Segmentation & Spatial Indexing
=====================================================================================

Builds bidirectional highway segment collections, precomputed O(log M) binary-search
station indices (`road_points_by_dir`, `road_seg_starts_dir1/2`), and nearest RSU/water
associations for corridor infrastructure.
"""

import bisect
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List
import geopy.distance as gp

from world.geo_utils import Auxiliary, WGS84CoordSystem, get_coord_system


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Fast spherical Haversine distance in kilometers."""
    return WGS84CoordSystem().distance_km(lon1, lat1, lon2, lat2)


class Road:
    """Models corridor geometry, directional segment indexing, and nearest-infrastructure lookups."""

    def __init__(
        self,
        road_properties: Dict[str, Any],
        road_geometry: Dict[str, Any],
        road_configuration: Dict[str, Any],
        road_spawn_metadata: Dict[str, Any],
        road_water_metadata: Dict[str, Any],
        roadside_units: Dict[str, Any],
    ) -> None:
        self.id = id(self)
        self.aux_methods = Auxiliary()
        self.road_structure_metadata_processed = {
            "type": "FeatureCollection",
            "features": []
        }

        configs_dir = Path(__file__).resolve().parent.parent / "configs"
        curves_file = configs_dir / "road_curves.geojson"
        segments_file = configs_dir / "road_segments.geojson"

        # Load from active scenario bundle (with fallback to configs/)
        from world.scenario_loader import get_active_scenario
        scenario = get_active_scenario()
        self.coord_system = get_coord_system(scenario.coordinate_system)
        self.road_curves = None
        self.road_segments = None

        if scenario.road_curves and scenario.road_segments:
            self.road_curves = scenario.road_curves
            self.road_segments = scenario.road_segments
        elif curves_file.exists() and segments_file.exists():
            with open(curves_file) as f:
                self.road_curves = json.load(f)
            with open(segments_file) as f:
                self.road_segments = json.load(f)

        if self.road_curves and self.road_segments:

            self.road_segments_by_id = {
                s['properties']['id']: s for s in self.road_segments['features']
            }

            self.road_segments_dir1 = [s for s in self.road_segments['features'] if s['properties'].get('direction', 1) == 1]
            self.road_segments_dir1.sort(key=lambda s: s['properties']['station_start_km'])
            self.road_segments_dir2 = [s for s in self.road_segments['features'] if s['properties'].get('direction', 1) == -1]
            self.road_segments_dir2.sort(key=lambda s: s['properties']['station_start_km'])
            self.road_seg_starts_dir1 = [s['properties']['station_start_km'] for s in self.road_segments_dir1]
            self.road_seg_starts_dir2 = [s['properties']['station_start_km'] for s in self.road_segments_dir2]

            # Build discrete health point nodes on the exact OpenStreetMap road centerline for BOTH directions
            for i, seg in enumerate(self.road_segments['features']):
                props = seg['properties']
                direction = props.get('direction', 1)
                coords = seg['geometry']['coordinates']
                mid_coord = coords[len(coords) // 2]
                dist = props.get('station_mid_km', props.get('station_start_km', 0.0))

                point_id = props.get('point_id', f"road_pt_dir{1 if direction == 1 else 2}_{i}")
                carriageway = props.get('carriageway', 'Dresden → Leipzig' if direction == 1 else 'Leipzig → Dresden')

                self.road_structure_metadata_processed['features'].append({
                    "type": "Feature",
                    "properties": {
                        "id": point_id,
                        "segment_id": props.get('id', f"road_seg_dir{1 if direction == 1 else 2}_{i}"),
                        "name": props.get('name', f"Road Point {point_id}"),
                        "direction": direction,
                        "carriageway": carriageway,
                        "state": round(props.get('state', 100)),
                        "dist": dist,
                        "station_start_km": props.get('station_start_km', dist),
                        "station_end_km": props.get('station_end_km', dist),
                        "length_m": props.get('length_m', 200.0),
                        "road": props.get('road', 'RoadStructure_1'),
                        "road_name": props.get('road_name', ''),
                        "lanes": props.get('lanes', 2),
                        "ClosestWater": 1e6,
                        "ClosestWaterDist": 1e6,
                        "ClosestRU": 1e6,
                        "ClosestRoadsideUnitId": None
                    },
                    "geometry": {
                        "coordinates": mid_coord,
                        "type": "Point"
                    }
                })

            # Update ClosestPoint and ClosestPointDist for infrastructure points
            for point in self.road_structure_metadata_processed['features']:
                pt_lat = point['geometry']['coordinates'][1]
                pt_lon = point['geometry']['coordinates'][0]
                total_dist = point['properties']['dist']

                for cfg_pt in road_configuration['features']:
                    c = cfg_pt['geometry']['coordinates']
                    dist = self.coord_system.distance_km(pt_lon, pt_lat, c[0], c[1])
                    if dist < cfg_pt['properties'].get('ClosestPointDist', 1e6):
                        cfg_pt['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist})

                for sp_pt in road_spawn_metadata['features']:
                    c = sp_pt['geometry']['coordinates']
                    dist = self.coord_system.distance_km(pt_lon, pt_lat, c[0], c[1])
                    if dist < sp_pt['properties'].get('ClosestPointDist', 1e6):
                        sp_pt['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist})

                for w_pt in road_water_metadata['features']:
                    c = w_pt['geometry']['coordinates']
                    dist = self.coord_system.distance_km(pt_lon, pt_lat, c[0], c[1])
                    if dist < w_pt['properties'].get('ClosestPointDist', 1e6):
                        w_pt['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist})

                for ru_pt in roadside_units['features']:
                    c = ru_pt['geometry']['coordinates']
                    dist = self.coord_system.distance_km(pt_lon, pt_lat, c[0], c[1])
                    if dist < ru_pt['properties'].get('ClosestPointDist', 1e6):
                        ru_pt['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist})

            # Match ClosestRoadsideUnit and ClosestWater
            for point in self.road_structure_metadata_processed['features']:
                pt_dist = point['properties']['dist']

                min_water_diff = 1e6
                closest_water_pos = 0.0
                for water_point in road_water_metadata['features']:
                    w_closest = water_point['properties'].get('ClosestPoint', 0.0)
                    diff = abs(pt_dist - w_closest)
                    if diff < min_water_diff:
                        min_water_diff = diff
                        closest_water_pos = w_closest
                point['properties']['ClosestWater'] = closest_water_pos
                point['properties']['ClosestWaterDist'] = min_water_diff

                min_ru_diff = 1e6
                closest_ru = None
                for ru_point in roadside_units['features']:
                    ru_closest = ru_point['properties'].get('ClosestPoint', 0.0)
                    diff = abs(pt_dist - ru_closest)
                    if diff < min_ru_diff:
                        min_ru_diff = diff
                        closest_ru = ru_point
                point['properties']['ClosestRU'] = min_ru_diff
                point['properties']['ClosestRoadsideUnitId'] = (
                    closest_ru['properties'].get('id') if closest_ru else None
                )

            # Ensure road structure assignment is consistent per direction
            max_road_index = len(road_configuration['features']) - 2
            for target_dir in [1, -1]:
                current_road_index = 0
                dir_points = [p for p in self.road_structure_metadata_processed['features'] if p['properties'].get('direction', 1) == target_dir]
                dir_points.sort(key=lambda p: p['properties']['dist'])
                for point in dir_points:
                    while current_road_index < max_road_index:
                        next_split = road_configuration['features'][current_road_index + 1]['properties']['ClosestPoint']
                        if point['properties']['dist'] > next_split:
                            current_road_index += 1
                        else:
                            break
                    point['properties']['road'] = f'RoadStructure_{current_road_index}'

        else:
            # Fallback legacy interpolation
            self.road_curves = None
            self.road_segments = None
            self.road_segments_by_id = {}
            discr = 0.1
            total_dist = 0
            leftover = 0
            coord = road_geometry['features'][0]['geometry']['coordinates']
            for index in range(1, len(coord)):
                prev_pt = coord[index - 1]
                curr_pt = coord[index]
                dist_to_prev = gp.distance(prev_pt, curr_pt)
                brng = self.aux_methods.calculate_bearing(prev_pt, curr_pt)
                next_pt_dist = leftover
                while next_pt_dist < dist_to_prev:
                    total_dist += discr
                    next_pt_coord = gp.distance(next_pt_dist).destination(prev_pt, brng).format_decimal()
                    for point in road_configuration['features']:
                        dist = gp.distance(next_pt_coord, point['geometry']['coordinates'])
                        if dist.kilometers < point['properties']['ClosestPointDist']:
                            point['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist.kilometers})

                    for point in road_spawn_metadata['features']:
                        dist = gp.distance(next_pt_coord, point['geometry']['coordinates'])
                        if dist.kilometers < point['properties']['ClosestPointDist']:
                            point['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist.kilometers})

                    for point in road_water_metadata['features']:
                        dist = gp.distance(next_pt_coord, point['geometry']['coordinates'])
                        if dist.kilometers < point['properties']['ClosestPointDist']:
                            point['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist.kilometers})

                    for point in roadside_units['features']:
                        dist = gp.distance(next_pt_coord, point['geometry']['coordinates'])
                        if dist.kilometers < point['properties']['ClosestPointDist']:
                            point['properties'].update({'ClosestPoint': total_dist, 'ClosestPointDist': dist.kilometers})

                    base_state = 75 + 15 * math.sin(total_dist * 2)
                    island_effect = 20 * math.sin(total_dist / 0.75)
                    final_state = base_state + island_effect + random.uniform(-5, 5)
                    final_state = max(10, min(99, final_state))

                    point_id = f"road_pt_{len(self.road_structure_metadata_processed['features'])}"
                    self.road_structure_metadata_processed['features'].append({
                        "type": "Feature",
                        "properties": {
                            "id": point_id,
                            "state": round(final_state),
                            "dist": total_dist,
                            "ClosestWater": 1e6,
                            "ClosestRU": 1e6,
                        },
                        "geometry": {
                            "coordinates": [float(x) for x in next_pt_coord.split(',')],
                            "type": "Point"
                        }
                    })
                    next_pt_dist += discr
                    leftover = abs((dist_to_prev - gp.Distance(next_pt_dist)).kilometers)

            current_road_index = 0
            for point in self.road_structure_metadata_processed['features']:
                if current_road_index + 1 < len(road_configuration['features']) and point['properties']['dist'] > road_configuration['features'][current_road_index + 1]['properties']['ClosestPoint']:
                    current_road_index += 1
                min_water_diff = 1e6
                closest_water_pos = 0.0
                for water_point in road_water_metadata['features']:
                    w_station = water_point['properties'].get('ClosestPoint', 0.0)
                    diff = abs(point['properties']['dist'] - w_station)
                    if diff < min_water_diff:
                        min_water_diff = diff
                        closest_water_pos = w_station
                point['properties']['ClosestWater'] = closest_water_pos
                point['properties']['ClosestWaterDist'] = min_water_diff

                min_ru_diff = 1e6
                closest_ru = None
                for ru_point in roadside_units['features']:
                    ru_station = ru_point['properties'].get('ClosestPoint', 0.0)
                    diff = abs(point['properties']['dist'] - ru_station)
                    if diff < min_ru_diff:
                        min_ru_diff = diff
                        closest_ru = ru_point
                point['properties']['ClosestRU'] = min_ru_diff
                point['properties']['ClosestRoadsideUnitId'] = (
                    closest_ru['properties'].get('id') if closest_ru else None
                )
                point['properties'].update({'road': f'RoadStructure_{current_road_index}'})

        # Build sorted directional point indices for O(log M) binary search in find_closest_point and update_road_state
        self.road_points_by_dir = {}
        self.road_dists_by_dir = {}
        for target_dir in (1, -1):
            pts = [
                p for p in self.road_structure_metadata_processed['features']
                if p['properties'].get('direction', 1) == target_dir
            ]
            pts.sort(key=lambda p: p['properties']['dist'])
            self.road_points_by_dir[target_dir] = pts
            self.road_dists_by_dir[target_dir] = [p['properties']['dist'] for p in pts]

        # Set up lightweight simulation metadata for each road point
        for point in self.road_structure_metadata_processed['features']:
            road_type = point['properties']['road']
            road_cfg = road_properties.get(road_type, {})
            mat_dict = road_cfg.get('RoadType', {'Asphalt': {}})
            material_name = next(iter(mat_dict.keys()), 'Asphalt') if isinstance(mat_dict, dict) else 'Asphalt'
            point.update({'simulation': {'Type': material_name, 'RoadStructure': road_type}})

    def get_points_in_range(self, direction: int, p_min: float, p_max: float) -> List[Dict[str, Any]]:
        """Returns road points in [p_min, p_max] for `direction` in O(log M) time via binary search."""
        pts = self.road_points_by_dir.get(direction)
        dists = self.road_dists_by_dir.get(direction)
        if not pts or not dists:
            return [
                p for p in self.road_structure_metadata_processed['features']
                if p['properties'].get('direction', 1) == direction and p_min <= p['properties']['dist'] <= p_max
            ]
        lo = bisect.bisect_left(dists, p_min)
        hi = bisect.bisect_right(dists, p_max)
        return pts[lo:hi]
