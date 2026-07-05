"""Minimal regression check against the first row of the supplied workbook."""

import unittest

from dissolution_calculation import ModelInputs, calculate_at_speed


class DefaultCaseTest(unittest.TestCase):
    def test_first_speed_matches_coursework_sheet(self) -> None:
        result = calculate_at_speed(10.0, ModelInputs())
        self.assertAlmostEqual(result.reynolds_number, 231762.4649859945, places=6)
        self.assertAlmostEqual(result.schmidt_number, 535.5535553555357, places=6)
        self.assertAlmostEqual(result.sherwood_number, 3127.609377276049, places=6)
        self.assertAlmostEqual(result.mass_transfer_coefficient_m_s, 0.006880740630007307, places=12)
        self.assertAlmostEqual(result.dissolution_time_s, 1.8703390919422747, places=12)
        self.assertAlmostEqual(result.motor_power_w, 24.09953871644447, places=8)


if __name__ == "__main__":
    unittest.main()
