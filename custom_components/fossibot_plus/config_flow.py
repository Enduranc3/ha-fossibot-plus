"""Config flow for FOSSiBOT — single step: email + password only."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import FossibotApiClient, FossibotAuthError, FossibotConnectionError
from .const import (
    CONF_ALLOWED_PREFIX, CONF_EMAIL, CONF_HOST, CONF_MODE, CONF_PASSWORD,
    CONF_PORT, CONF_SERIAL, DOMAIN, LOCAL_TCP_PORT, MODE_CLOUD, MODE_LOCAL,
)

_LOGGER = logging.getLogger(__name__)

MODE_SCHEMA = vol.Schema(
    {vol.Required(CONF_MODE, default=MODE_CLOUD): vol.In({MODE_CLOUD, MODE_LOCAL})}
)

CLOUD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL): str,
        vol.Required(CONF_HOST, default="0.0.0.0"): str,
        vol.Required(CONF_PORT, default=LOCAL_TCP_PORT): vol.All(int, vol.Range(min=1, max=65535)),
        vol.Optional(CONF_ALLOWED_PREFIX, default=""): str,
    }
)


class FossibotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure either the cloud or local AP transport.

    Model detection is automatic — derived from each device's serial number
    prefix (F180... → F1800, F300... → F3000) so no user input is needed,
    and accounts with multiple devices of different models work correctly
    without any extra questions.
    """

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            mode = user_input.get(CONF_MODE, MODE_CLOUD)
            self._mode = mode
            return await (self.async_step_local() if mode == MODE_LOCAL else self.async_step_cloud())
        return self.async_show_form(step_id="user", data_schema=MODE_SCHEMA)

    async def async_step_cloud(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = FossibotApiClient(
                session, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
            )
            try:
                await api.async_login()
                await api.async_get_devices()
            except FossibotAuthError as err:
                _LOGGER.debug("FOSSiBOT auth rejected: %s", err)
                errors["base"] = "invalid_auth"
            except FossibotConnectionError as err:
                _LOGGER.debug("FOSSiBOT connection failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating FOSSiBOT credentials")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL],
                    data={**user_input, CONF_MODE: MODE_CLOUD},
                )
        return self.async_show_form(step_id="cloud", data_schema=CLOUD_SCHEMA, errors=errors)

    async def async_step_local(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            serial = user_input[CONF_SERIAL].strip()
            if not serial:
                errors["base"] = "invalid_serial"
            else:
                await self.async_set_unique_id(f"local_{serial.lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"FOSSiBOT {serial}",
                    data={**user_input, CONF_MODE: MODE_LOCAL, CONF_SERIAL: serial},
                )
        return self.async_show_form(step_id="local", data_schema=LOCAL_SCHEMA, errors=errors)
