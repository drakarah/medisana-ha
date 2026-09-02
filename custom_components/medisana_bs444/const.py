"""Constants for the Medisana BS444 integration."""
from __future__ import annotations

DOMAIN = "medisana_bs444"

# GATT service/characteristic UUIDs, reverse engineered by
# https://github.com/keptenkurk/BS440 and used by the ESPHome
# https://github.com/bwynants/weegschaal component.
SERVICE_UUID = "000078b2-0000-1000-8000-00805f9b34fb"
CHAR_PERSON_UUID = "00008a82-0000-1000-8000-00805f9b34fb"
CHAR_WEIGHT_UUID = "00008a21-0000-1000-8000-00805f9b34fb"
CHAR_BODY_UUID = "00008a22-0000-1000-8000-00805f9b34fb"
CHAR_COMMAND_UUID = "00008a81-0000-1000-8000-00805f9b34fb"

# Maximum number of user "slots" the scale supports.
NUM_USERS = 8

# Some scales (BS410, BS444, ...) count time from 1/1/2010 instead of the
# unix epoch. This is the offset (in seconds) between the two.
TIME_OFFSET = 1262304000

LB_TO_KG = 0.45359237

CONF_USE_TIME_OFFSET = "use_time_offset"
DEFAULT_USE_TIME_OFFSET = True

# How long we wait for the scale to send all of its data and disconnect
# after we successfully connect, before giving up and disconnecting
# ourselves.
CONNECT_TIMEOUT = 10
DATA_TIMEOUT = 20
