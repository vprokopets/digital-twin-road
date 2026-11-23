# Analytical 2D Boussinesq & Westergaard Mechanics

The **2D Pavement Cross-Section Engine** (implemented in `BoussinesqViewer.vue` and `dashboard_backend.py`) provides continuous real-time calculation of internal pavement stresses and surface deflection basins under dynamic multi-axle freight loads.

---

## Mathematical Formulation

Joseph Boussinesq (1885) established the closed-form analytical solution for the state of stress and displacement in a semi-infinite, homogeneous, isotropic, linear-elastic half-space subjected to a normal point load $P$ acting at the surface ($z = 0$).

### Point Load Equations

For a point load $P$ applied at the origin $(0, 0, 0)$, the vertical normal stress $\sigma_z(r, z)$ and vertical displacement $w(r, z)$ at radial distance $r = \sqrt{x^2 + y^2}$ and depth $z > 0$ are given by:

$$\sigma_z(r, z) = \frac{3 P}{2 \pi} \cdot \frac{z^3}{(r^2 + z^2)^{5/2}}$$

$$w(r, z) = \frac{P (1 + \nu)}{2 \pi E} \cdot \left[ \frac{2 (1 - \nu)}{\sqrt{r^2 + z^2}} + \frac{z^2}{(r^2 + z^2)^{3/2}} \right]$$

where:

* $P$: Concentrated vertical point load acting at the surface ($\text{N}$ or $\text{kN}$).
* $\sigma_z(r, z)$: Vertical normal compressive stress at radial offset $r$ and depth $z$ ($\text{Pa}$ or $\text{kPa}$).
* $w(r, z)$: Vertical downward elastostatic displacement at $(r, z)$ ($\text{m}$ or $\text{mm}$).
* $E$: Equivalent Young's modulus of the pavement structure ($\text{kPa}$ or $\text{MPa}$).
* $\nu$: Poisson's ratio (typically $0.35$ for asphalt concrete).
* $z$: Depth below the road surface ($z > 0$).
* $r$: Horizontal distance from the vertical load axis.

---

### Circular Tire Contact Patch Integration

Real vehicle tires do not apply point loads; they exert a distributed contact pressure $p_0$ over a finite area. Assuming a circular contact patch of radius $a$, the contact radius is derived from the tire load $P_{\text{tire}}$ and tire inflation pressure $p_{\text{inflation}}$:

$$a = \sqrt{\frac{P_{\text{tire}}}{\pi \cdot p_{\text{inflation}}}}$$

where:

* $a$: Circular tire-pavement contact patch radius ($\text{m}$).
* $P_{\text{tire}}$: Vertical load carried by a single tire ($\text{N}$; equal to $P_{\text{dyn}}/2$ on single-wheel axles or $P_{\text{dyn}}/4$ on dual-wheel axles).
* $p_{\text{inflation}} \equiv p_0$: Uniform tire contact pressure at the road surface ($\text{Pa}$ or $\text{kPa}$, typically $750\text{–}800\,\text{kPa}$ for HGVs).

Integrating Boussinesq's point-load solution over the circular area of radius $a$ yields the exact centerline vertical stress directly beneath the tire center ($r = 0$):

$$\sigma_z(0, z) = p_0 \left[ 1 - \frac{z^3}{(a^2 + z^2)^{3/2}} \right]$$

At the surface ($z \to 0$), $\sigma_z(0, 0) = p_0$. As depth increases ($z \gg a$), the stress decays inversely with the square of depth, asymptotically matching a point load.

---

### Off-Centerline Lateral Stress Spread

For lateral cross-section evaluation ($r > 0$), the engine applies the generalized Love-Sneddon radial decay operator with an equivalent depth-dependent spread radius $R_{\text{spread}}(z) = \sqrt{a^2 + \beta z^2}$:

$$\sigma_z(r, z) = p_0 \cdot \left[ 1 - \frac{z^3}{(a^2 + z^2)^{3/2}} \right] \cdot \left[ 1 + \left(\frac{r}{R_{\text{spread}}(z)}\right)^2 \right]^{-5/2}$$

where the first bracketed factor captures centerline Boussinesq depth decay and the second applies Love-Sneddon lateral attenuation away from the tire axis:

* $R_{\text{spread}}(z) = \sqrt{a^2 + \beta z^2}$: Effective load-distribution cone radius at depth $z$ ($\text{m}$).
* $\beta$: Dimensionless lateral dispersion cone factor governed by pavement layer stiffness.

---

## Dual-Tire Superposition

