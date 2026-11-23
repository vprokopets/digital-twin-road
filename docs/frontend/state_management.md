# Reactive State Management & Delta Replay

The Pinia store in `frontend/src/stores/dashboard.ts` manages the reactive digital shadow state, handling the split between static GIS geometries and high-frequency dynamic delta streams.

---

## Static Initialization & SSE Delta Replay

1. **Phase 1 (One-Time Startup):** The frontend calls `fetchStaticLayers()` via `GET /dashboard/static_layers`. Heavy road curves, 1,215 road segments, junctions, and water bodies are cached in Pinia state.

2. **Phase 2 (5-Second Delta Stream):** The frontend connects to `GET /dashboard/stream` via the browser's native `EventSource` API. When a message arrives with `data.is_delta === true`:

```typescript
// Apply dirty_segments mutations in-place on cached road_segments
const dirty: Record<string, number> = incomingLayers.dirty_segments || {}
if (Object.keys(dirty).length > 0) {
    const segFeatures = existingLayers.road_segments?.features
    if (Array.isArray(segFeatures)) {
        for (const f of segFeatures) {
            const pid = String(f.properties?.point_id ?? f.properties?.id ?? '')
            const sid = String(f.properties?.id ?? '')
            if (dirty[pid] !== undefined) f.properties.state = dirty[pid]
            else if (dirty[sid] !== undefined) f.properties.state = dirty[sid]
        }
    }
}

// Update moving entities without recreating static layers
this.digitalShadowRaw = {
    ...this.digitalShadowRaw,
    map_layers: {
        ...existingLayers,
        vehicles: incomingLayers.vehicles,
        drones: incomingLayers.drones,
        warnings: incomingLayers.warnings,
        dirty_segments: dirty,
    }
}
```

---

## Benefits of In-Place Property Mutation

* **No Layer Rebuilds:** Leaflet polyline paths and GIS GeoJSON instances are never destroyed or re-created during continuous simulation.
* **Instant Color Shifts:** Because Leaflet path styles read from `f.properties.state`, mutating the state in-place triggers Leaflet canvas repainting with zero DOM allocations.
* **Zero Garbage Collection Spikes:** Moving vehicle markers are updated by updating their coordinates, eliminating memory churn and GC pauses.
