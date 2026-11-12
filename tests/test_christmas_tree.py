from __future__ import annotations

import contextlib
import io
import math
from pathlib import Path
import re
import subprocess
import sys
import unittest

import christmas_tree as tree


class RecordingCanvas(tree.Canvas):
    """Keep draw requests so overlapping baubles can still be counted."""

    def __init__(self, width: int = 100, height: int = 40) -> None:
        super().__init__(width, height)
        self.draws = []

    def put(self, x, y, char, style, depth=10.0):
        self.draws.append((x, y, char, style, depth))
        super().put(x, y, char, style, depth)


class CanvasTests(unittest.TestCase):
    def test_nearer_cells_occlude_farther_cells_in_either_draw_order(self):
        for layers in (
            [(0.1, ".", "pine1"), (0.8, "O", "red")],
            [(0.8, "O", "red"), (0.1, ".", "pine1")],
        ):
            with self.subTest(layers=layers):
                canvas = tree.Canvas(3, 3)
                for depth, char, style in layers:
                    canvas.put(1, 1, char, style, depth)
                self.assertEqual(canvas.rows[1][1].char, "O")
                self.assertEqual(canvas.rows[1][1].style, "red")

    def test_outside_draws_are_clipped(self):
        canvas = tree.Canvas(3, 2)
        for x, y in [(-1, 0), (3, 0), (0, -1), (0, 2), (1000, 1000)]:
            canvas.put(x, y, "X", "white")
        self.assertEqual(canvas.plain(), "   \n   ")

    def test_color_output_preserves_the_same_characters(self):
        canvas = tree.Canvas(5, 1)
        canvas.put(1, 0, "~", "gold")
        canvas.put(3, 0, "O", "red")
        ansi = canvas.ansi_row(0)
        self.assertIn("\x1b[", ansi)
        self.assertEqual(re.sub(r"\x1b\[[0-9;]*m", "", ansi), canvas.plain())
        self.assertEqual(canvas.ansi_row(0, color=False), canvas.plain())

    def test_ornament_fill_does_not_bleed_onto_neighboring_foliage(self):
        canvas = tree.Canvas(7, 1)
        for x, (char, style) in enumerate([
            ("a", "pine5"), ("b", "red_gloss"), ("c", "red"),
            ("d", "pine5"), ("e", "blue_shade"), ("f", "pine5"), ("g", "sky"),
        ]):
            canvas.put(x, 0, char, style)
        backgrounds, background = {}, None
        for part in re.split(r"(\x1b\[[0-9;]*m)", canvas.ansi_row(0)):
            if part.startswith("\x1b["):
                codes = [int(value) for value in part[2:-1].split(";")]
                index = 0
                while index < len(codes):
                    if codes[index] == 0:
                        background = None
                    if codes[index] in (38, 48) and codes[index + 1:index + 2] == [2]:
                        if codes[index] == 48:
                            background = tuple(codes[index + 2:index + 5])
                        index += 4
                    index += 1
            else:
                backgrounds.update((char, background) for char in part)
        for char in "adfg":
            self.assertEqual(backgrounds[char], tree.BACKGROUND)
        for char in "bce":
            self.assertNotEqual(backgrounds[char], tree.BACKGROUND)
        self.assertIsNone(background)
        self.assertEqual(canvas.ansi_row(0, color=False), "abcdefg")


class AnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene = tree.Scene(100, 40, seed=25)

    def rendered_layer(self, method, time):
        canvas = RecordingCanvas()
        getattr(self.scene, method)(canvas, time)
        return canvas

    def test_foliage_grows_from_the_bottom_toward_the_tip(self):
        empty = self.rendered_layer("_tree", tree.GROW_START)
        self.assertEqual(empty.draws, [])
        counts, top_rows = [], []
        duration = tree.GROW_END - tree.GROW_START
        for fraction in (0.20, 0.55, 1.0):
            canvas = self.rendered_layer("_tree", tree.GROW_START + duration * fraction)
            pixels = [(x, y) for y, row in enumerate(canvas.rows)
                      for x, cell in enumerate(row) if cell.char != " "]
            counts.append(len(pixels))
            top_rows.append(min(y for _, y in pixels))
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])
        self.assertGreater(top_rows[0], top_rows[1])
        self.assertGreater(top_rows[1], top_rows[2])

    def test_decorations_wait_for_the_preceding_stage(self):
        self.assertGreaterEqual(tree.GARLAND_START, tree.GROW_END)
        self.assertGreaterEqual(tree.ORNAMENT_START, tree.GARLAND_END)
        self.assertGreaterEqual(tree.STAR_START, tree.ORNAMENT_END)
        phases = [
            (tree.GROW_END, (False, False, False)),
            ((tree.GARLAND_START + tree.GARLAND_END) / 2, (True, False, False)),
            (tree.ORNAMENT_START + 0.2, (True, True, False)),
            (tree.STAR_END, (True, True, True)),
        ]
        for time, expected in phases:
            with self.subTest(time=time):
                visible = tuple(bool(self.rendered_layer(method, time).draws)
                                for method in ("_garland", "_ornaments", "_star"))
                self.assertEqual(visible, expected)

    def test_garland_is_laid_down_progressively(self):
        self.assertFalse(self.rendered_layer("_garland", tree.GARLAND_START).draws)
        duration = tree.GARLAND_END - tree.GARLAND_START
        counts = [len(self.rendered_layer("_garland", tree.GARLAND_START + duration * p).draws)
                  for p in (0.15, 0.5, 1.0)]
        self.assertLess(counts[0], counts[1])
        self.assertLess(counts[1], counts[2])

    def test_ornaments_arrive_one_at_a_time_and_all_sixteen_settle(self):
        colors = {ornament.color for ornament in self.scene.ornaments}
        self.assertEqual(len(self.scene.ornaments), 16)
        self.assertFalse(self.rendered_layer("_ornaments", tree.ORNAMENT_START).draws)
        for index in range(tree.ORNAMENT_COUNT):
            time = tree.ORNAMENT_START + index * tree.ORNAMENT_INTERVAL + 0.1
            draws = self.rendered_layer("_ornaments", time).draws
            bodies = [draw for draw in draws if draw[2] in ("O", "o") and draw[3] in colors]
            trails = [draw for draw in draws if draw[2] == "." and draw[3] in colors]
            with self.subTest(ornament=index + 1):
                self.assertEqual(len(bodies), index + 1)
                self.assertLessEqual(len(trails), 1)
        final = self.rendered_layer("_ornaments", tree.ORNAMENT_END).draws
        self.assertEqual(sum(draw[2] in ("O", "o") for draw in final), tree.ORNAMENT_COUNT)
        self.assertFalse(any(draw[2] == "." and draw[3] in colors for draw in final))

    def test_completed_star_stays_above_the_tip_and_keeps_shining(self):
        centers, brightness = set(), set()
        tip_y = self.scene.layout.base - self.scene.layout.tree_height
        for offset in (0.0, 0.4, 0.8, 1.2, 1.6):
            draws = self.rendered_layer("_star", tree.STAR_END + offset).draws
            stars = [draw for draw in draws if draw[2] == "*"]
            self.assertEqual(len(stars), 1)
            x, y, _, style, _ = stars[0]
            self.assertLess(y, tip_y)
            self.assertAlmostEqual(x, self.scene.layout.center)
            centers.add((x, y))
            brightness.add(style)
        self.assertEqual(len(centers), 1)
        self.assertGreater(len(brightness), 1)

    def test_frames_are_ascii_and_keep_the_requested_dimensions(self):
        for width, height in ((40, 22), (80, 30), (120, 44)):
            scene = tree.Scene(width, height)
            for time in (0, tree.GROW_START + 2, tree.GARLAND_END,
                         tree.ORNAMENT_END, tree.COMPLETE):
                with self.subTest(width=width, height=height, time=time):
                    canvas = scene.render(time)
                    lines = canvas.plain().splitlines()
                    self.assertEqual(len(lines), height)
                    self.assertTrue(all(len(line) == width for line in lines))
                    self.assertTrue(all(32 <= ord(char) <= 126 for line in lines for char in line))
                    self.assertTrue(all(cell.style in tree.PALETTE for row in canvas.rows for cell in row))

    def test_a_snapshot_is_repeatable_and_does_not_depend_on_render_history(self):
        scene = tree.Scene(80, 30, seed=123)
        expected = scene.render(tree.COMPLETE).plain()
        scene.render(0)
        scene.render(tree.GARLAND_END)
        self.assertEqual(scene.render(tree.COMPLETE).plain(), expected)
        self.assertEqual(tree.Scene(80, 30, seed=123).render(tree.COMPLETE).plain(), expected)
        self.assertNotEqual(tree.Scene(80, 30, seed=124).render(tree.COMPLETE).plain(), expected)

    def test_snow_continues_after_construction(self):
        earlier = tree.Canvas(100, 40)
        later = tree.Canvas(100, 40)
        self.scene._snow(earlier, tree.COMPLETE, False)
        self.scene._snow(later, tree.COMPLETE + 2, False)
        self.assertTrue(any(cell.char != " " for row in earlier.rows for cell in row))
        self.assertNotEqual(earlier.plain(), later.plain())

    def test_baubles_gain_round_shading_when_the_terminal_has_room(self):
        widths = []
        for width, height in ((40, 22), (100, 36), (140, 50)):
            scene = tree.Scene(width, height)
            ornament = scene.ornaments[0]
            canvas = tree.Canvas(25, 15)
            scene._bauble(canvas, 12, 6, 8.0, ornament, scene._ornament_size(ornament), False)
            body = [(x, y, cell) for y, row in enumerate(canvas.rows)
                    for x, cell in enumerate(row) if cell.style.startswith(ornament.color)]
            left, right = min(x for x, _, _ in body), max(x for x, _, _ in body)
            widths.append(right - left + 1)
            self.assertTrue(all(32 <= ord(cell.char) <= 126 for _, _, cell in body))
            if width > 40:
                lit = [sum(tree.PALETTE[cell.style][0]) for x, y, cell in body if x == left and y == 6]
                shaded = [sum(tree.PALETTE[cell.style][0]) for x, y, cell in body if x == right and y == 6]
                self.assertGreater(min(lit), max(shaded))
                self.assertTrue(any(cell.char != " " for row in canvas.rows[:6] for cell in row))
        self.assertEqual(widths[0], 1)
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])

    def test_ornament_glints_leave_the_round_body_in_place(self):
        scene = tree.Scene(140, 50)
        ornament = scene.ornaments[0]
        frames = []
        for gleam in (False, True):
            canvas = tree.Canvas(25, 15)
            scene._bauble(canvas, 12, 6, 8.0, ornament, scene._ornament_size(ornament), gleam)
            frames.append(canvas)
        self.assertEqual(frames[0].rows[6][12], frames[1].rows[6][12])
        self.assertNotEqual(frames[0].rows, frames[1].rows)
        for before, after in zip(frames[0].rows, frames[1].rows):
            self.assertEqual([cell.depth for cell in before], [cell.depth for cell in after])

    def test_ornament_shadows_only_tint_needles_without_changing_geometry(self):
        canvas = tree.Canvas(8, 7)
        canvas.put(2, 4, "/", "pine6", 0.75)
        canvas.put(3, 4, "~", "gold", 0.8)
        canvas.put(4, 4, "*", "snow_near", 5.0)
        before = [row[:] for row in canvas.rows]
        self.scene._ornament_shadow(canvas, 2, 3, 3)
        self.assertNotEqual(canvas.rows[4][2].style, before[4][2].style)
        for row_before, row_after in zip(before, canvas.rows):
            for old, new in zip(row_before, row_after):
                self.assertEqual((old.char, old.depth), (new.char, new.depth))
                if not old.style.startswith("pine"):
                    self.assertEqual(old, new)

    def test_branch_geometry_stays_finite_and_gently_asymmetric(self):
        for step in range(21):
            y = step / 20
            radii = [tree.radius(y, angle * math.tau / 24) for angle in range(24)]
            self.assertTrue(all(math.isfinite(r) and r >= 0 for r in radii))
            if y == 1:
                self.assertEqual(max(radii), 0)
            else:
                self.assertGreater(min(radii), 0)
                self.assertLess((max(radii) - min(radii)) / max(radii), 0.25)
        self.assertGreater(abs(tree.radius(0.35, -0.8) - tree.radius(0.35, 0.8)), 0.001)


