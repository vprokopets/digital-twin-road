# 1D Subsurface Thermal Diffusion

Pavement structural performance is intrinsically coupled with thermodynamic environmental boundary conditions. Bitumen is a viscoelastic thermoplastic binder: at low winter temperatures ($-10^\circ\text{C}$), asphalt is stiff and brittle ($E \approx 18{,}000\,\text{MPa}$); at elevated summer temperatures ($>50^\circ\text{C}$), it softens exponentially ($E \approx 1{,}500\,\text{MPa}$), rendering the pavement vulnerable to plastic rutting.

---

## Governing Mathematical Formulation

The 1D transient heat conduction equation through the multi-layer stratified road pavement is governed by Fourier's law:

$$\rho(z) \cdot c_p(z) \cdot \frac{\partial T(z, t)}{\partial t} = \frac{\partial}{\partial z} \left( k(z) \cdot \frac{\partial T(z, t)}{\partial z} \right)$$

where:

* $T(z, t)$: Temperature at depth $z$ and time $t$ ($^\circ\text{C}$).
* $\rho(z)$: Layer bulk density ($\text{kg/m}^3$).
* $c_p(z)$: Layer specific heat capacity ($\text{J}/(\text{kg}\cdot\text{K})$).
* $k(z)$: Layer thermal conductivity ($\text{W}/(\text{m}\cdot\text{K})$).

---

## Surface Boundary Condition ($z = 0$)

The road surface experiences dynamic energy exchange with the atmosphere via shortwave solar irradiation, longwave radiative cooling, and sensible convective heat transfer:

$$-k_1 \left. \frac{\partial T}{\partial z} \right|_{z=0} = q_{\text{net}} = q_{\text{solar}} + q_{\text{convection}} + q_{\text{radiation}}$$

where:

* $k_1$: Thermal conductivity of the top wearing course ($\text{W}/(\text{m}\cdot\text{K})$).
* $\left.\frac{\partial T}{\partial z}\right|_{z=0}$: Vertical temperature gradient at the pavement surface ($\text{K}/\text{m}$).
* $q_{\text{net}}$: Net downward conductive heat flux entering the wearing course ($\text{W}/\text{m}^2$).
* $q_{\text{solar}}$: Absorbed shortwave solar irradiance flux ($\text{W}/\text{m}^2$).
* $q_{\text{convection}}$: Sensible convective heat exchange with ambient air ($\text{W}/\text{m}^2$).
* $q_{\text{radiation}}$: Net longwave infrared radiative cooling or warming with the sky ($\text{W}/\text{m}^2$).

### 1. Shortwave Solar Absorption

$$q_{\text{solar}} = (1 - \alpha) \cdot I_{\text{global}}(t)$$

where $\alpha$ is the surface albedo ($0.15$ for dark asphalt, $0.35$ for light concrete), $(1 - \alpha)$ is the resulting surface solar absorptivity, and $I_{\text{global}}(t)$ is incident solar irradiance ($\text{W}/\text{m}^2$).

### 2. Sensible Convective Heat Flux

$$q_{\text{convection}} = h_c \cdot (T_{\text{air}} - T_{\text{surface}})$$

where:

* $h_c = 5.7 + 3.8 \cdot v_{\text{wind}}$: Wind-dependent surface convective heat transfer coefficient ($\text{W}/(\text{m}^2\cdot\text{K})$).
* $T_{\text{air}}$: Ambient air temperature measured by the roadside weather station ($^\circ\text{C}$).
* $T_{\text{surface}}$: Pavement skin temperature at $z = 0$ ($^\circ\text{C}$).
* $v_{\text{wind}}$: Near-surface wind speed ($\text{m/s}$).

---

## Bottom Boundary Condition ($z = z_{\text{deep}}$)

At depth $z = 1.5\,\text{m}$ (hydrological ground table / undisturbed soil depth), the boundary temperature is held at the seasonal soil equilibrium temperature $T_{\text{soil}}$ (or coupled with the subsurface water table distance in `road_water_sources.json`):

$$T(z = 1.5\,\text{m}, t) = T_{\text{soil}}$$

---

## Thermal Resistance Stratification

In steady-state evaluation (as implemented in `fem_solver.py` and `compute_thermal_distribution` in `dashboard_backend.py`), total thermal resistance through $N$ pavement layers is computed as:

$$R_{\text{total}} = \sum_{i=1}^{N} \frac{h_i}{k_i}$$

The temperature at any intermediate layer interface $z_m$ is determined via proportional thermal resistance:

$$T(z_m) = T_{\text{surface}} - (T_{\text{surface}} - T_{\text{soil}}) \cdot \frac{\sum_{i=1}^{m} \frac{h_i}{k_i}}{R_{\text{total}}}$$

where:

* $N$: Total number of stratified RStO 12 pavement and subgrade layers.
* $h_i$: Thickness of layer $i$ ($\text{m}$).
* $k_i$: Thermal conductivity of layer $i$ ($\text{W}/(\text{m}\cdot\text{K})$).
* $R_{\text{total}}$: Total series thermal resistance across the full $N$-layer column ($\text{m}^2\cdot\text{K}/\text{W}$).
* $z_m$: Depth of the bottom interface of layer $m$ ($1 \le m \le N$).

This analytical formulation executes in **$<0.05\,\text{ms}$**, enabling the frontend `ThermalSimulation.vue` probe to recompute thermal profiles instantaneously as users adjust air and soil temperature parameters.
