# Continuum Damage Mechanics & Rutting

Real-world highway infrastructure degradation is governed by two coupled physical mechanisms:

1. **Fatigue Micro-Cracking:** Tensile strain cycles at the base of bound asphalt courses.
2. **Permanent Viscoelastic Rutting:** Cumulative plastic shear strain in the wheel tracks under elevated pavement temperatures.

The platform implements **Continuum Damage Mechanics (CDM)**, representing localized deterioration parametrically without requiring non-converging 3D crack mesh generation.

---

## Modulus Degradation Law

In Continuum Damage Mechanics (Kachanov, Lemaitre), material micro-defects reduce the effective load-bearing area. The effective Young's modulus $E_{\text{eff}}$ of a damaged pavement layer is formulated as:

$$E_{\text{eff}} = E_0 \cdot (1 - D)$$

where:

* $E_0$: Initial pristine Young's modulus ($\text{MPa}$).
* $D \in [0.0, 1.0]$: Scalar internal damage variable.
  - $D = 0.0$: Undamaged, virgin pavement.
  - $0.0 < D \le 0.4$: Stable micro-crack progression.
  - $D > 0.5$: Macro-crack coalescence, leading to structural breakdown.

---

## Fatigue Life & Damage Increment (AASHTO MEPDG)

Under repeated axle passes, tensile strain $\varepsilon_t$ at the bottom of the bound asphalt layers causes incremental fatigue accumulation via Miner's hypothesis:

$$\Delta D = \frac{1}{N_f}$$

where allowable repetitions to failure $N_f$ is governed by the phenomenological power law:

$$N_f = k_1 \cdot \left(\frac{1}{\varepsilon_t}\right)^{k_2} \cdot \left(\frac{1}{E_{\text{eff}}}\right)^{k_3}$$

where:

* $\Delta D$: Per-pass incremental Miner fatigue damage added to the bound course.
* $N_f$: Allowable heavy-axle load repetitions before bottom-up fatigue cracking initiates.
* $\varepsilon_t$: Horizontal tensile strain at the underside of the bound asphalt base course.
* $E_{\text{eff}}$: Current degraded asphalt Young's modulus ($\text{MPa}$).
* $k_1, k_2, k_3$: Empirically calibrated AASHTO MEPDG fatigue life regression coefficients for the asphalt mixture.

The tensile strain $\varepsilon_t$ is evaluated from the **Boussinesq strain tensor** via 3D generalized Hooke's law in cylindrical coordinates around the load axis:

$$\varepsilon_t = \frac{\sigma_r - \nu (\sigma_z + \sigma_\theta)}{E_{\text{eff}}}$$

where:

* $\sigma_r$: Radial horizontal stress ($\text{MPa}$).
* $\sigma_z$: Vertical compressive stress ($\text{MPa}$).
* $\sigma_\theta$: Circumferential (hoop) horizontal stress ($\text{MPa}$).
* $\nu$: Asphalt Poisson's ratio.

---

## High-Temperature Viscoelastic Rutting (Creep)

Permanent deformation in asphalt mixtures increases exponentially with temperature when the bitumen binder enters its viscoelastic softening regime ($T > 40^\circ\text{C}$). The incremental rut depth per axle pass $\Delta \text{rut}$ in the wheel path is modeled as:

$$\Delta \text{rut} = C \cdot \left(\frac{F_{\text{axle}}}{100\,\text{kN}}\right)^\alpha \cdot e^{\beta(T_{\text{surface}} - 20^\circ\text{C})} \cdot \left(\frac{v}{80\,\text{km/h}}\right)^{-\gamma}$$

where:

* $\Delta \text{rut}$: Incremental permanent wheel-track rut depth added per axle pass ($\text{mm}$).
* $C$: Empirical asphalt viscoelastic creep calibration constant ($\text{mm/pass}$).
* $F_{\text{axle}}$: Dynamic axle load ($\text{kN}$, calibrated against Weigh-In-Motion).
* $T_{\text{surface}}$: Live asphalt surface temperature from SWIS edge sensors ($^\circ\text{C}$).
* $v$: Cruising velocity ($\text{km/h}$; slower trucks prolong tire dwell time, increasing creep).
* $\alpha \approx 4.0$: AASHTO Fourth Power Law load-damage exponent.
* $\beta \approx 0.08\,\text{K}^{-1}$: Arrhenius temperature sensitivity coefficient.
* $\gamma > 0$: Loading-duration velocity sensitivity exponent.
* $100\,\text{kN},\; 20^\circ\text{C},\; 80\,\text{km/h}$: Standard reference axle load, baseline asphalt temperature, and highway cruising speed.

---

## Composite Road Condition Index

In `world/world.py`, each 100–250 m segment calculates a composite structural health index ($0 \text{ to } 100$):

$$\text{Health}(t) = \max\Big(5, \; \min\big(100, \; 100 \cdot (1 - D_{\text{surface}}) - 1.8 \cdot \text{rut\_depth\_mm}\big)\Big)$$

where:

* $D_{\text{surface}} \in [0, 1]$: Accumulated surface fatigue damage ratio ($0$ pristine to $1$ exhausted).
* $\text{rut\_depth\_mm}$: Cumulative permanent wheel-track rut depth ($\text{mm}$).
* $1.8\,\text{pt/mm}$: Linear serviceability penalty weight converting rut depth into health index points.
* $[5, 100]$: Lower survivable floor ($5$) and undamaged ceiling ($100$) bounding the index.

When $\text{Health} < 60$, the segment turns amber on the GIS map; when $\text{Health} < 40$, it turns red and automatically registers an anomaly alert for autonomous UAV drone dispatch.