class CommandLineTests(unittest.TestCase):
    def test_rejects_invalid_numeric_options(self):
        invalid = [
            ["--speed", "0"], ["--speed", "-2"], ["--speed", "nan"],
            ["--fps", "0"], ["--fps", "inf"], ["--fps", "nope"],
            ["--time", "-1"], ["--time", "nan"], ["--time", "inf"],
            ["--width", "0"], ["--width", "501"], ["--height", "-1"],
            ["--once", "--loop"],
        ]
        for args in invalid:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    tree.parse_args(args)
                self.assertEqual(error.exception.code, 2)

    def test_small_snapshot_reports_a_useful_error(self):
        for width, height in ((39, 22), (40, 21)):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(width=width, height=height):
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    result = tree.main(["--snapshot", "--width", str(width), "--height", str(height)])
                self.assertEqual(result, 2)
                self.assertEqual(stdout.getvalue(), "")
                self.assertIn("40", stderr.getvalue())
                self.assertIn("22", stderr.getvalue())

    def test_redirected_output_exits_with_one_plain_ascii_frame(self):
        result = subprocess.run(
            [sys.executable, str(Path(tree.__file__).resolve()), "--music", "--width", "80", "--height", "30"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertNotIn("\x1b", result.stdout)
        self.assertNotIn("\a", result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 30)
        self.assertTrue(all(len(line) == 80 for line in lines))
        self.assertIn("M E R R Y", result.stdout)


if __name__ == "__main__":
    unittest.main()
