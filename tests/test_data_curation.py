"""
tests/test_data_curation.py — Data Curation & Brokering Subsystem Tests
=======================================================================

Validates the BaseDataBroker contract across Native and FIWARE backends,
testing entity registration, telemetry ingestion, active state retrieval,
historical time-series logging, and dynamic factory selection.
"""

from data_curation import (
    NativeBroker,
    FiwareBroker,
    get_data_broker,
    register_device,
    send_telemetry,
    get_entity,
    get_broker_status,
)


def test_native_broker():
    broker = NativeBroker(max_history_per_device=50)

    # 1. Register device
    ok = broker.register_device(
        device_id="veh_001",
        entity_type="Vehicle",
        static_attributes={"Weight": 18000, "Length": 12},
        geo_data={"geometry": {"coordinates": [13.737, 51.063]}},
    )
    assert ok is True

    # 2. Retrieve entity
    ent = broker.get_entity("veh_001")
    assert ent is not None
    assert ent["id"] == "veh_001"
    assert ent["type"] == "Vehicle"
    assert ent["coordinates"] == [13.737, 51.063]
    assert ent["static_attributes"]["Weight"] == 18000

    # 3. Send telemetry
    broker.send_telemetry(
        device_id="veh_001",
        entity_type="Vehicle",
        sensor_dict={"velocity": 82.5, "load": 115.0},
    )
    ent_updated = broker.get_entity("veh_001")
    assert ent_updated["telemetry"]["velocity"] == 82.5
    assert ent_updated["telemetry"]["load"] == 115.0

    # 4. History log
    hist = broker.get_history("veh_001", count=10)
    assert len(hist) == 1
    assert hist[0]["data"]["velocity"] == 82.5

    # 5. Query multiple entities
    broker.register_device("rsu_001", "Roadside_unit")
    all_ents = broker.get_entities()
    assert len(all_ents) == 2
    veh_only = broker.get_entities("Vehicle")
    assert len(veh_only) == 1
    assert veh_only[0]["id"] == "veh_001"

    # 6. Delete
    assert broker.delete_entity("veh_001") is True
    assert broker.get_entity("veh_001") is None

    # 7. Status
    status = broker.get_status()
    assert status["backend"] == "native"
    assert status["connected"] is True


def test_fiware_broker_contract():
    broker = FiwareBroker()

    ok = broker.register_device(
        device_id="veh_fiware_01",
        entity_type="Vehicle",
        static_attributes={"Weight": 22000},
    )
    assert ok is True

    ok_tel = broker.send_telemetry(
        device_id="veh_fiware_01",
        entity_type="Vehicle",
        sensor_dict={"Velocity": 78.0},
    )
    assert ok_tel is True

    status = broker.get_status()
    assert status["backend"] == "fiware"


def test_factory_and_module_convenience_functions():
    # Test factory switching
    b_native = get_data_broker("native")
    assert isinstance(b_native, NativeBroker)

    b_unknown = get_data_broker("unknown_backend")
    assert isinstance(b_unknown, NativeBroker)

    b_fiware = get_data_broker("fiware")
    assert isinstance(b_fiware, FiwareBroker)

    # Test module convenience functions on active broker
    get_data_broker("native")  # activate native
    assert register_device("test_dev_99", "Vehicle") is True
    assert send_telemetry("test_dev_99", "Vehicle", {"speed": 60}) is True
    ent = get_entity("test_dev_99")
    assert ent is not None
    assert ent["telemetry"]["speed"] == 60

    st = get_broker_status()
    assert st["backend"] == "native"
