import unittest

from masonpy.app import GenerationSession


class GenerationSessionTests(unittest.TestCase):
    def test_failure_is_terminal_until_explicit_undo_or_reset(self):
        session = GenerationSession(
            width=5,
            height=2,
            generator_id="ashlar",
            generator_parameters={
                "min_stone_width": 4,
                "max_stone_width": 4,
                "allow_snecks": 0,
                "min_stone_height": 2,
                "max_stone_height": 2,
            },
        )
        session.generate_all()
        failed = session.to_dict()
        self.assertIsNotNone(failed["failure"])
        self.assertFalse(failed["complete"])
        self.assertEqual(len(failed["wall"]["stones"]), 0)
        self.assertFalse(failed["failure"]["retry_possible"])
        session.generate_all()
        self.assertEqual(session.to_dict(), failed)
        session.undo()
        self.assertIsNone(session.failure)
        self.assertEqual(session.wall.stones, ())
        self.assertIsNone(session.step())
        self.assertIsNotNone(session.failure)
        session.reset(width=8, height=4)
        session.generate_all()
        self.assertTrue(session.complete)
        self.assertIsNone(session.failure)

    def test_empty_failure_can_be_cleared_without_placement(self):
        session = GenerationSession(
            width=1,
            height=1,
            generator_id="ashlar",
            generator_parameters={"allow_snecks": 0},
        )
        session.generate_all()
        self.assertIsNotNone(session.failure)
        self.assertIsNone(session.undo())
        self.assertIsNone(session.failure)

    def test_step_and_generate_share_incremental_state(self):
        session = GenerationSession(width=8, height=4)

        first = session.step()
        self.assertIsNotNone(first)
        self.assertEqual(len(session.wall.stones), 1)

        session.generate_all()
        state = session.to_dict()
        self.assertTrue(state["complete"])
        self.assertEqual(len(state["events"]), len(state["wall"]["stones"]))
        self.assertEqual(state["last_stone_id"], state["wall"]["stones"][-1]["id"])

    def test_undo_removes_data_and_next_step_re_evaluates_placement(self):
        session = GenerationSession(width=8, height=4)
        session.step()
        original_second = session.step()

        undone = session.undo()
        self.assertEqual(undone, original_second)
        self.assertEqual(len(session.wall.stones), 1)
        self.assertEqual(len(session.events), 1)
        self.assertFalse(session.complete)

        replacement = session.step()
        self.assertEqual(replacement.stone, original_second.stone)
        self.assertEqual(len(session.wall.stones), 2)

    def test_undo_on_empty_session_is_a_no_op(self):
        session = GenerationSession(width=8, height=4)
        self.assertIsNone(session.undo())
        self.assertEqual(session.wall.stones, ())

    def test_generator_catalog_and_dynamic_parameters_are_serialized(self):
        session = GenerationSession(
            width=12,
            height=4,
            generator_id="english_bond",
            generator_parameters={
                "stretcher_width": 6,
                "header_width": 2,
                "brick_height": 2,
            },
        )

        state = session.to_dict()
        self.assertEqual(state["generator"]["id"], "english_bond")
        self.assertEqual(state["generator"]["parameters"]["stretcher_width"], 6)
        self.assertEqual(
            [(item["category"], item["id"]) for item in state["generators"]],
            [
                ("Brick", "running_bond"),
                ("Brick", "stack_bond"),
                ("Brick", "english_bond"),
                ("Brick", "flemish_bond"),
                ("Stone", "ashlar"),
            ],
        )

        first = session.step()
        self.assertEqual(first.stone.traits["face"], "stretcher")

    def test_ashlar_undo_re_evaluates_with_continuing_random_state(self):
        session = GenerationSession(
            width=24,
            height=12,
            generator_id="ashlar",
            generator_parameters={
                "min_stone_width": 3,
                "max_stone_width": 8,
                "min_stone_height": 2,
                "max_stone_height": 5,
                "seed": 1,
            },
        )
        session.step()
        original = session.step()
        session.undo()
        replacement = session.step()

        self.assertEqual(replacement.stone.id, original.stone.id)
        self.assertNotEqual(
            (replacement.stone.width, replacement.stone.height),
            (original.stone.width, original.stone.height),
        )

    def test_unknown_generator_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown generator"):
            GenerationSession(generator_id="not_a_generator", generator_parameters={})

    def test_bonding_rebuilds_context_after_undo_and_retains_hard_limit(self):
        from masonpy import vertical_seams

        session = GenerationSession(
            width=24,
            height=12,
            generator_id="ashlar",
            generator_parameters={
                "enforce_stack": 1,
                "snecking_factor": 0.01,
                "seed": 1,
            },
        )
        for _ in range(8):
            self.assertIsNotNone(session.step())
        session.undo()
        self.assertEqual(len(session.wall.stones), 7)
        self.assertIsNotNone(session.step())
        self.assertEqual(len(session.wall.stones), 8)
        self.assertTrue(all(s.stack_count <= 2 for s in vertical_seams(session.wall)))
        self.assertEqual(session.events[-1].stone, session.wall.stones[-1])

    def test_session_serializes_whole_overhanging_stone(self):
        session = GenerationSession(width=12, height=4)
        session.generate_all()
        state = session.to_dict()

        overhanging_stones = [
            stone
            for stone in state["wall"]["stones"]
            if stone["traits"]["overhangs_wall"]
        ]
        self.assertEqual(
            [(stone["x"], stone["width"]) for stone in overhanging_stones], [(-2, 4)]
        )


if __name__ == "__main__":
    unittest.main()
