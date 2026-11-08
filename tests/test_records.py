"""Exact specimens, atomic imports and session history across downstream stages."""

from copy import deepcopy
import io
import json
import unittest

from masonpy.app.server import MasonPyRequestHandler
from masonpy.app.workbench import WorkbenchSession
from masonpy.records import WallRecord


class WallRecordTests(unittest.TestCase):
    def ashlar(self):
        return WorkbenchSession(
            width=24,
            height=12,
            generator_id="ashlar",
            generator_parameters={"seed": 4},
        )

    def saved(self, session):
        return json.loads(session.save_record(revision=session.wall_revision)[0])

    def test_partial_json_round_trip_preserves_geometry_evidence_and_continuation(self):
        original = self.ashlar()
        for _ in range(8):
            original.step()
        data = self.saved(original)
        restored = WorkbenchSession()
        restored.load_record(data)
        self.assertEqual(restored.wall.to_dict(), original.wall.to_dict())
        self.assertEqual(self.saved(restored)["events"], data["events"])
        self.assertEqual(restored.wall_report(), original.wall_report())
        original.generate_all()
        restored.generate_all()
        self.assertEqual(restored.wall.to_dict(), original.wall.to_dict())
        self.assertEqual(restored.complete, original.complete)
        self.assertEqual(self.saved(restored)["events"], self.saved(original)["events"])
        self.assertNotIn("version", data)

    def test_completed_periodic_and_finite_overhanging_stones_restore_exactly(self):
        for session in (self.ashlar(), WorkbenchSession(width=12, height=4)):
            session.generate_all()
            data = self.saved(session)
            record = WallRecord.from_dict(data)
            restored = record.hydrate()
            self.assertEqual(restored["wall"].to_dict(), session.wall.to_dict())
            self.assertTrue(restored["complete"])
            self.assertEqual(restored["wall"].wrap_x, session.wall.wrap_x)
            changed = record.to_dict()
            changed["wall"]["stones"].clear()
            self.assertEqual(record.to_dict()["wall"], data["wall"])

    def test_history_starts_on_attempt_and_updates_without_duplicate_entries(self):
        session = self.ashlar()
        self.assertEqual(session.to_dict()["history"]["entries"], [])
        session.step()
        first = session.active_record
        prefix = session.wall.to_dict()
        expected_next = session.step().stone
        session.undo()
        # Undo deliberately does not rewind RNG; compare continuation after a switch.
        next_record = self.saved(session)
        session.reset(width=12, height=4)
        self.assertIsNone(session.active_record)
        session.generate_all()
        session.generate_all()
        second = session.active_record
        self.assertNotEqual(first, second)
        self.assertEqual(len(session.to_dict()["history"]["entries"]), 2)
        session.select_record(first)
        self.assertEqual(session.wall.to_dict(), prefix)
        reference = self.ashlar()
        reference.load_record(next_record)
        self.assertEqual(session.step().stone, reference.step().stone)
        self.assertEqual(session.wall.stones[-1].id, expected_next.id)
        session.select_record(second)
        self.assertTrue(session.complete)

    def test_failed_zero_and_nonzero_prefixes_are_kept_with_original_failure(self):
        for parameters in (
            {
                "allow_snecks": 0,
                "min_stone_width": 4,
                "max_stone_width": 4,
                "min_stone_height": 2,
                "max_stone_height": 2,
            },
            {"min_sneck_size": 2},
        ):
            session = WorkbenchSession(
                width=5 if "allow_snecks" in parameters else 24,
                height=3 if "allow_snecks" in parameters else 12,
                generator_id="ashlar",
                generator_parameters=parameters,
            )
            session.generate_all()
            self.assertIsNotNone(session.failure)
            data = self.saved(session)
            self.assertIn(
                "stopped", session.to_dict()["history"]["entries"][0]["label"]
            )
            session.reset(width=12, height=4)
            session.load_record(data)
            self.assertEqual(session.failure.to_dict(), data["construction"]["failure"])
            self.assertEqual(session.wall.to_dict(), data["wall"])
            count = len(session.events)
            session.generate_all()
            self.assertEqual(len(session.events), count)
            session.undo()
            self.assertIsNone(session.failure)

    def test_invalid_load_is_atomic_including_history_and_downstream(self):
        session = self.ashlar()
        session.generate_all()
        session.apply_shape(0.1)
        session.build_3d({"depth": 0.5})
        data = self.saved(session)
        bad = []
        for path, value in (
            (("wall", "width"), True),
            (("wall", "height"), 1.5),
            (("wall", "wrap_x"), "false"),
            (("random_state",), [1, 2]),
            (("generation_seconds",), float("nan")),
            (("generator", "parameters"), {"unknown": 4}),
        ):
            item = deepcopy(data)
            target = item
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            bad.append(item)
        overlap = deepcopy(data)
        overlap["wall"]["stones"].append(overlap["wall"]["stones"][0])
        bad.append(overlap)
        mismatch = deepcopy(data)
        mismatch["events"][0]["stone"]["width"] += 1
        bad.append(mismatch)
        before, mesh = session.to_dict(), session.geometry_snapshot()
        for item in bad:
            with self.subTest(item=item.get("generation_seconds")):
                with self.assertRaises((ValueError, TypeError)):
                    session.load_record(item)
                self.assertEqual(session.to_dict(), before)
                self.assertEqual(session.geometry_snapshot(), mesh)
        with self.assertRaisesRegex(ValueError, "Wall changed"):
            session.load_record(data, source_revision=session.wall_revision - 1)
        with self.assertRaisesRegex(ValueError, "Wall changed"):
            session.save_record(revision=session.wall_revision - 1)
        with self.assertRaisesRegex(ValueError, "Unknown wall"):
            session.select_record("missing")
        with self.assertRaises(ValueError):
            session.reset(width=12, height=4, generator_id="missing")
        self.assertEqual(session.to_dict(), before)

    def test_restore_invalidates_both_stages_but_preserves_processing_settings(self):
        session = self.ashlar()
        session.generate_all()
        session.apply_shape(0.1, 0.1, 7, 6)
        session.build_3d({"depth": 0.5})
        first = session.active_record
        settings = (session.shape_result.settings, deepcopy(session.build_settings))
        session.reset(width=12, height=4)
        session.generate_all()
        revision = session.wall_revision
        session.select_record(first)
        self.assertGreater(session.wall_revision, revision)
        self.assertFalse(session.shape_current)
        self.assertFalse(session.build_current)
        self.assertEqual(
            (session.shape_result.settings, session.build_settings), settings
        )
        session.apply_shape(**settings[0].to_dict())
        session.build_3d(settings[1])
        self.assertTrue(session.build_current)

    def test_missing_evidence_and_simple_recipe_do_not_invent_generation(self):
        session = self.ashlar()
        session.generate_all()
        data = self.saved(session)
        for key in ("events", "random_state", "analysis"):
            data.pop(key, None)
        session.load_record(data)
        self.assertEqual(session.wall.to_dict(), data["wall"])
        self.assertFalse(session.events[0].decision["original_evidence"])
        session.load_record(
            dict(generator="ashlar", width=24, height=12, parameters={"seed": 4})
        )
        self.assertEqual(session.wall.stones, ())
        self.assertFalse(session.complete)
        session.generate_all()
        self.assertTrue(session.complete)

    def test_historical_stock_is_reported_instead_of_silently_regenerated(self):
        data = dict(
            generator=dict(id="ashlar", parameters={"max_stone_width": 4}),
            wall=dict(
                width=8, height=2, stones=[dict(id=0, x=0, y=0, width=8, height=2)]
            ),
        )
        session = self.ashlar()
        session.load_record(data)
        self.assertEqual(session.wall.stones[0].width, 8)
        self.assertTrue(session.wall_report()["invariant_errors"])

    def test_http_load_history_save_and_malformed_requests(self):
        session = self.ashlar()
        session.step()
        first = session.active_record

        def request(path, payload):
            handler = object.__new__(MasonPyRequestHandler)
            handler.path, handler.session = path, session
            body = json.dumps(payload).encode()
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = io.BytesIO(body)
            replies = []
            handler._send_json = lambda value, **kwargs: replies.append(
                (value, kwargs.get("status", 200))
            )
            handler._send_bytes = lambda content, mime, **kwargs: replies.append(
                (json.loads(content), 200)
            )
            handler.do_POST()
            return replies[0]

        data, status = request("/api/save", {"revision": session.wall_revision})
        self.assertEqual(status, 200)
        loaded, status = request(
            "/api/load", {"record": data, "source_revision": session.wall_revision}
        )
        self.assertEqual(status, 200)
        self.assertEqual(loaded["wall"]["width"], data["width"])
        self.assertEqual(loaded["wall"]["stones"], [])
        self.assertEqual(len(loaded["history"]["entries"]), 1)
        selected, status = request("/api/history", {"record_id": first})
        self.assertEqual(selected["history"]["active"], first)
        before = session.to_dict()
        for payload in ([], None, {"record": {"wall": []}}):
            error, status = request("/api/load", payload)
            self.assertEqual(status, 400)
            self.assertIn("error", error)
            self.assertEqual(session.to_dict(), before)
