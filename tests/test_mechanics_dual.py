"""
tests/test_mechanics_dual.py — Unit tests for dual-mechanics FODA variability & Westergaard / Boussinesq models.
================================================================================================================
"""

import fm


def test_structural_token_codec():
    """Verify ETSI ITS-G5 CAM configuration token encoding and decoding."""
    assert fm.encode_structural_token("Asphalt SMA 11 S") == fm.STRUCTURAL_TOKEN_ASPHALT
    assert fm.encode_structural_token("Concrete JPCP C30/37") == fm.STRUCTURAL_TOKEN_CONCRETE
    assert fm.encode_structural_token("Betondecke") == fm.STRUCTURAL_TOKEN_CONCRETE

    assert fm.decode_structural_token(fm.STRUCTURAL_TOKEN_ASPHALT) == "Asphalt"
    assert fm.decode_structural_token(fm.STRUCTURAL_TOKEN_CONCRETE) == "Concrete"


def test_boussinesq_mixin_mechanics():
    """Verify Boussinesq continuum mechanics mixin deflection and shear calculations."""
    cls = fm.compose_simulation_class(["Asphalt", "Sunny", "Boussinesq"])
    assert cls is not None
    instance = cls()

    wheel_load_n = 57500.0  # 115 kN axle / 2
    contact_radius_m = 0.15  # ~15 cm contact radius

    w0_mm = instance.compute_surface_deflection(wheel_load_n, contact_radius_m)
    tau_kpa = instance.compute_critical_stress(wheel_load_n, contact_radius_m)

    assert 0.3 < w0_mm < 1.2, f"Surface deflection {w0_mm} mm out of physical range for asphalt"
    assert 100.0 < tau_kpa < 400.0, f"Critical shear stress {tau_kpa} kPa out of range"


def test_westergaard_mixin_mechanics():
    """Verify Westergaard rigid slab on Winkler spring foundation mechanics."""
    cls = fm.compose_simulation_class(["Concrete", "Cloudy", "Westergaard"])
    assert cls is not None
    instance = cls()

    wheel_load_n = 57500.0
    contact_radius_m = 0.15

    # Check radius of relative stiffness ell
    ell_m = instance.get_radius_of_relative_stiffness()
    assert 0.7 < ell_m < 1.2, f"Radius of relative stiffness {ell_m} m out of range"

    # Concrete slabs are much stiffer than asphalt, so deflection must be much smaller (~0.1 mm vs ~0.6 mm)
    w0_mm = instance.compute_surface_deflection(wheel_load_n, contact_radius_m)
    assert 0.05 < w0_mm < 0.25, f"Concrete slab deflection {w0_mm} mm out of range"

    # Tensile bending stress at slab bottom
    sigma_bend_kpa = instance.compute_critical_stress(wheel_load_n, contact_radius_m)
    assert 800.0 < sigma_bend_kpa < 2500.0, f"Tensile bending stress {sigma_bend_kpa} kPa out of range"


def test_feature_model_toggling():
    """Verify FODA toggling switches between Boussinesq and Westergaard XOR features."""
    model = fm.clone_feature_model()
    model = fm.toggle_feature(model, "Westergaard")

    active = fm.get_active_features(model)
    assert "Westergaard" in active
    assert "Boussinesq" not in active

    cls = fm.compose_simulation_class(active)
    assert cls is not None
    assert issubclass(cls, fm.WestergaardMixin)
