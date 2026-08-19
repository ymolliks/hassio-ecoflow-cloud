import inspect
import logging
import struct
from datetime import timedelta
from decimal import Decimal
from typing import Any, Mapping, OrderedDict

import jsonpath_ng.ext as jp
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import (SensorDeviceClass, SensorStateClass, SensorEntity)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (PERCENTAGE,
                                 UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfEnergy, UnitOfFrequency,
                                 UnitOfPower, UnitOfTemperature, UnitOfTime)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt

from . import ECOFLOW_DOMAIN, ATTR_STATUS_SN, ATTR_STATUS_DATA_LAST_UPDATE, ATTR_STATUS_LAST_UPDATE, \
    ATTR_STATUS_RECONNECTS, \
    ATTR_STATUS_PHASE, ATTR_MQTT_CONNECTED, ATTR_QUOTA_REQUESTS
from .api import EcoflowApiClient
from .devices import BaseDevice
from .entities import BaseSensorEntity, EcoFlowAbstractEntity, EcoFlowDictEntity

_LOGGER = logging.getLogger(__name__)

# HA 2025.8 added a `hass` argument to IntegrationSensor.__init__ and 2026.8 removed it again
_INTEGRATION_SENSOR_TAKES_HASS = "hass" in inspect.signature(IntegrationSensor.__init__).parameters

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    client: EcoflowApiClient = hass.data[ECOFLOW_DOMAIN][entry.entry_id]
    for (sn, device) in client.devices.items():
        sensors = device.sensors(client)
        async_add_entities(sensors)

        # Add integral energy sensors for power sensors that have it enabled
        integral_sensors = filter(lambda s: isinstance(s, WattsSensorEntity) and s.energy_enabled(), sensors)
        async_add_entities([s.energy_sensor() for s in integral_sensors])


class MiscBinarySensorEntity(BinarySensorEntity, EcoFlowDictEntity):

    def _update_value(self, val: Any) -> bool:
        self._attr_is_on = bool(val)
        return True
    

