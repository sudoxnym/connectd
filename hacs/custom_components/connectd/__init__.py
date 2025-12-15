"""connectd integration for home assistant."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

DOMAIN = "connectd"
PLATFORMS = [Platform.SENSOR]
SCAN_INTERVAL = timedelta(minutes=1)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """set up connectd from a config entry."""
    host = entry.data["host"]
    port = entry.data["port"]

    coordinator = ConnectdDataUpdateCoordinator(hass, host, port)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class ConnectdDataUpdateCoordinator(DataUpdateCoordinator):
    """class to manage fetching connectd data."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """initialize."""
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )

    async def _async_update_data(self):
        """fetch data from connectd api."""
        try:
            async with asyncio.timeout(10):
                async with aiohttp.ClientSession() as session:
                    # get stats
                    async with session.get(f"{self.base_url}/api/stats") as resp:
                        if resp.status != 200:
                            raise UpdateFailed(f"error fetching stats: {resp.status}")
                        stats = await resp.json()

                    # get state
                    async with session.get(f"{self.base_url}/api/state") as resp:
                        if resp.status != 200:
                            raise UpdateFailed(f"error fetching state: {resp.status}")
                        state = await resp.json()

                    # get priority matches (optional)
                    priority_matches = {}
                    try:
                        async with session.get(f"{self.base_url}/api/priority_matches") as resp:
                            if resp.status == 200:
                                priority_matches = await resp.json()
                    except Exception:
                        pass

                    # get top humans (optional)
                    top_humans = {}
                    try:
                        async with session.get(f"{self.base_url}/api/top_humans") as resp:
                            if resp.status == 200:
                                top_humans = await resp.json()
                    except Exception:
                        pass

                    # get user info (optional)
                    user = {}
                    try:
                        async with session.get(f"{self.base_url}/api/user") as resp:
                            if resp.status == 200:
                                user = await resp.json()
                    except Exception:
                        pass

                    return {
                        "stats": stats,
                        "state": state,
                        "priority_matches": priority_matches,
                        "top_humans": top_humans,
                        "user": user,
                    }

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"error communicating with connectd: {err}")
        except Exception as err:
            raise UpdateFailed(f"unexpected error: {err}")
