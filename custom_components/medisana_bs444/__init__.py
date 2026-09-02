"""The Medisana BS444 Bluetooth scale integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_USE_TIME_OFFSET, DEFAULT_USE_TIME_OFFSET, DOMAIN
from .coordinator import MedisanaBS444Coordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Medisana BS444 from a config entry."""
    address = entry.data[CONF_ADDRESS]
    use_time_offset = entry.data.get(CONF_USE_TIME_OFFSET, DEFAULT_USE_TIME_OFFSET)

    coordinator = MedisanaBS444Coordinator(hass, address, use_time_offset)
    coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: MedisanaBS444Coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_stop()

    return unload_ok