class ChargingStateSensorEntity(BaseSensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:battery-charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def _update_value(self, val: Any) -> bool:
        if val == 0:
            return super()._update_value("unused")
        elif val == 1:
            return super()._update_value("charging")
        elif val == 2:
            return super()._update_value("discharging")
        else:
            return False


class CyclesSensorEntity(BaseSensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:battery-heart-variant"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING


class FanSensorEntity(BaseSensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:fan"


class MiscSensorEntity(BaseSensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC


class LevelSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT


class StateOfHealthSensorEntity(BaseSensorEntity):
    # State of health is a battery wear/health percentage, not the amount of
    # charge left, so it must not use the BATTERY device class (HA defines that
    # as "percentage of battery that is left").
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT


class RemainSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0

    def _update_value(self, val: Any) -> Any:
        ival = int(val)
        if ival < 0 or ival > 5000:
            ival = 0

        return super()._update_value(ival)


class SecondsRemainSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0

    def _update_value(self, val: Any) -> Any:
        ival = int(val)
        if ival < 0 or ival > 5000:
            ival = 0

        return super()._update_value(ival)


class TempSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = -1

class CelsiusSensorEntity(TempSensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val))

class DecicelsiusSensorEntity(TempSensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)

class MilliCelsiusSensorEntity(TempSensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 100)

class VoltSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0


class MilliVoltSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfElectricPotential.MILLIVOLT
    _attr_suggested_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 3

class BeSensorEntity(BaseSensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(struct.unpack('<I', struct.pack('>I', val))[0]))

class BeMilliVoltSensorEntity(BeSensorEntity):
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfElectricPotential.MILLIVOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0

class InMilliVoltSensorEntity(MilliVoltSensorEntity):
    _attr_icon = "mdi:transmission-tower-import"
    _attr_suggested_display_precision = 0


class OutMilliVoltSensorEntity(MilliVoltSensorEntity):
    _attr_icon = "mdi:transmission-tower-export"
    _attr_suggested_display_precision = 0


class DecivoltSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.VOLTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfElectricPotential.VOLT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0

    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class CentivoltSensorEntity(DecivoltSensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class AmpSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.MILLIAMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0


class MilliampSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.MILLIAMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0


class DeciampSensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0

    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class WattsSensorEntity(BaseSensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_value = 0

    def __init__(self, client, device, mqtt_key, title, enabled=True, auto_enable=False):
        super().__init__(client, device, mqtt_key, title, enabled, auto_enable)
        self._energy_enabled = False
        self._energy_enabled_default = True

    def with_energy(self, enabled_default: bool = True):
        self._energy_enabled = True
        self._energy_enabled_default = enabled_default
        return self

    def energy_enabled(self) -> bool:
        return self._energy_enabled

    def energy_sensor(self):
        if not self._energy_enabled:
            return None
        return IntegralEnergySensorEntity(self, self._energy_enabled_default)


class EnergySensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def _update_value(self, val: Any) -> bool:
        ival = int(val)
        if ival > 0:
            return super()._update_value(ival)
        else:
            return False


class CapacitySensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.CURRENT
    _attr_native_unit_of_measurement = "mAh"
    _attr_state_class = SensorStateClass.MEASUREMENT


class DeciwattsSensorEntity(WattsSensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class InWattsSensorEntity(WattsSensorEntity):
    _attr_icon = "mdi:transmission-tower-import"


class InWattsSolarSensorEntity(InWattsSensorEntity):
    _attr_icon = "mdi:solar-power"

    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class SolarInPowerSensorEntity(InWattsSensorEntity):
    """Combined solar input power (PV1 + PV2) for dual-MPPT devices.

    mppt.inWatts / mppt.pv2InWatts are already expressed in watts, so no
    scaling is applied (unlike InWattsSolarSensorEntity).
    """

    _attr_icon = "mdi:solar-power"

    def __init__(self, client, device, title, enabled=True, auto_enable=False):
        super().__init__(client, device, "mppt.inWatts", title, enabled, auto_enable)
        # The base mqtt key is shared with the "Solar (1) In Power" sensor, so
        # give this combined sensor its own unique id.
        self._attr_unique_id = f"ecoflow-{self._type_prefix()}{self._device.device_info.sn}-solar-in-power"
        self._pv2_key_expr = jp.parse(self._adopt_json_key("mppt.pv2InWatts"))

    def _updated(self, data: dict[str, Any]):
        pv1 = self._mqtt_key_expr.find(data)
        pv2 = self._pv2_key_expr.find(data)
        if len(pv1) == 1 and len(pv2) == 1:
            self._attr_available = True
            v1 = pv1[0].value
            v2 = pv2[0].value
            total = (int(v1) if v1 is not None else 0) + (int(v2) if v2 is not None else 0)
            if self._update_value(total):
                self.schedule_update_ha_state()


class OutWattsSensorEntity(WattsSensorEntity):
    _attr_icon = "mdi:transmission-tower-export"


class OutWattsDcSensorEntity(WattsSensorEntity):
    _attr_icon = "mdi:transmission-tower-export"

    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class InVoltSensorEntity(VoltSensorEntity):
    _attr_icon = "mdi:transmission-tower-import"

class InVoltSolarSensorEntity(VoltSensorEntity):
    _attr_icon = "mdi:solar-power"

    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)

class OutVoltDcSensorEntity(VoltSensorEntity):
    _attr_icon = "mdi:transmission-tower-export"
    
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)      

class InAmpSensorEntity(AmpSensorEntity):
    _attr_icon = "mdi:transmission-tower-import"

class InAmpSolarSensorEntity(AmpSensorEntity):
    _attr_icon = "mdi:solar-power"

    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) * 10)


class OutMilliampSensorEntity(MilliampSensorEntity):
    _attr_icon = "mdi:transmission-tower-export"


class InMilliampSensorEntity(MilliampSensorEntity):
    _attr_icon = "mdi:transmission-tower-import"


class InEnergySensorEntity(EnergySensorEntity):
    _attr_icon = "mdi:transmission-tower-import"


class OutEnergySensorEntity(EnergySensorEntity):
    _attr_icon = "mdi:transmission-tower-export"


class InEnergySolarSensorEntity(InEnergySensorEntity):
    _attr_icon = "mdi:solar-power"


class IntegralEnergySensorEntity(IntegrationSensor):
    """Energy (kWh) computed by integrating a power sensor over time.

    EcoFlow stopped providing per-input accumulated energy values (e.g. the
    old pd.chgSunPower key), so energy is derived from the live power reading
    using HA's integration sensor, exactly like upstream tolwi does.
    """

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 1

    def __init__(self, base: WattsSensorEntity, enabled_default: bool = True):
        version_kwargs: dict[str, Any] = {"hass": base.coordinator.hass} if _INTEGRATION_SENSOR_TAKES_HASS else {}
        super().__init__(
            **version_kwargs,
            integration_method="left",
            name=f"{base._device.device_info.name} {base._attr_name.replace(' Power', ' Energy')}",
            round_digits=4,
            source_entity=base.entity_id,
            unique_id=f"{base._attr_unique_id}_energy",
            unit_prefix="k",
            unit_time=UnitOfTime.HOURS,
            max_sub_interval=timedelta(seconds=60),
        )
        self._attr_device_info = base.device_info
        self._attr_entity_registry_enabled_default = enabled_default and base.enabled_default
        # Seed the integral at 0 so the sensor reports a value even before the
        # source power changes for the first time (IntegrationSensor only
        # computes once the source emits a state change/report).
        self._state = Decimal(0)


class FrequencySensorEntity(BaseSensorEntity):
    _attr_device_class = SensorDeviceClass.FREQUENCY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
    _attr_state_class = SensorStateClass.MEASUREMENT


class DecihertzSensorEntity(FrequencySensorEntity):
    def _update_value(self, val: Any) -> bool:
        return super()._update_value(int(val) / 10)


class StatusSensorEntity(SensorEntity, EcoFlowAbstractEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client: EcoflowApiClient,  device: BaseDevice):
        super().__init__(client, device, "Status", "status")
        self._online = -1
        self._last_update = dt.utcnow().replace(year=2000, month=1, day=1, hour=0, minute=0, second=0)
        self._skip_count = 0
        self._offline_skip_count = int(120 / self.coordinator.update_interval.seconds) # 2 minutes
        self._attrs = OrderedDict[str, Any]()
        self._attrs[ATTR_STATUS_SN] = self._device.device_info.sn
        self._attrs[ATTR_STATUS_DATA_LAST_UPDATE] = None
        self._attrs[ATTR_MQTT_CONNECTED] = None

    def _handle_coordinator_update(self) -> None:
        changed = False
        update_time = self.coordinator.data.data_holder.last_received_time()
        if self._last_update < update_time:
            self._last_update = max(update_time, self._last_update)
            self._attrs[ATTR_STATUS_DATA_LAST_UPDATE] = update_time
            self._attrs[ATTR_MQTT_CONNECTED] = self._client.mqtt_client.is_connected()
            self._skip_count = 0
            changed = True
        else:
            self._skip_count += 1

        changed = self._actualize_status() or changed

        if changed:
            self.schedule_update_ha_state()

    def _actualize_status(self) -> bool:
        changed = False
        if self._online != 0 and self._skip_count >= self._offline_skip_count:
            self._online = 0
            self._attr_native_value = "assume_offline"
            self._attrs[ATTR_MQTT_CONNECTED] = self._client.mqtt_client.is_connected()
            changed = True
        elif self._online != 1 and self._skip_count == 0:
            self._online = 1
            self._attr_native_value = "online"
            self._attrs[ATTR_MQTT_CONNECTED] = self._client.mqtt_client.is_connected()
            changed = True
        return changed

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        return self._attrs

class QuotaStatusSensorEntity(StatusSensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, client: EcoflowApiClient, device: BaseDevice):
        super().__init__(client, device)
        self._attrs[ATTR_QUOTA_REQUESTS] = 0

    def _actualize_status(self) -> bool:
        changed = False
        if self._online != 0 and self._skip_count >= self._offline_skip_count * 2:
            self._online = 0
            self._attr_native_value = "assume_offline"
            self._attrs[ATTR_MQTT_CONNECTED] = self._client.mqtt_client.is_connected()
            changed = True
        elif self._online != 0 and self._skip_count >= self._offline_skip_count:
            self.hass.async_create_background_task(self._client.quota_all(self._device.device_info.sn), "get quota")
            self._attrs[ATTR_QUOTA_REQUESTS] = self._attrs[ATTR_QUOTA_REQUESTS] + 1
            changed = True
        elif self._online != 1 and self._skip_count == 0:
            self._online = 1
            self._attr_native_value = "online"
            self._attrs[ATTR_MQTT_CONNECTED] = self._client.mqtt_client.is_connected()
            changed = True
        return changed


class ReconnectStatusSensorEntity(StatusSensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    CONNECT_PHASES = [3, 5, 7]

    def __init__(self, client: EcoflowApiClient, device: BaseDevice):
        super().__init__(client, device)
        self._attrs[ATTR_STATUS_PHASE] = 0
        self._attrs[ATTR_STATUS_RECONNECTS] = 0

    def _actualize_status(self) -> bool:
        time_to_reconnect = self._skip_count in self.CONNECT_PHASES

        if self._online == 1 and time_to_reconnect:
            self._attrs[ATTR_STATUS_RECONNECTS] = self._attrs[ATTR_STATUS_RECONNECTS] + 1
            self._client.mqtt_client.reconnect()
            return True
        else:
            return super()._actualize_status()

