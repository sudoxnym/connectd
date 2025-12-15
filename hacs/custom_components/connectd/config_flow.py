"""config flow for connectd integration."""
from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN

DEFAULT_PORT = 8099


class ConnectdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """handle a config flow for connectd."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """handle the initial step."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)

            # test connection
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"http://{host}:{port}/api/health"
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            # connection works
                            await self.async_set_unique_id(f"{host}:{port}")
                            self._abort_if_unique_id_configured()

                            return self.async_create_entry(
                                title=f"connectd ({host})",
                                data={
                                    "host": host,
                                    "port": port,
                                },
                            )
                        else:
                            errors["base"] = "cannot_connect"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default="192.168.1.8"): str,
                    vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )
