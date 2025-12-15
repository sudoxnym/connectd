"""sensor platform for connectd."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, ConnectdDataUpdateCoordinator

SENSORS = [
    # stats sensors
    ("total_humans", "total humans", "mdi:account-group", "stats"),
    ("high_score_humans", "high score humans", "mdi:account-star", "stats"),
    ("total_matches", "total matches", "mdi:handshake", "stats"),
    ("total_intros", "total intros", "mdi:email-outline", "stats"),
    ("sent_intros", "sent intros", "mdi:email-check", "stats"),
    ("active_builders", "active builders", "mdi:hammer-wrench", "stats"),
    ("lost_builders", "lost builders", "mdi:account-question", "stats"),
    ("recovering_builders", "recovering builders", "mdi:account-heart", "stats"),
    ("lost_outreach_sent", "lost outreach sent", "mdi:heart-pulse", "stats"),

    # state sensors
    ("intros_today", "intros today", "mdi:email-fast", "state"),
    ("lost_intros_today", "lost intros today", "mdi:heart-outline", "state"),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """set up connectd sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for sensor_key, name, icon, data_source in SENSORS:
        entities.append(
            ConnectdSensor(coordinator, sensor_key, name, icon, data_source)
        )

    # add status sensor
    entities.append(ConnectdStatusSensor(coordinator))

    # add platform sensors (by_platform dict)
    entities.append(ConnectdPlatformSensor(coordinator, "github"))
    entities.append(ConnectdPlatformSensor(coordinator, "mastodon"))
    entities.append(ConnectdPlatformSensor(coordinator, "reddit"))
    entities.append(ConnectdPlatformSensor(coordinator, "lemmy"))
    entities.append(ConnectdPlatformSensor(coordinator, "discord"))
    entities.append(ConnectdPlatformSensor(coordinator, "lobsters"))

    async_add_entities(entities)


class ConnectdSensor(CoordinatorEntity, SensorEntity):
    """connectd sensor entity."""

    def __init__(
        self,
        coordinator: ConnectdDataUpdateCoordinator,
        sensor_key: str,
        name: str,
        icon: str,
        data_source: str,
    ) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._attr_name = f"connectd {name}"
        self._attr_unique_id = f"connectd_{sensor_key}"
        self._attr_icon = icon
        self._data_source = data_source
        self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        """return the state."""
        if self.coordinator.data:
            data = self.coordinator.data.get(self._data_source, {})
            return data.get(self._sensor_key, 0)
        return None


class ConnectdStatusSensor(CoordinatorEntity, SensorEntity):
    """connectd daemon status sensor."""

    def __init__(self, coordinator: ConnectdDataUpdateCoordinator) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._attr_name = "connectd status"
        self._attr_unique_id = "connectd_status"
        self._attr_icon = "mdi:connection"

    @property
    def native_value(self):
        """return the state."""
        if self.coordinator.data:
            state = self.coordinator.data.get("state", {})
            if state.get("running"):
                return "running" if not state.get("dry_run") else "dry_run"
            return "stopped"
        return "unavailable"

    @property
    def extra_state_attributes(self):
        """return extra attributes."""
        if self.coordinator.data:
            state = self.coordinator.data.get("state", {})
            return {
                "last_scout": state.get("last_scout"),
                "last_match": state.get("last_match"),
                "last_intro": state.get("last_intro"),
                "last_lost": state.get("last_lost"),
                "started_at": state.get("started_at"),
            }
        return {}


class ConnectdPlatformSensor(CoordinatorEntity, SensorEntity):
    """connectd per-platform sensor."""

    def __init__(
        self,
        coordinator: ConnectdDataUpdateCoordinator,
        platform: str,
    ) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._platform = platform
        self._attr_name = f"connectd {platform} humans"
        self._attr_unique_id = f"connectd_platform_{platform}"
        self._attr_icon = self._get_platform_icon(platform)
        self._attr_state_class = SensorStateClass.MEASUREMENT

    def _get_platform_icon(self, platform: str) -> str:
        """get icon for platform."""
        icons = {
            "github": "mdi:github",
            "mastodon": "mdi:mastodon",
            "reddit": "mdi:reddit",
            "lemmy": "mdi:alpha-l-circle",
            "discord": "mdi:discord",
            "lobsters": "mdi:web",
            "bluesky": "mdi:cloud",
            "matrix": "mdi:matrix",
        }
        return icons.get(platform, "mdi:web")

    @property
    def native_value(self):
        """return the state."""
        if self.coordinator.data:
            stats = self.coordinator.data.get("stats", {})
            by_platform = stats.get("by_platform", {})
            return by_platform.get(self._platform, 0)
        return 0
