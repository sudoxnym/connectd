"""sensor platform for connectd."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, ConnectdDataUpdateCoordinator


def get_device_info(entry_id: str, host: str) -> DeviceInfo:
    """return device info for connectd daemon."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry_id)},
        name="connectd daemon",
        manufacturer="sudoxnym",
        model="connectd",
        sw_version="1.1.0",
        configuration_url=f"http://{host}:8099",
    )

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
    host = entry.data.get("host", "localhost")
    device_info = get_device_info(entry.entry_id, host)

    entities = []
    for sensor_key, name, icon, data_source in SENSORS:
        entities.append(
            ConnectdSensor(coordinator, sensor_key, name, icon, data_source, device_info)
        )

    # add status sensor
    entities.append(ConnectdStatusSensor(coordinator, device_info))

    # add priority matches sensor
    entities.append(ConnectdPriorityMatchesSensor(coordinator, device_info))

    # add top humans sensor
    entities.append(ConnectdTopHumansSensor(coordinator, device_info))

    # add countdown sensors
    entities.append(ConnectdCountdownSensor(coordinator, device_info, "scout", "mdi:radar"))
    entities.append(ConnectdCountdownSensor(coordinator, device_info, "match", "mdi:handshake"))
    entities.append(ConnectdCountdownSensor(coordinator, device_info, "intro", "mdi:email-fast"))

    # add personal score sensor
    entities.append(ConnectdUserScoreSensor(coordinator, device_info))

    # add platform sensors (by_platform dict)
    entities.append(ConnectdPlatformSensor(coordinator, "github", device_info))
    entities.append(ConnectdPlatformSensor(coordinator, "mastodon", device_info))
    entities.append(ConnectdPlatformSensor(coordinator, "reddit", device_info))
    entities.append(ConnectdPlatformSensor(coordinator, "lemmy", device_info))
    entities.append(ConnectdPlatformSensor(coordinator, "discord", device_info))
    entities.append(ConnectdPlatformSensor(coordinator, "lobsters", device_info))

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
        device_info: DeviceInfo,
    ) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self._attr_name = f"connectd {name}"
        self._attr_unique_id = f"connectd_{sensor_key}"
        self._attr_icon = icon
        self._data_source = data_source
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """return the state."""
        if self.coordinator.data:
            data = self.coordinator.data.get(self._data_source, {})
            return data.get(self._sensor_key, 0)
        return None


class ConnectdStatusSensor(CoordinatorEntity, SensorEntity):
    """connectd daemon status sensor."""

    def __init__(self, coordinator: ConnectdDataUpdateCoordinator, device_info: DeviceInfo) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._attr_name = "connectd status"
        self._attr_unique_id = "connectd_status"
        self._attr_icon = "mdi:connection"
        self._attr_device_info = device_info

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
        device_info: DeviceInfo,
    ) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._platform = platform
        self._attr_name = f"connectd {platform} humans"
        self._attr_unique_id = f"connectd_platform_{platform}"
        self._attr_icon = self._get_platform_icon(platform)
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = device_info

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


class ConnectdPriorityMatchesSensor(CoordinatorEntity, SensorEntity):
    """connectd priority matches sensor."""

    def __init__(self, coordinator: ConnectdDataUpdateCoordinator, device_info: DeviceInfo) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._attr_name = "connectd priority matches"
        self._attr_unique_id = "connectd_priority_matches"
        self._attr_icon = "mdi:account-star"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """return count of new priority matches."""
        if self.coordinator.data:
            pm = self.coordinator.data.get("priority_matches", {})
            return pm.get("new_count", 0)
        return 0

    @property
    def extra_state_attributes(self):
        """return top matches as attributes."""
        if self.coordinator.data:
            pm = self.coordinator.data.get("priority_matches", {})
            top = pm.get("top_matches", [])
            attrs = {
                "total_matches": pm.get("count", 0),
                "new_matches": pm.get("new_count", 0),
            }
            for i, m in enumerate(top[:3]):
                attrs[f"match_{i+1}_username"] = m.get("username")
                attrs[f"match_{i+1}_platform"] = m.get("platform")
                attrs[f"match_{i+1}_score"] = m.get("overlap_score")
                attrs[f"match_{i+1}_reasons"] = ", ".join(m.get("reasons", []))
            return attrs
        return {}


