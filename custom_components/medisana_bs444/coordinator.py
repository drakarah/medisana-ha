"""Data update coordinator for the Medisana BS444 scale.

The scale only accepts a single active GATT connection at a time. Instead of
requiring a single dedicated ESPHome ``ble_client`` device (as the ESPHome
``medisana_bs444`` external component does), this coordinator asks Home
Assistant's ``bluetooth`` integration for a connectable ``BLEDevice``.

Home Assistant's bluetooth manager automatically picks the best available
connectable source (a local adapter or any ``bluetooth_proxy`` capable
ESPHome device, e.g. multiple Bluetooth proxies) based on signal strength,
and transparently fails over to another proxy if the one currently in use
goes away. This gives us the failover behaviour requested: any proxy that
hears the scale's advertisement can be used to service the connection.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CHAR_BODY_UUID,
    CHAR_COMMAND_UUID,
    CHAR_PERSON_UUID,
    CHAR_WEIGHT_UUID,
    CONNECT_TIMEOUT,
    DATA_TIMEOUT,
    DOMAIN,
)
from .parser import (
    BodyData,
    PersonData,
    ScaleSession,
    UserMeasurement,
    WeightData,
    now,
    timestamp_to_bytes,
)

_LOGGER = logging.getLogger(__name__)

# The indication-enable descriptor value, as used by the ESPHome component.
_ENABLE_INDICATIONS = b"\x02\x00"


class MedisanaBS444Coordinator(DataUpdateCoordinator[dict[int, UserMeasurement]]):
    """Coordinates connecting to the scale whenever it is seen advertising."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        use_time_offset: bool,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # event driven, see async_start()
        )
        self.address = address
        self.use_time_offset = use_time_offset
        self.data = {}

        self._connect_lock = asyncio.Lock()
        self._unregister_callback: callback | None = None

    @callback
    def async_start(self) -> None:
        """Start listening for advertisements from the scale."""
        self._unregister_callback = bluetooth.async_register_callback(
            self.hass,
            self._async_advertisement_callback,
            bluetooth.BluetoothCallbackMatcher(address=self.address, connectable=True),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

    @callback
    def async_stop(self) -> None:
        """Stop listening for advertisements."""
        if self._unregister_callback is not None:
            self._unregister_callback()
            self._unregister_callback = None

    @callback
    def _async_advertisement_callback(
        self,
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle a new advertisement seen by any (proxied) Bluetooth adapter."""
        if self._connect_lock.locked():
            # Already connecting/connected to the scale, nothing to do.
            return
        self.hass.async_create_task(self._async_connect_and_read())

    async def _async_connect_and_read(self) -> None:
        """Connect to the scale, read its data and update listeners."""
        async with self._connect_lock:
            ble_device: BLEDevice | None = bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if ble_device is None:
                _LOGGER.debug(
                    "No connectable Bluetooth adapter/proxy currently available for %s",
                    self.address,
                )
                return

            try:
                measurements = await self._async_do_session(ble_device)
            except (BleakError, asyncio.TimeoutError) as err:
                _LOGGER.debug("Error talking to scale %s: %s", self.address, err)
                return

        if measurements:
            merged = dict(self.data or {})
            merged.update(measurements)
            self.async_set_updated_data(merged)

    async def _async_do_session(
        self, ble_device: BLEDevice
    ) -> dict[int, UserMeasurement]:
        """Open a connection, register for notifications and gather data."""
        session = ScaleSession()
        disconnected_event = asyncio.Event()

        @callback
        def _disconnected_callback(_client) -> None:
            disconnected_event.set()

        client = await establish_connection(
            BleakClientWithServiceCache,
            ble_device,
            self.address,
            disconnected_callback=_disconnected_callback,
            timeout=CONNECT_TIMEOUT,
        )

        try:

            def _person_handler(_handle, data: bytearray) -> None:
                session.add_person(PersonData.decode(bytes(data)))

            def _weight_handler(_handle, data: bytearray) -> None:
                session.add_weight(WeightData.decode(bytes(data), self.use_time_offset), now())

            def _body_handler(_handle, data: bytearray) -> None:
                session.add_body(BodyData.decode(bytes(data), self.use_time_offset), now())

            await client.start_notify(CHAR_PERSON_UUID, _person_handler)
            await client.start_notify(CHAR_WEIGHT_UUID, _weight_handler)
            await client.start_notify(CHAR_BODY_UUID, _body_handler)

            # Tell the scale to send its (buffered) measurements, passing our
            # current time so it can timestamp them correctly.
            offset_now = now()
            await client.write_gatt_char(
                CHAR_COMMAND_UUID,
                b"\x02" + timestamp_to_bytes(offset_now),
                response=True,
            )

            try:
                await asyncio.wait_for(disconnected_event.wait(), timeout=DATA_TIMEOUT)
            except asyncio.TimeoutError:
                _LOGGER.debug(
                    "Timed out waiting for scale %s to finish sending data", self.address
                )
        finally:
            if client.is_connected:
                await client.disconnect()

        return session.measurements()
