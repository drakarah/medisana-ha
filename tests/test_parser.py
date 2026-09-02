"""Unit tests for the Medisana BS444 protocol parser.

These tests do not require Home Assistant or bleak to be installed; they
only exercise the pure-python decoding logic in
``custom_components/medisana_bs444/parser.py``.

Run with: python -m unittest discover -s tests
"""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPONENT_DIR = REPO_ROOT / "custom_components" / "medisana_bs444"

# Register a stub "medisana_bs444" package pointing at the real component
# directory, without executing its __init__.py (which imports Home
# Assistant). This lets us import "medisana_bs444.parser" and
# "medisana_bs444.const" directly for testing, without requiring Home
# Assistant or bleak to be installed.
if "medisana_bs444" not in sys.modules:
    _pkg = types.ModuleType("medisana_bs444")
    _pkg.__path__ = [str(COMPONENT_DIR)]
    sys.modules["medisana_bs444"] = _pkg

_parser = importlib.import_module("medisana_bs444.parser")

BodyData = _parser.BodyData
PersonData = _parser.PersonData
ScaleSession = _parser.ScaleSession
WeightData = _parser.WeightData
sanitize_timestamp = _parser.sanitize_timestamp
timestamp_to_bytes = _parser.timestamp_to_bytes


def _bytes_from_hex(hex_string: str) -> bytes:
    return bytes.fromhex(hex_string)


class TestSanitizeTimestamp(unittest.TestCase):
    def test_no_offset(self) -> None:
        self.assertEqual(sanitize_timestamp(1000, False), 1000)

    def test_with_offset(self) -> None:
        self.assertEqual(sanitize_timestamp(1000, True), 1000 + 1262304000)

    def test_max_timestamp_returns_zero(self) -> None:
        self.assertEqual(sanitize_timestamp(2**31 - 1, True), 0)
        self.assertEqual(sanitize_timestamp(2**31 - 1, False), 0)


class TestTimestampToBytes(unittest.TestCase):
    def test_round_trip(self) -> None:
        value = 1700000000
        data = timestamp_to_bytes(value)
        self.assertEqual(len(data), 4)
        self.assertEqual(int.from_bytes(data, "little"), value)


class TestPersonDecode(unittest.TestCase):
    def test_decode_from_docstring_example(self) -> None:
        # handle=0x25, value=0x845302800134b6e0000000000000000000000000
        values = _bytes_from_hex("845302800134b6e0000000000000000000000000")
        person = PersonData.decode(values)
        self.assertTrue(person.valid)
        self.assertEqual(person.person, 2)
        self.assertTrue(person.male)  # gender byte is 1 -> male
        self.assertEqual(person.age, 0x34)
        self.assertAlmostEqual(person.size, 0xB6 / 100.0)
        self.assertFalse(person.high_activity)

    def test_invalid_marker_byte(self) -> None:
        values = bytes([0x00] + [0] * 20)
        person = PersonData.decode(values)
        self.assertFalse(person.valid)


class TestWeightDecode(unittest.TestCase):
    def test_decode_kg(self) -> None:
        # weight = 75.30 kg -> raw = 7530 = 0x1D6A -> low=0x6A high=0x1D
        values = bytearray(20)
        values[0] = 0x1D
        values[1] = 0x6A
        values[2] = 0x1D
        timestamp = 100
        values[5:9] = timestamp.to_bytes(4, "little")
        values[13] = 4
        weight = WeightData.decode(bytes(values), use_time_offset=False)
        self.assertTrue(weight.valid)
        self.assertAlmostEqual(weight.weight, 75.30)
        self.assertEqual(weight.timestamp, timestamp)
        self.assertEqual(weight.person, 4)

    def test_decode_lb_converts_to_kg(self) -> None:
        values = bytearray(20)
        values[0] = 0x3D
        raw = 10000  # 100.00 lb
        values[1] = raw & 0xFF
        values[2] = (raw >> 8) & 0xFF
        values[13] = 1
        weight = WeightData.decode(bytes(values), use_time_offset=False)
        self.assertTrue(weight.valid)
        self.assertAlmostEqual(weight.weight, 100.0 * 0.45359237)

    def test_invalid_marker_byte(self) -> None:
        values = bytearray(20)
        values[0] = 0xFF
        weight = WeightData.decode(bytes(values), use_time_offset=False)
        self.assertFalse(weight.valid)

    def test_time_offset_applied(self) -> None:
        values = bytearray(20)
        values[0] = 0x1D
        values[5:9] = (100).to_bytes(4, "little")
        weight = WeightData.decode(bytes(values), use_time_offset=True)
        self.assertEqual(weight.timestamp, 100 + 1262304000)


