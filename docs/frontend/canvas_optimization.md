# Canvas Rendering Optimization (60 FPS)

The user interface achieves locked 60 FPS performance across the full-corridor GIS map and interactive millisecond-scale redraws on the analytical Boussinesq stress cross-section viewer by eliminating browser DOM bottlenecks.

---

## 1. Leaflet Canvas Rendering (`preferCanvas: true`)

The highway corridor models 1,215 road segments and over 10,000 polyline curve vertices.

* **Standard SVG Mode (Antipattern):** Creating standard Leaflet SVG paths forces the browser to manage 2,400+ distinct SVG DOM nodes. Panning and zooming triggers extensive DOM reflow and layout thrashing, dropping frame rates to 15–25 FPS.
* **HTML5 Canvas Renderer:** Initializing Leaflet with `preferCanvas: true` draws all road polylines, water bodies, and RSU coverage circles directly onto a single hardware-accelerated `<canvas>` element. Vector rendering execution drops to **$<1.5\,\text{ms}$ per frame**.

---

## 2. Zoom-Animation Guard

During Leaflet zoom transitions (`zoomstart` to `zoomend`), updating vehicle positions mid-scale causes visual marker jitter. The `DashboardMap.vue` controller pauses the `requestAnimationFrame` dead-reckoning extrapolation while the map is actively animating zoom, resuming instantly upon `zoomend`.

---

## 3. Boussinesq Offscreen ImageData Blit

The 2D Boussinesq stress viewer (`BoussinesqViewer.vue`) renders a grid of $140 \times 80 = 11{,}200$ cells (transverse cross-section) or $160 \times 80 = 12{,}800$ cells (longitudinal side view) smoothly as the user drags wheel load or contact pressure sliders.

### Legacy Antipattern
The original renderer looped through every grid cell and called `ctx.fillRect()` with individual `ctx.fillStyle` string assignments on every frame:

```typescript
// Up to 12,800 separate canvas state changes per frame!
for (let iz = 0; iz < nz; iz++) {
  for (let ix = 0; ix < nx; ix++) {
    ctx.fillStyle = getColormapRGBA(...)
    ctx.fillRect(x, z, cellW, cellH)
  }
}
```

### Modern Offscreen Blit Optimization
The optimized engine maintains a hidden offscreen `<canvas>` matching the exact numerical grid dimensions ($140 \times 80$ or $160 \times 80$). Pixels are written directly into a 32-bit integer view (`Uint32Array`) of an `ImageData` buffer in native memory:

```typescript
const offscreenCanvas = document.createElement('canvas')
offscreenCanvas.width = gridNx
offscreenCanvas.height = gridNz
const offCtx = offscreenCanvas.getContext('2d')
const imgData = offCtx.createImageData(gridNx, gridNz)
const buf32 = new Uint32Array(imgData.data.buffer)

// Write raw 32-bit ABGR color integers in one fast loop
for (let i = 0; i < totalCells; i++) {
  buf32[i] = colormapUint32(normalizedStress[i])
}
offCtx.putImageData(imgData, 0, 0)

// Single draw call scales the texture smoothly onto the display canvas
ctx.imageSmoothingEnabled = true
ctx.drawImage(offscreenCanvas, x0, z0, renderWidth, renderHeight)
```

### Architecture Impact

* **Draw Call Count:** Reduced from **11,200–12,800 `fillRect` calls** to **1 `putImageData` + 1 `drawImage` blit**.
* **Responsiveness:** Field computation and pixel blitting complete in **< 2 ms**, keeping slider dragging responsive without UI frame drops.