Commercial heavy goods vehicles (HGVs) in the European Union utilize dual-tire assemblies ($315/80\text{R}22.5$) on drive and trailer axles, with center-to-center tire spacings of $d_{\text{dual}} \approx 340\,\text{mm}$ (offsets $\pm 170\,\text{mm}$).

By the principle of linear superposition in elastostatics:

$$\sigma_z^{\text{total}}(x, z) = \sigma_z(x - x_{\text{tire}, 1}, z) + \sigma_z(x - x_{\text{tire}, 2}, z)$$

$$w_z^{\text{total}}(x, 0) = w_z(x - x_{\text{tire}, 1}, 0) + w_z(x - x_{\text{tire}, 2}, 0)$$

where:

* $x$: Transverse lateral coordinate across the lane cross-section ($\text{m}$).
* $x_{\text{tire}, 1}, x_{\text{tire}, 2} = \pm d_{\text{dual}}/2$: Lateral offsets of the two tires forming the dual assembly ($\pm 170\,\text{mm}$).
* $\sigma_z^{\text{total}}(x, z)$: Superposed vertical compressive stress beneath both tires ($\text{kPa}$).
* $w_z^{\text{total}}(x, 0)$: Superposed surface deflection basin at $z = 0$ ($\text{m}$ or $\text{mm}$).

---

## Maximum Shear Stress & Rutting Hazard

Viscoelastic rutting and plastic flow in asphalt are driven primarily by maximum shear stress $\tau_{\max}$:

$$\tau_{\max}(x, z) = \frac{\sigma_z(x, z) - \sigma_x(x, z)}{2} \approx \frac{\sigma_z(x, z)}{2} \cdot \left[ 1 - 2\nu + \frac{2(1+\nu)z}{\sqrt{a^2 + z^2}} \right]$$

where:

* $\tau_{\max}(x, z)$: Tresca maximum shear stress driving plastic shear flow and permanent wheel-track rutting ($\text{kPa}$).
* $\sigma_x(x, z)$: Horizontal lateral normal stress generated by Poisson confinement within bound pavement courses ($\text{kPa}$).
* $\nu$: Asphalt Poisson's ratio governing lateral confinement.

Maximum shear stress peaks at a critical sub-surface depth of $z_{\text{crit}} \approx 0.5 a \text{ to } 0.7 a$ (typically $3\,\text{cm to } 8\,\text{cm}$ below the surface), which directly corresponds to the **Asphalt Binder Course** where rutting grooves physically initiate in real highways.

---

## Rigid Concrete Slabs: Westergaard Plate Theory

For rigid concrete pavements (JPCP), the platform solves the **Westergaard Plate on Winkler Spring Foundation** equations. The key governing metric is the **radius of relative stiffness** $\ell$:

$$\ell = \sqrt[4]{\frac{E h^3}{12 (1 - \nu^2) k}}$$

Here $\ell$ (in $\text{m}$) defines the characteristic horizontal length scale over which the rigid concrete slab distributes concentrated wheel loads onto the Winkler spring foundation, where:

* $E$: Young's modulus of concrete ($30{,}000 - 35{,}000\,\text{MPa}$)
* $h$: Slab thickness ($0.22 - 0.28\,\text{m}$)
* $\nu$: Poisson's ratio ($\approx 0.18$)
* $k$: Modulus of subgrade reaction ($50 - 150\,\text{MN/m}^3$)

Critical edge and interior bending tensile stresses are evaluated to verify crack initiation criteria under heavy axle repetitions.

---

## German RStO 12 Standard Pavement Stratification

The engine models the standard German heavy-traffic highway cross-section (Construction Class Bk100, `Asphalt_Bk100_SMA11S` in `scenarios/a14_corridor/pavement_catalog.json`):

| Layer Name | Thickness $h$ | Modulus $E$ (20°C) | Poisson's Ratio $\nu$ | Material Description |
| :--- | :--- | :--- | :--- | :--- |
| **SMA 11 S** | $4.0\,\text{cm}$ | $6{,}500\,\text{MPa}$ | $0.35$ | Stone Mastic Asphalt Surface Course |
| **AC 16 B S** | $8.0\,\text{cm}$ | $8{,}000\,\text{MPa}$ | $0.35$ | Asphalt Concrete Binder Course |
| **AC 22 T S** | $22.0\,\text{cm}$ | $7{,}500\,\text{MPa}$ | $0.35$ | Asphalt Concrete Base Course |
| **FSS (Frostschutz)** | $36.0\,\text{cm}$ | $150\,\text{MPa}$ | $0.40$ | Unbound Crushed Aggregate Frost Protection Layer |
| **Subgrade (Soil)** | Semi-infinite | $80\,\text{MPa}$ | $0.40$ | Compacted natural subgrade soil |
