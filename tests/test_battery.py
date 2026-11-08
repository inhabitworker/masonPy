"""The diagnostic battery reports imperfect generation without hiding defects."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from masonpy.diagnostics import (
    BatteryCase,
    battery_cases,
    compare_runs,
    main,
    run_case,
    summarize,
    write_reports,
)
from masonpy.models import Stone
from masonpy.generators.ashlar import AshlarGenerator
from masonpy.app.workbench import WorkbenchSession


class BatteryTests(unittest.TestCase):
    def cases(self):
        parameters = dict(
            min_stone_width=4, max_stone_width=4, min_stone_height=2, max_stone_height=2
        )
        return (
            BatteryCase("closer", 5, 3, "Small closing stock", parameters),
            BatteryCase(
                "impossible",
                5,
                2,
                "No closure",
                {**parameters, "allow_snecks": 0},
                "incompatible",
            ),
        )

    def test_case_families_include_the_reported_seed_and_control_extremes(self):
        cases = {c.id: c for c in battery_cases("stress")}
        self.assertEqual((cases["reported"].width, cases["reported"].height), (104, 60))
        self.assertIn("many_snecks", cases)
        self.assertIn("refined_3x", cases)
        self.assertIn("impossible_height", cases)

    def test_reports_capture_failures_without_counting_them_as_invariant_errors(self):
        cases = self.cases()
        rows = [run_case(case, 4) for case in cases]
        self.assertTrue(rows[0]["complete"])
        self.assertFalse(rows[1]["complete"])
        self.assertFalse(rows[1]["invariant_errors"])
        self.assertEqual(rows[1]["failure"]["kind"], "incompatible_configuration")
        summaries = summarize(rows)
        self.assertIsNone(summaries[1]["complete_sneck_area_share"])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            write_reports(output, cases, rows)
            payload = json.loads((output / "report.json").read_text())
            self.assertEqual(payload["runs"][1]["failure"], rows[1]["failure"])
            self.assertTrue((output / "summary.csv").is_file())
            self.assertIn("impossible-4.svg", (output / "report.html").read_text())
            self.assertIn("closer-4.config.json", (output / "report.html").read_text())
            for row in rows:
                specimen = json.loads(
                    (output / f"{row['case']}-4.config.json").read_text()
                )
                session = WorkbenchSession()
                session.load_config(specimen)
                self.assertEqual(session.wall.stones, ())
                self.assertNotIn("wall", specimen)
                session.generate_all()
                self.assertEqual(session.wall.to_dict(), row["wall"])
                self.assertEqual(session.wall_report()["summary"], row["summary"])
                self.assertEqual(session.generator_parameters["seed"], 4)
            comparison = compare_runs(rows, payload)
            self.assertEqual(comparison["matched_runs"], 2)
            self.assertEqual(comparison["lost_completions"], 0)
            changed = [{**rows[0], "width": 100}]
            self.assertEqual(compare_runs(changed, payload)["matched_runs"], 0)

    def test_cli_allows_legitimate_failure_but_returns_nonzero_for_defects(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("masonpy.diagnostics.battery_cases", return_value=self.cases()),
        ):
            self.assertEqual(main(["--seeds", "1", "--output", directory]), 0)

            def broken_generate(generator, wall):
                wall.wrap_x = True
                wall.add_stone(
                    Stone(0, 0, 0, 5, 1)
                )  # Above the configured maximum width.
                return iter(())

            with patch.object(
                AshlarGenerator, "generate_incrementally", broken_generate
            ):
                self.assertEqual(main(["--seeds", "1", "--output", directory]), 1)
            rows = json.loads(Path(directory, "report.json").read_text())["runs"]
            self.assertTrue(all(r["invariant_errors"] for r in rows))
