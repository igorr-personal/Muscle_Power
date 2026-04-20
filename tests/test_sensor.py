"""Tests for sensor_service.py."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from muscle_power.utils.errors import (
    InvalidStatusTransitionError,
    SensorNotFoundError,
    SDKNotInstalledError,
)
from muscle_power.services.sensor_service import (
    SensorManager,
    SensorStatus,
)


# ---------------------------------------------------------------------------
# SensorStatus state machine
# ---------------------------------------------------------------------------

class TestSensorStatus:
    def test_initial_state_is_available(self):
        status = SensorStatus("dev-001")
        assert status.current == "available"

    def test_valid_transitions(self):
        status = SensorStatus("dev-001")
        status.transition_to("in-use")
        assert status.current == "in-use"
        status.transition_to("maintenance")
        assert status.current == "maintenance"
        status.transition_to("available")
        assert status.current == "available"

    def test_invalid_direct_transition_raises(self):
        status = SensorStatus("dev-001")
        with pytest.raises(InvalidStatusTransitionError):
            status.transition_to("available")  # already available

    def test_in_use_to_available_requires_session_complete(self):
        status = SensorStatus("dev-001")
        status.transition_to("in-use")
        with pytest.raises(
            InvalidStatusTransitionError,
            match="Cannot transition from in-use to available without completing session",
        ):
            status.transition_to("available", require_session_complete=True)

    def test_history_log_recorded(self):
        status = SensorStatus("dev-001")
        status.transition_to("in-use")
        status.transition_to("maintenance")
        history = status.get_history()
        assert len(history) >= 2
        assert history[0]["from_status"] == "available"
        assert history[0]["to_status"] == "in-use"
        assert history[1]["from_status"] == "in-use"
        assert history[1]["to_status"] == "maintenance"

    def test_invalid_status_name_raises(self):
        status = SensorStatus("dev-001")
        with pytest.raises(InvalidStatusTransitionError, match="Invalid status"):
            status.transition_to("broken")


# ---------------------------------------------------------------------------
# SensorManager
# ---------------------------------------------------------------------------

class TestSensorManager:
    def test_add_and_get_sensors(self):
        manager = SensorManager()
        sensor1 = MagicMock()
        sensor1.name = "Callibri_MF_001"
        sensor1.state = "Connected"
        sensor1.address = "AA:BB:CC:DD:EE:01"

        sensor2 = MagicMock()
        sensor2.name = "Callibri_MF_002"
        sensor2.state = "Connected"
        sensor2.address = "AA:BB:CC:DD:EE:02"

        manager.add_sensor(sensor1)
        manager.add_sensor(sensor2)

        assert len(manager.connected_sensors) == 2
        assert manager.get_sensor("Callibri_MF_001").state == "Connected"
        assert manager.get_sensor("Callibri_MF_002").state == "Connected"

    def test_remove_sensor(self):
        manager = SensorManager()
        sensor = MagicMock()
        sensor.name = "Callibri_MF_001"
        manager.add_sensor(sensor)
        manager.remove_sensor("Callibri_MF_001")
        assert manager.get_sensor("Callibri_MF_001") is None

    def test_get_nonexistent_returns_none(self):
        manager = SensorManager()
        assert manager.get_sensor("nonexistent") is None


# ---------------------------------------------------------------------------
# connect_sensor convenience helper
# ---------------------------------------------------------------------------

class TestConnectSensor:
    def test_raises_sdk_not_installed_when_no_sdk(self):
        """When SDK is not installed, SDKNotInstalledError should be raised."""
        import muscle_power.services.sensor_service as svc_mod
        original = svc_mod.SDK_AVAILABLE
        svc_mod.SDK_AVAILABLE = False
        try:
            with pytest.raises(SDKNotInstalledError, match="not installed"):
                from muscle_power.services.sensor_service import connect_sensor
                connect_sensor()
        finally:
            svc_mod.SDK_AVAILABLE = original

    def test_happy_path_with_mock_scanner(self):
        """Mocked scanner returns a sensor with expected properties."""
        import muscle_power.services.sensor_service as svc_mod
        if not svc_mod.SDK_AVAILABLE:
            pytest.skip("pyneurosdk2 not installed — skipping live mock test")

        mock_scanner = MagicMock()
        mock_sensor_info = MagicMock()
        mock_sensor_info.name = "Callibri_MF"
        mock_sensor_info.address = "AA:BB:CC:DD:EE:FF"
        mock_scanner.sensors.return_value = [mock_sensor_info]

        mock_sensor = MagicMock()
        mock_sensor.state = "Connected"
        mock_sensor.sampling_frequency = 250
        mock_scanner.create_sensor.return_value = mock_sensor

        with patch(
            "muscle_power.services.sensor_service.Scanner",
            return_value=mock_scanner,
        ):
            from muscle_power.services.sensor_service import connect_sensor
            sensor = connect_sensor()
            assert sensor.state == "Connected"
            assert sensor.sampling_frequency == 250

    def test_no_devices_found_raises(self):
        import muscle_power.services.sensor_service as svc_mod
        if not svc_mod.SDK_AVAILABLE:
            pytest.skip("pyneurosdk2 not installed")

        mock_scanner = MagicMock()
        mock_scanner.sensors.return_value = []

        with patch(
            "muscle_power.services.sensor_service.Scanner",
            return_value=mock_scanner,
        ):
            with pytest.raises(SensorNotFoundError, match="No Callibri sensors found"):
                from muscle_power.services.sensor_service import connect_sensor
                connect_sensor(timeout=0)
