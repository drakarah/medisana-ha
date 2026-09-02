"""Parsing helpers for the Medisana BS444 (and compatible) BLE protocol.

This is a Python port of the decoding logic found in the ESPHome
``medisana_bs444`` external component (https://github.com/bwynants/weegschaal),
which in turn is based on reverse engineering work done in
https://github.com/keptenkurk/BS440.

Keeping this module free of Home Assistant / bleak imports makes it easy to
unit test in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import time as time_module

from .const import LB_TO_KG, NUM_USERS, TIME_OFFSET

MAX_TIMESTAMP = 2**31 - 1  # max value of a signed 32 bit unix timestamp


def sanitize_timestamp(timestamp: int, use_time_offset: bool) -> int:
    """Apply the scale's time offset (if any) to a raw timestamp.

    Mirrors ``sanitize_timestamp`` in Scale.cpp.
    """
    if timestamp >= MAX_TIMESTAMP:
        return 0

    if use_time_offset:
        if timestamp + TIME_OFFSET < MAX_TIMESTAMP:
            return timestamp + TIME_OFFSET
        return timestamp

    return timestamp


def timestamp_to_bytes(timestamp: int) -> bytes:
    """Convert a unix timestamp to the little-endian 4 byte form the scale expects."""
    return int(timestamp).to_bytes(4, byteorder="little", signed=False)


@dataclass
class PersonData:
    """Decoded "person" characteristic payload."""

    valid: bool = False
    person: int = 255
    male: bool = False
    age: int = 0
    size: float = 0.0  # meters
    high_activity: bool = False

    @staticmethod
    def decode(values: bytes) -> "PersonData":
        """Decode handle 0x25 (Person) payload.

        Byte layout: B x B x B B B x B
        0 validity byte (0x84), 2 person, 4 gender, 5 age, 6 size (cm), 8 activity
        """
        return PersonData(
            valid=values[0] == 0x84,
            person=values[2],
            male=values[4] == 1,
            age=values[5],
            size=values[6] / 100.0,
            high_activity=values[8] == 3,
        )


@dataclass
class WeightData:
    """Decoded "weight" characteristic payload."""

    valid: bool = False
    timestamp: int = 0
    person: int = 255
    weight: float = 0.0  # kg

    @staticmethod
    def decode(values: bytes, use_time_offset: bool) -> "WeightData":
        """Decode handle 0x1b (Weight) payload.

        Byte layout: B H x x I x x x x B
        0 validity byte (0x1d=kg, 0x3d=lb), 1-2 weight, 5-8 timestamp, 13 person
        """
        weight = ((values[2] << 8) | values[1]) / 100.0

        if values[0] == 0x3D:
            valid = True
            weight *= LB_TO_KG
        elif values[0] == 0x1D:
            valid = True
        else:
            valid = False

        timestamp = (values[8] << 24) | (values[7] << 16) | (values[6] << 8) | values[5]

        return WeightData(
            valid=valid,
            timestamp=sanitize_timestamp(timestamp, use_time_offset),
            person=values[13],
            weight=weight,
        )


@dataclass
class BodyData:
    """Decoded "body" characteristic payload."""

    valid: bool = False
    timestamp: int = 0
    person: int = 255
    kcal: int = 0
    fat: float = 0.0
    tbw: float = 0.0
    muscle: float = 0.0
    bone: float = 0.0

    @staticmethod
    def decode(values: bytes, use_time_offset: bool) -> "BodyData":
        """Decode handle 0x1e (Body) payload.

        Byte layout: B I B B H H H H H
        0 validity byte (0x6f), 1-4 timestamp, 5 person, 6-7 kcal,
        8-9 fat, 10-11 tbw, 12-13 muscle, 14-15 bone (all lower 12 bits)
        """
        timestamp = (values[4] << 24) | (values[3] << 16) | (values[2] << 8) | values[1]

        return BodyData(
            valid=values[0] == 0x6F,
            timestamp=sanitize_timestamp(timestamp, use_time_offset),
            person=values[5],
            kcal=(values[7] << 8) | values[6],
            fat=(0x0FFF & ((values[9] << 8) | values[8])) / 10.0,
            tbw=(0x0FFF & ((values[11] << 8) | values[10])) / 10.0,
            muscle=(0x0FFF & ((values[13] << 8) | values[12])) / 10.0,
            bone=(0x0FFF & ((values[15] << 8) | values[14])) / 10.0,
        )


@dataclass
class UserMeasurement:
    """Aggregated measurement data for a single user/person slot."""

    user_id: int  # 1..NUM_USERS

    age: int = 0
    size: float = 0.0  # meters
    is_male: bool = False
    high_activity: bool = False

    weight: float | None = None
    bmi: float | None = None

    kcal: int | None = None
    fat: float | None = None
    tbw: float | None = None
    muscle: float | None = None
    bone: float | None = None

    timestamp: int = 0

    @property
    def has_weight(self) -> bool:
        return self.weight is not None

    @property
    def has_body(self) -> bool:
        return self.kcal is not None


@dataclass
class ScaleSession:
    """Collects the notifications received during a single BLE session.

    A "session" corresponds to a single connection to the scale, during
    which it replays its history for whichever users stepped on it. This
    mirrors the aggregation logic in ``MedisanaBS444::gattc_event_handler``.
    """

    persons: dict[int, PersonData] = field(default_factory=dict)
    weights: dict[int, WeightData] = field(default_factory=dict)
    bodies: dict[int, BodyData] = field(default_factory=dict)

    def add_person(self, data: PersonData) -> None:
        if not data.valid:
            return
        self.persons[data.person] = data

    def add_weight(self, data: WeightData, now: int | None = None) -> None:
        if not data.valid:
            return
        if now is not None and data.timestamp > now:
            return
        existing = self.weights.get(data.person)
        if existing is None or data.timestamp >= existing.timestamp:
            self.weights[data.person] = data

    def add_body(self, data: BodyData, now: int | None = None) -> None:
        if not data.valid:
            return
        if now is not None and data.timestamp > now:
            return
        existing = self.bodies.get(data.person)
        if existing is None or data.timestamp >= existing.timestamp:
            self.bodies[data.person] = data

    def measurements(self) -> dict[int, UserMeasurement]:
        """Combine the collected person/weight/body data per user."""
        result: dict[int, UserMeasurement] = {}
        for person_id, person in self.persons.items():
            if not 1 <= person_id <= NUM_USERS:
                continue

            measurement = UserMeasurement(
                user_id=person_id,
                age=person.age,
                size=person.size,
                is_male=person.male,
                high_activity=person.high_activity,
            )

            weight = self.weights.get(person_id)
            if weight is not None:
                measurement.weight = weight.weight
                measurement.timestamp = weight.timestamp
                if person.size:
                    measurement.bmi = weight.weight / (person.size * person.size)

            body = self.bodies.get(person_id)
            if body is not None:
                measurement.kcal = body.kcal
                measurement.fat = body.fat
                measurement.tbw = body.tbw
                measurement.muscle = body.muscle
                measurement.bone = body.bone
                if not measurement.timestamp:
                    measurement.timestamp = body.timestamp

            result[person_id] = measurement

        return result


def now() -> int:
    """Return the current unix timestamp (seconds)."""
    return int(time_module.time())
