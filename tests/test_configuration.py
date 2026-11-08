"""Compact recipes reproduce generation without importing generated state."""

from copy import deepcopy
import json
import unittest

from masonpy.app.workbench import WorkbenchSession


class ConfigurationTests(unittest.TestCase):
    def test_export_is_parameters_only_and_load_does_not_generate(self):
        source = WorkbenchSession(
            width=24, height=12, generator_id="ashlar", generator_parameters={"seed": 4}
        )
        source.generate_all()
        source.apply_shape(0.1, 0.3, 12, 4)
        source.build_3d({"depth": 0.4})
        body, filename = source.export_config()
        config = json.loads(body)
        self.assertEqual(filename, "masonpy-config.json")
        self.assertLess(len(body), 1500)
        self.assertEqual(
            set(config),
            {"generator", "width", "height", "parameters", "shape", "build"},
        )
        before = source.wall.to_dict()
        source.load_config(config)
        state = source.to_dict()
        self.assertEqual(state["wall"]["stones"], [])
        self.assertEqual(state["events"], [])
        self.assertIsNone(state["shape"]["result"])
        self.assertFalse(state["build"]["present"])
        self.assertEqual(state["shape"]["defaults"], config["shape"])
        self.assertEqual(state["build"]["defaults"], config["build"])
        self.assertEqual(len(state["history"]["entries"]), 1)
        source.generate_all()
        self.assertEqual(source.wall.to_dict(), before)
        source.apply_shape(**state["shape"]["defaults"])
        source.build_3d({})
        self.assertEqual(source.build_settings, config["build"])

    def test_exporting_unapplied_parameters_never_changes_active_wall(self):
        session = WorkbenchSession(width=12, height=4)
        session.generate_all()
        before = session.to_dict()
        draft = dict(
            generator="ashlar",
            width=104,
            height=60,
            parameters={"seed": 4},
            shape={"distortion": 0.5},
            build={"depth": 0.7},
        )
        config = json.loads(session.export_config(draft)[0])
        self.assertEqual(config["parameters"]["seed"], 4)
        self.assertEqual(config["build"]["depth"], 0.7)
        self.assertEqual(session.to_dict(), before)

    def test_invalid_parameters_are_rejected_before_reset_or_history_changes(self):
        session = WorkbenchSession(width=12, height=4)
        session.generate_all()
        session.apply_shape(0.1)
        session.build_3d({})
        valid = json.loads(session.export_config()[0])
        before = session.to_dict()
        for section, key, value in (
            (None, "width", True),
            (None, "height", 3.5),
            ("parameters", "unknown", 1),
            ("shape", "distortion", 2),
            ("shape", "seed", False),
            ("build", "resolution", 1.5),
            ("build", "mode", "unknown"),
            ("build", "depth", float("nan")),
        ):
            bad = deepcopy(valid)
            (bad[section] if section else bad)[key] = value
            with self.assertRaises((TypeError, ValueError)):
                session.load_config(bad)
            self.assertEqual(session.to_dict(), before)
        with self.assertRaisesRegex(ValueError, "Wall changed"):
            session.load_config(valid, source_revision=session.wall_revision - 1)
        self.assertEqual(session.to_dict(), before)

    def test_small_incompatible_wall_configs_can_reproduce_generation_failures(self):
        session = WorkbenchSession()
        session.load_config(
            dict(generator="ashlar", width=1, height=1, parameters={"allow_snecks": 0})
        )
        self.assertIsNone(session.failure)
        session.generate_all()
        self.assertIsNotNone(session.failure)
        config = json.loads(session.export_config()[0])
        other = WorkbenchSession()
        other.load_config(config)
        other.generate_all()
        self.assertEqual(other.failure.to_dict(), session.failure.to_dict())

    def test_legacy_full_specimen_only_supplies_its_recipe(self):
        session = WorkbenchSession(
            width=24, height=12, generator_id="ashlar", generator_parameters={"seed": 4}
        )
        session.generate_all()
        legacy = json.loads(session.save_record()[0])
        other = WorkbenchSession()
        other.load_config(legacy)
        self.assertEqual(other.wall.stones, ())
        self.assertEqual(other.generator_parameters, session.generator_parameters)
        other.generate_all()
        self.assertEqual(other.wall.to_dict(), session.wall.to_dict())