class TestBodyDecode(unittest.TestCase):
    def test_decode(self) -> None:
        values = bytearray(20)
        values[0] = 0x6F
        timestamp = 500
        values[1:5] = timestamp.to_bytes(4, "little")
        values[5] = 2  # person
        kcal = 1800
        values[6] = kcal & 0xFF
        values[7] = (kcal >> 8) & 0xFF
        fat = 235  # 23.5%
        values[8] = fat & 0xFF
        values[9] = (fat >> 8) & 0xFF
        tbw = 550
        values[10] = tbw & 0xFF
        values[11] = (tbw >> 8) & 0xFF
        muscle = 400
        values[12] = muscle & 0xFF
        values[13] = (muscle >> 8) & 0xFF
        bone = 32
        values[14] = bone & 0xFF
        values[15] = (bone >> 8) & 0xFF

        body = BodyData.decode(bytes(values), use_time_offset=False)
        self.assertTrue(body.valid)
        self.assertEqual(body.timestamp, timestamp)
        self.assertEqual(body.person, 2)
        self.assertEqual(body.kcal, kcal)
        self.assertAlmostEqual(body.fat, 23.5)
        self.assertAlmostEqual(body.tbw, 55.0)
        self.assertAlmostEqual(body.muscle, 40.0)
        self.assertAlmostEqual(body.bone, 3.2)

    def test_invalid_marker_byte(self) -> None:
        values = bytearray(20)
        values[0] = 0x00
        body = BodyData.decode(bytes(values), use_time_offset=False)
        self.assertFalse(body.valid)


class TestScaleSession(unittest.TestCase):
    def test_combines_person_weight_body_by_id(self) -> None:
        session = ScaleSession()

        person = PersonData(valid=True, person=1, male=True, age=30, size=1.80, high_activity=False)
        weight = WeightData(valid=True, timestamp=100, person=1, weight=80.0)
        body = BodyData(
            valid=True, timestamp=100, person=1, kcal=2000, fat=20.0, tbw=55.0, muscle=40.0, bone=3.5
        )

        session.add_person(person)
        session.add_weight(weight)
        session.add_body(body)

        measurements = session.measurements()
        self.assertIn(1, measurements)
        measurement = measurements[1]
        self.assertEqual(measurement.weight, 80.0)
        self.assertAlmostEqual(measurement.bmi, 80.0 / (1.80 * 1.80))
        self.assertEqual(measurement.kcal, 2000)
        self.assertTrue(measurement.has_weight)
        self.assertTrue(measurement.has_body)

    def test_ignores_invalid_data(self) -> None:
        session = ScaleSession()
        session.add_person(PersonData(valid=False))
        session.add_weight(WeightData(valid=False))
        session.add_body(BodyData(valid=False))
        self.assertEqual(session.measurements(), {})

    def test_ignores_out_of_range_person(self) -> None:
        session = ScaleSession()
        session.add_person(PersonData(valid=True, person=255))
        self.assertEqual(session.measurements(), {})

    def test_keeps_latest_weight_for_same_person(self) -> None:
        session = ScaleSession()
        person = PersonData(valid=True, person=1)
        session.add_person(person)
        session.add_weight(WeightData(valid=True, timestamp=100, person=1, weight=79.0))
        session.add_weight(WeightData(valid=True, timestamp=200, person=1, weight=80.0))
        session.add_weight(WeightData(valid=True, timestamp=150, person=1, weight=79.5))
        measurements = session.measurements()
        self.assertEqual(measurements[1].weight, 80.0)

    def test_rejects_future_timestamp(self) -> None:
        session = ScaleSession()
        session.add_weight(WeightData(valid=True, timestamp=1000, person=1, weight=79.0), now=500)
        self.assertEqual(session.weights, {})


if __name__ == "__main__":
    unittest.main()