class ConnectdTopHumansSensor(CoordinatorEntity, SensorEntity):
    """connectd top humans sensor."""

    def __init__(self, coordinator: ConnectdDataUpdateCoordinator, device_info: DeviceInfo) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._attr_name = "connectd top human"
        self._attr_unique_id = "connectd_top_human"
        self._attr_icon = "mdi:account-check"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """return top human username."""
        if self.coordinator.data:
            th = self.coordinator.data.get("top_humans", {})
            top = th.get("top_humans", [])
            if top:
                return top[0].get("username", "none")
        return "none"

    @property
    def extra_state_attributes(self):
        """return top humans as attributes."""
        if self.coordinator.data:
            th = self.coordinator.data.get("top_humans", {})
            top = th.get("top_humans", [])
            attrs = {"total_high_score": th.get("count", 0)}
            for i, h in enumerate(top[:5]):
                attrs[f"human_{i+1}_username"] = h.get("username")
                attrs[f"human_{i+1}_platform"] = h.get("platform")
                attrs[f"human_{i+1}_score"] = h.get("score")
                attrs[f"human_{i+1}_signals"] = ", ".join(h.get("signals", [])[:3])
                attrs[f"human_{i+1}_contact"] = h.get("contact_method")
            return attrs
        return {}


class ConnectdCountdownSensor(CoordinatorEntity, SensorEntity):
    """connectd countdown timer sensor."""

    def __init__(
        self,
        coordinator: ConnectdDataUpdateCoordinator,
        device_info: DeviceInfo,
        cycle_type: str,
        icon: str,
    ) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._cycle_type = cycle_type
        self._attr_name = f"connectd next {cycle_type}"
        self._attr_unique_id = f"connectd_countdown_{cycle_type}"
        self._attr_icon = icon
        self._attr_device_info = device_info
        self._attr_native_unit_of_measurement = "min"

    @property
    def native_value(self):
        """return minutes until next cycle."""
        if self.coordinator.data:
            state = self.coordinator.data.get("state", {})
            secs = state.get(f"countdown_{self._cycle_type}", 0)
            return int(secs / 60)
        return 0

    @property
    def extra_state_attributes(self):
        """return detailed countdown info."""
        if self.coordinator.data:
            state = self.coordinator.data.get("state", {})
            secs = state.get(f"countdown_{self._cycle_type}", 0)
            return {
                "seconds": secs,
                "hours": round(secs / 3600, 1),
                f"last_{self._cycle_type}": state.get(f"last_{self._cycle_type}"),
            }
        return {}


class ConnectdUserScoreSensor(CoordinatorEntity, SensorEntity):
    """connectd personal score sensor."""

    def __init__(self, coordinator: ConnectdDataUpdateCoordinator, device_info: DeviceInfo) -> None:
        """initialize."""
        super().__init__(coordinator)
        self._attr_name = "connectd my score"
        self._attr_unique_id = "connectd_user_score"
        self._attr_icon = "mdi:star-circle"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = device_info

    @property
    def native_value(self):
        """return user's personal score."""
        if self.coordinator.data:
            user = self.coordinator.data.get("user", {})
            return user.get("score", 0)
        return 0

    @property
    def extra_state_attributes(self):
        """return user profile details."""
        if self.coordinator.data:
            user = self.coordinator.data.get("user", {})
            signals = user.get("signals", [])
            interests = user.get("interests", [])
            return {
                "configured": user.get("configured", False),
                "name": user.get("name"),
                "github": user.get("github"),
                "mastodon": user.get("mastodon"),
                "reddit": user.get("reddit"),
                "lobsters": user.get("lobsters"),
                "matrix": user.get("matrix"),
                "lemmy": user.get("lemmy"),
                "discord": user.get("discord"),
                "bluesky": user.get("bluesky"),
                "location": user.get("location"),
                "bio": user.get("bio"),
                "match_count": user.get("match_count", 0),
                "new_matches": user.get("new_match_count", 0),
                "signals": ", ".join(signals[:5]) if signals else "",
                "interests": ", ".join(interests[:5]) if interests else "",
            }
        return {}
