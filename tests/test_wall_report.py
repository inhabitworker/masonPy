"""Shared specimen measurements agree across the browser session and test battery."""

import unittest

from masonpy import Stone, Wall
from masonpy.analysis import wall_report
from masonpy.app.workbench import WorkbenchSession
from masonpy.diagnostics import BatteryCase, run_case


class WallReportTests(unittest.TestCase):
    def test_battery_and_session_use_identical_metrics_colours_and_english_summary(
        self,
    ):
        parameters = dict(
            min_stone_width=3,
            max_stone_width=10,
            min_stone_height=3,
            max_stone_height=7,
        )
        case = BatteryCase(
            "reported", 104, 60, "Reported permissive failure", parameters
        )
        row = run_case(case, 4)
        session = WorkbenchSession(
            width=104,
            height=60,
            generator_id="ashlar",
            generator_parameters={**parameters, "seed": 4},
        )
        session.generate_all()
        report = session.wall_report()
        for key, value in report.items():
            self.assertEqual(row[key], value, key)
        self.assertEqual(row["wall"], session.wall.to_dict())
        self.assertIn("Completed", report["summary"])
        self.assertIn("No size, occupancy or joint-limit violations", report["summary"])
        report["sneck_ids"].clear()
        self.assertEqual(
            session.wall_report()["sneck_count"],
            len(session.wall_report()["sneck_ids"]),
        )

    def test_classification_uses_dimensions_and_distinguishes_deliberate_stock(self):
        wall = Wall(10, 4)
        for stone in (
            Stone(0, 0, 0, 5, 4),
            Stone(1, 5, 0, 2, 2),
            Stone(2, 7, 0, 3, 2, traits={"sneck_deliberate": True}),
        ):
            wall.add_stone(stone)
        report = wall_report(
            wall,
            "ashlar",
            dict(
                min_stone_width=3,
                min_stone_height=3,
                max_stone_width=6,
                max_stone_height=5,
            ),
        )
        self.assertEqual(report["sneck_ids"], [1, 2])
        self.assertEqual(report["deliberate_sneck_ids"], [2])
        self.assertEqual(report["sneck_count"], 2)
        self.assertEqual(report["both_small_snecks"], 1)
        self.assertAlmostEqual(report["sneck_area_share"], 10 / 30)
        self.assertIn("Partial wall", report["summary"])
        self.assertFalse(report["invariant_errors"])

    def test_complete_claims_and_true_layout_defects_are_reported(self):
        wall = Wall(8, 4)
        wall.add_stone(Stone(0, 0, 0, 8, 1))
        report = wall_report(
            wall,
            "ashlar",
            dict(
                min_stone_width=3,
                min_stone_height=2,
                max_stone_width=5,
                max_stone_height=4,
                allow_snecks=0,
            ),
            complete=True,
        )
        self.assertFalse(report["complete"])
        self.assertEqual(len(report["invariant_errors"]), 3)
        self.assertIn("Layout checks:", report["summary"])

    def test_brick_selection_strings_and_unavailable_imported_evidence_are_safe(self):
        session = WorkbenchSession(width=12, height=4)
        session.generate_all()
        report = session.wall_report()
        self.assertEqual(report["fill"], 1)
        self.assertFalse(report["invariant_errors"])
        self.assertEqual(report["sneck_count"], 0)
        self.assertIn("No snecks", report["summary"])
