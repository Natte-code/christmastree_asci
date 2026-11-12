"""A tiny Christmas production, performed entirely by terminal characters."""

from __future__ import annotations

import argparse
import math
import os
import random
import shutil
import sys
import time
from dataclasses import dataclass

from music import MusicPlayer


RESET = "\x1b[0m"
BACKGROUND = (7, 13, 23)
PALETTE = {
    "sky": (BACKGROUND, False),
    "pine0": ((10, 36, 29), False),
    "pine1": ((13, 52, 34), False),
    "pine2": ((19, 70, 40), False),
    "pine3": ((27, 92, 48), False),
    "pine4": ((39, 116, 58), False),
    "pine5": ((60, 140, 70), False),
    "pine6": ((87, 161, 85), False),
    "pine7": ((120, 181, 105), False),
    "pine8": ((157, 201, 134), False),
    "growth": ((166, 233, 145), True),
    "bark": ((122, 79, 48), False),
    "bark_light": ((185, 127, 71), False),
    "gold_dark": ((150, 101, 32), False),
    "gold": ((233, 176, 55), True),
    "gold_light": ((255, 223, 118), True),
    "star": ((255, 236, 153), True),
    "white": ((245, 248, 238), True),
    "snow_far": ((47, 66, 84), False),
    "snow": ((113, 143, 163), False),
    "snow_near": ((201, 221, 228), False),
    "ground": ((66, 91, 107), False),
    "red": ((245, 77, 93), True),
    "blue": ((91, 167, 255), True),
    "pink": ((237, 120, 194), True),
    "amber": ((255, 180, 73), True),
    "violet": ((174, 139, 251), True),
    "aqua": ((83, 222, 199), True),
    "text": ((174, 195, 203), False),
    "muted": ((87, 115, 132), False),
}

ORNAMENT_BACKGROUNDS: dict[str, tuple[int, int, int]] = {}
for _color in ("red", "blue", "pink", "amber", "violet", "aqua"):
    _rgb = PALETTE[_color][0]
    PALETTE[_color + "_light"] = (tuple(round(c * 0.60 + 255 * 0.40) for c in _rgb), True)
    PALETTE[_color + "_dark"] = (tuple(round(c * 0.45) for c in _rgb), False)
    PALETTE[_color + "_gloss"] = (tuple(round(c * 0.20 + 255 * 0.80) for c in _rgb), True)
    PALETTE[_color + "_shade"] = (tuple(round(c * 0.70) for c in _rgb), False)
    ORNAMENT_BACKGROUNDS[_color] = tuple(round(c * 0.40) for c in _rgb)
    ORNAMENT_BACKGROUNDS[_color + "_gloss"] = tuple(round(c * 0.78) for c in _rgb)
    ORNAMENT_BACKGROUNDS[_color + "_shade"] = tuple(round(c * 0.32) for c in _rgb)

GROW_START = 1.0
GROW_END = 9.0
GARLAND_START = 9.6
GARLAND_END = 16.6
ORNAMENT_START = 17.2
ORNAMENT_COUNT = 16
ORNAMENT_INTERVAL = 0.52
ORNAMENT_END = ORNAMENT_START + ORNAMENT_COUNT * ORNAMENT_INTERVAL
STAR_START = ORNAMENT_END + 0.6
STAR_END = STAR_START + 2.5
COMPLETE = STAR_END + 1.0
LOOP_DURATION = COMPLETE + 14.0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def smooth(value: float) -> float:
    value = clamp(value)
    return value * value * (3.0 - 2.0 * value)


def progress(t: float, start: float, end: float) -> float:
    return clamp((t - start) / (end - start))


def branch_phase(y: float) -> float:
    return y * 6.4 + 0.12 * math.sin(y * 8.0)


def radius(y: float, angle: float = 0.0) -> float:
    # Slightly uneven whorls and branch tips keep the fir from looking lathe-cut.
    skirt = branch_phase(y) % 1.0
    flare = 0.75 + 0.25 * (1.0 - smooth(skirt))
    boughs = (0.97 + 0.035 * math.sin(3 * angle + y * 9)
              + 0.025 * math.sin(7 * angle - y * 13)
              + 0.012 * math.sin(13 * angle + y * 29))
    return max(0.0, 1.0 - y) ** 0.86 * flare * boughs


@dataclass(frozen=True)
class Cell:
    char: str = " "
    style: str = "sky"
    depth: float = -999.0


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.rows = [[Cell() for _ in range(width)] for _ in range(height)]

    def put(self, x: float, y: float, char: str, style: str, depth: float = 10.0) -> None:
        ix, iy = math.floor(x + 0.5), math.floor(y + 0.5)
        if 0 <= ix < self.width and 0 <= iy < self.height:
            if depth >= self.rows[iy][ix].depth:
                self.rows[iy][ix] = Cell(char, style, depth)

    def text(self, x: int, y: int, value: str, style: str = "text") -> None:
        for offset, char in enumerate(value):
            self.put(x + offset, y, char, style, 100.0)

    def centered(self, y: int, value: str, style: str = "text") -> None:
        value = value[: self.width - 2]
        self.text((self.width - len(value)) // 2, y, value, style)

    def plain(self) -> str:
        return "\n".join("".join(cell.char for cell in row) for row in self.rows)

    def ansi_row(self, row: int, color: bool = True) -> str:
        if not color:
            return "".join(cell.char for cell in self.rows[row])
        chunks, previous, previous_background = [], None, None
        for cell in self.rows[row]:
            if cell.style != previous:
                rgb, bold = PALETTE[cell.style]
                chunks.append(f"\x1b[{1 if bold else 22};38;2;{rgb[0]};{rgb[1]};{rgb[2]}m")
                background = ORNAMENT_BACKGROUNDS.get(cell.style, BACKGROUND)
                if background != previous_background:
                    chunks.append(f"\x1b[48;2;{background[0]};{background[1]};{background[2]}m")
                    previous_background = background
                previous = cell.style
            chunks.append(cell.char)
        return "".join(chunks) + RESET


@dataclass(frozen=True)
class Layout:
    width: int
    height: int

    @property
    def center(self) -> float:
        return (self.width - 1) / 2

    @property
    def base(self) -> int:
        return self.height - (7 if self.height < 30 else 8)

    @property
    def tree_height(self) -> int:
        return self.base - (4 if self.height < 30 else 7)

    @property
    def half_width(self) -> float:
        return min(self.width * 0.30, self.tree_height * 1.05)

    @property
    def floor(self) -> int:
        return self.height - 5

    def project(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        return (
            self.center + x * self.half_width,
            self.base - y * self.tree_height + z * self.tree_height * 0.075,
            z + y * 0.32,
        )


@dataclass(frozen=True)
class Needle:
    x: float
    y: float
    z: float
    char: str
    shade: int


@dataclass(frozen=True)
class Ornament:
    y: float
    angle: float
    color: str
    side: int


class Scene:
    def __init__(self, width: int, height: int, seed: int = 25) -> None:
        self.layout = Layout(width, height)
        self.seed = seed
        rng = random.Random(seed)
        self.flakes = [
            (rng.random(), rng.random(), rng.uniform(0.5, 1.5), rng.random() * math.tau, i % 3)
            for i in range(max(70, width * height // 38))
        ]
        self.needles = self._needles()
        self._finished_tree: list[tuple[int, int, Cell]] | None = None
        colors = ["red", "blue", "amber", "pink", "aqua", "violet"]
        # Front-facing baubles stay readable, while the garland travels all the way around.
        positions = [
            (0.10, -0.68), (0.15, 0.62), (0.24, -0.13), (0.29, -0.86),
            (0.34, 0.80), (0.40, 0.27), (0.46, -0.57), (0.51, 0.91),
            (0.56, -0.10), (0.62, -0.85), (0.67, 0.52), (0.72, -0.30),
            (0.77, 0.84), (0.82, -0.77), (0.86, 0.20), (0.91, -0.20),
        ]
        self.ornaments = [
            Ornament(y, angle, colors[i % len(colors)], -1 if i % 2 == 0 else 1)
            for i, (y, angle) in enumerate(positions)
        ]

    def _needles(self) -> list[Needle]:
        points = []
        rings = max(65, self.layout.tree_height * 5)
        for row in range(rings + 1):
            y = row / rings
            steps = max(3, math.ceil((1.0 - y) ** 0.86 * self.layout.half_width * 4))
            skirt = branch_phase(y) % 1.0
            for col in range(steps + 1):
                angle = math.asin(-1.0 + 2.0 * col / steps)
                nx, nz = math.sin(angle), math.cos(angle)
                r = radius(y, angle)
                x, z = nx * r, nz * r
                noise = math.sin(row * 127.1 + col * 311.7 + self.seed) * 43758.5453
                grain = noise - math.floor(noise)
                # Light follows the boughs; random brightness alone reads as static.
                dr = (radius(y, angle + 0.015) - radius(y, angle - 0.015)) / 0.03
                slope = dr / max(r, 0.02)
                normal_x, normal_z = nx - slope * nz, nz + slope * nx
                length = math.sqrt(normal_x * normal_x + normal_z * normal_z + 0.25)
                diffuse = max(0.0, (-0.55 * normal_x + 0.375 + 0.65 * normal_z) / (length * 1.135))
                spray = 0.5 + 0.5 * math.cos(y * math.tau * 17 + abs(nx) * 7.5
                                           + math.sin(angle * 9 + y * 13) * 1.1)
                underside = math.exp(-((skirt - 0.93) / 0.13) ** 2)
                light = clamp(0.13 + diffuse * 0.77 + (spray - 0.5) * 0.14
                              + (grain - 0.5) * 0.10 - underside * 0.20)
                shade = min(8, int(light * 9))
                if shade <= 2:
                    char = "." if grain < 0.55 else ":"
                elif spray > 0.91 and grain > 0.35:
                    char = "v" if grain > 0.65 else "Y"
                elif grain < 0.54:
                    char = "/" if nx + 0.18 * math.sin(angle * 11 + y * 7) < 0 else "\\"
                else:
                    char = "'" if grain < 0.88 else ","
                points.append(Needle(x, y, z, char, shade))
        return points

    def _snow(self, canvas: Canvas, t: float, foreground: bool) -> None:
        layout = self.layout
        span = max(1, layout.floor - 4)
        for fx, fy, speed, phase, layer in self.flakes:
            if (layer == 2) != foreground:
                continue
            x = (fx * layout.width + math.sin(t * 0.35 + phase) * (2 + layer) + t * (0.15 + layer * 0.1)) % layout.width
            y = 4 + (fy * span + t * speed * (0.35 + layer * 0.25)) % span
            char = "." if layer == 0 else ("+" if layer == 2 and math.sin(phase) > 0.65 else "*")
            canvas.put(x, y, char, ("snow_far", "snow", "snow_near")[layer], 5.0 if foreground else -10.0)

    def _ground(self, canvas: Canvas, t: float) -> None:
        layout = self.layout
        for x in range(2, layout.width - 2):
            ripple = math.sin(x * 0.13) * 0.4 + math.cos(x * 0.071) * 0.35
            canvas.put(x, layout.floor + ripple, "_" if x % 4 else ".", "ground", -4.0)
        # A shallow ellipse anchors the tree in the snow instead of letting it float.
        for i in range(81):
            angle = i / 80 * math.tau
            canvas.put(layout.center + math.cos(angle) * layout.half_width * 0.79,
                       layout.floor + math.sin(angle) * 0.65,
                       "." if i % 3 else "_", "snow", -3.0)

    def _trunk(self, canvas: Canvas, t: float) -> None:
        amount = smooth(progress(t, 0.3, 1.7))
        if amount <= 0:
            return
        layout = self.layout
        trunk_width = max(1, round(layout.half_width * 0.09))
        for row in range(round(4 * amount)):
            for x in range(-trunk_width, trunk_width + 1):
                canvas.put(layout.center + x, layout.floor - row, "|" if x % 2 else ":",
                           "bark_light" if x < 0 else "bark", -0.2)

    def _tree(self, canvas: Canvas, t: float) -> None:
        grown = progress(t, GROW_START, GROW_END)
        if grown <= 0:
            return
        if grown >= 1:
            if self._finished_tree is None:
                surface = Canvas(self.layout.width, self.layout.height)
                self._draw_needles(surface, grown)
                self._finished_tree = [
                    (x, y, cell)
                    for y, row in enumerate(surface.rows)
                    for x, cell in enumerate(row)
                    if cell.char != " "
                ]
            for x, y, cell in self._finished_tree:
                canvas.put(x, y, cell.char, cell.style, cell.depth)
            return
        self._draw_needles(canvas, grown)

    def _draw_needles(self, canvas: Canvas, grown: float) -> None:
        layout = self.layout
        for needle in self.needles:
            local_growth = smooth((grown - needle.y * 0.93) / 0.07)
            if local_growth <= 0:
                continue
            x, y, depth = layout.project(needle.x * local_growth, needle.y, needle.z * local_growth)
            style = f"pine{needle.shade}"
            if local_growth < 0.9 and needle.shade >= 6:
                style = "growth"
            canvas.put(x, y, needle.char, style, depth)

    def garland_point(self, amount: float) -> tuple[float, float, float]:
        y = 0.055 + amount * 0.90
        angle = amount * math.tau * 4.25 + 0.9
        r = radius(y, angle) + 0.045
        return self.layout.project(math.sin(angle) * r, y, math.cos(angle) * r)

    def _garland(self, canvas: Canvas, t: float) -> None:
        amount = progress(t, GARLAND_START, GARLAND_END)
        if amount <= 0:
            return
        samples = max(700, self.layout.tree_height * 45)
        for i in range(math.ceil(samples * amount) + 1):
            s = min(amount, i / samples)
            x, y, depth = self.garland_point(s)
            sparkle = math.sin(i * 1.7 + t * 3.0)
            style = "gold_light" if sparkle > 0.91 else "gold"
            char = "*" if sparkle > 0.96 else "~"
            canvas.put(x, y, char, style, depth + 0.045)
        if amount < 1:
            x, y, depth = self.garland_point(amount)
            canvas.put(x, y, "*", "white", depth + 0.12)

    def _ornament_size(self, ornament: Ornament) -> int:
        room = radius(ornament.y, ornament.angle) * self.layout.half_width
        if self.layout.width < 60 or room < 2.7:
            return 1
        if self.layout.width >= 140 and self.layout.tree_height >= 35 and room >= 10.0:
            return 5
        return 3

    def _ornament_shadow(self, canvas: Canvas, x: float, y: float, size: int) -> None:
        # Tint the needles already here; a loose black dot would look like another bauble.
        for offset in range(-(size // 2) + 1, size // 2 + 2):
            ix, iy = math.floor(x + offset + 0.5), math.floor(y + 1.5)
            if 0 <= ix < canvas.width and 0 <= iy < canvas.height:
                cell = canvas.rows[iy][ix]
                if cell.style.startswith("pine"):
                    canvas.put(ix, iy, cell.char, "pine0", cell.depth)

    def _bauble(self, canvas: Canvas, x: float, y: float, depth: float,
                ornament: Ornament, size: int, gleam: bool) -> None:
        color = ornament.color
        if size == 1:
            canvas.put(x, y, "o", color, depth + 0.13)
            return
        canvas.put(x, y - (2 if size == 5 else 1), "'", "gold_light", depth + 0.11)
        half = size // 2
        rim_light = "white" if gleam and size == 3 else color + "_light"
        canvas.put(x - half, y, "(", rim_light, depth + 0.10)
        canvas.put(x + half, y, ")", color + "_dark", depth + 0.10)
        if size == 5:
            for dx, char in ((-1, "."), (0, "-"), (1, ".")):
                canvas.put(x + dx, y - 1, char,
                           color + ("_light" if dx <= 0 else "_dark"), depth + 0.09)
            canvas.put(x - 1, y, "*" if gleam else "'", color + "_gloss", depth + 0.14)
            canvas.put(x + 1, y, ":", color + "_shade", depth + 0.12)
            for dx, char in ((-1, "'"), (0, "-"), (1, "'")):
                canvas.put(x + dx, y + 1, char, color + "_shade", depth + 0.08)
        canvas.put(x, y, "O", color, depth + 0.13)

    def _ornaments(self, canvas: Canvas, t: float) -> None:
        layout = self.layout
        for i, ornament in enumerate(self.ornaments):
            p = progress(t, ORNAMENT_START + i * ORNAMENT_INTERVAL,
                         ORNAMENT_START + i * ORNAMENT_INTERVAL + 0.44)
            if p <= 0:
                continue
            r = radius(ornament.y, ornament.angle) + 0.08
            x, y, depth = layout.project(math.sin(ornament.angle) * r,
                                         ornament.y, math.cos(ornament.angle) * r)
            flying = p < 1
            if flying:
                ease = 1.0 - (1.0 - p) ** 3
                start_x = layout.center + ornament.side * (layout.half_width + 8)
                x = start_x + (x - start_x) * ease
                y = y - (1 - ease) * 4 - math.sin(p * math.pi) * 2
                depth = 8.0
                canvas.put(x - ornament.side * 2, y, ".", ornament.color, depth)
            else:
                y += math.sin((t - ORNAMENT_START - i * ORNAMENT_INTERVAL) * 8) * 0.12
            size = self._ornament_size(ornament)
            if not flying:
                self._ornament_shadow(canvas, x, y, size)
            gleam = not flying and math.sin(t * 2.5 + i * 2.9) > 0.97
            self._bauble(canvas, x, y, depth, ornament, size, gleam)

    def _star(self, canvas: Canvas, t: float) -> None:
        amount = progress(t, STAR_START, STAR_END)
        if amount <= 0:
            return
        layout = self.layout
        target_y = layout.base - layout.tree_height - 2
        y = target_y - (1.0 - smooth(amount)) * 5
        if y < (1 if layout.height < 30 else 3):
            return
        pulse = (math.sin(t * 3.6) + 1.0) / 2
        style = "star" if pulse < 0.7 else "white"
        canvas.put(layout.center, y, "*", style, 15.0)
        for dx, dy, char in [(-1, 0, "<"), (1, 0, ">"), (0, -1, "^"), (0, 1, "v")]:
            canvas.put(layout.center + dx, y + dy, char, style, 15.0)
        if amount >= 1 and pulse > 0.30:
            for dx, dy, char in [(-3, 0, "-"), (3, 0, "-"), (-2, -1, "\\"),
                                  (2, -1, "/"), (-2, 1, "/"), (2, 1, "\\")]:
                canvas.put(layout.center + dx, y + dy, char, "gold_dark" if pulse < 0.7 else "gold_light", 14.0)
        if amount >= 1:
            for i in range(7):
                angle = i * 2.4 + t * 0.65
                distance = 3 + ((t * 0.7 + i * 0.71) % 3)
                canvas.put(layout.center + math.cos(angle) * distance,
                           target_y + math.sin(angle) * distance * 0.45,
                           ".", "gold_dark", -2.0)

    @staticmethod
    def stage(t: float) -> tuple[str, float]:
        if t < GROW_START:
            return "A seed of Christmas magic", 0.0
        if t < GROW_END:
            return "Growing, branch by branch", progress(t, GROW_START, GROW_END)
        if t < GARLAND_START:
            return "Every branch in place", 1.0
        if t < GARLAND_END:
            return "Winding one golden garland", progress(t, GARLAND_START, GARLAND_END)
        if t < ORNAMENT_START:
            return "A little gold goes a long way", 1.0
        if t < ORNAMENT_END:
            count = min(ORNAMENT_COUNT, int((t - ORNAMENT_START) / ORNAMENT_INTERVAL) + 1)
            return f"Hanging ornaments  {count:02d} / {ORNAMENT_COUNT}", progress(t, ORNAMENT_START, ORNAMENT_END)
        if t < STAR_START:
            return "One last wish...", 1.0
        if t < STAR_END:
            return "A star to light the winter night", progress(t, STAR_START, STAR_END)
        return "M E R R Y   C H R I S T M A S", 1.0

    def render(self, t: float, paused: bool = False, music: bool = False, speed: float = 1.0) -> Canvas:
        layout = self.layout
        canvas = Canvas(layout.width, layout.height)
        self._snow(canvas, t, False)
        self._ground(canvas, t)
        self._trunk(canvas, t)
        self._tree(canvas, t)
        self._garland(canvas, t)
        self._ornaments(canvas, t)
        self._snow(canvas, t, True)
        self._star(canvas, t)
        title = "*  A   L I T T L E   C H R I S T M A S  *" if layout.width >= 60 else "* A LITTLE CHRISTMAS *"
        canvas.centered(0 if layout.height < 30 else 1, title, "gold_light")
        if layout.height >= 30:
            subtitle = "a winter night, built one piece at a time" if layout.width >= 60 else "built one piece at a time"
            canvas.centered(2, subtitle, "muted")
        label, amount = self.stage(t)
        canvas.centered(layout.height - 3, "[ PAUSED ]" if paused else label,
                        "gold_light" if t >= STAR_END else "text")
        if t < STAR_END:
            size = min(26, layout.width - 12)
            filled = round(amount * size)
            canvas.centered(layout.height - 2, "[" + "=" * filled + "." * (size - filled) + "]", "gold_dark")
        else:
            canvas.centered(layout.height - 2, "may your days be merry and bright", "muted")
        controls = f"[space] pause  [r] replay  [m] music {'on' if music else 'off'}  [q] quit"
        if layout.width < 68:
            controls = "SPACE pause  R replay  M music  Q quit"
        if layout.width >= 90:
            controls += f"   {speed:g}x"
        canvas.centered(layout.height - 1, controls, "muted")
        return canvas


class Terminal:
    def __init__(self, color: bool = True) -> None:
        self.color = color
        self.previous: list[list[Cell]] = []
        self._input_settings = None
        self._console_mode = None

    def __enter__(self) -> Terminal:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            handle = kernel.GetStdHandle(-11 & 0xFFFFFFFF)
            mode = wintypes.DWORD()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                self._console_mode = (kernel, handle, mode.value)
                if not kernel.SetConsoleMode(handle, mode.value | 0x0004):
                    raise OSError("This console needs ANSI support. Try Windows Terminal.")
        elif sys.stdin.isatty():
            import termios
            import tty

            self._input_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        # Stay in the alternate screen so quitting gives the user their shell back.
        background = f"\x1b[48;2;{BACKGROUND[0]};{BACKGROUND[1]};{BACKGROUND[2]}m" if self.color else ""
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[?7l" + background + "\x1b[2J\x1b[H")
        sys.stdout.flush()
        return self

    def __exit__(self, *_: object) -> None:
        try:
            sys.stdout.write(RESET + "\x1b[?7h\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
        finally:
            if self._input_settings is not None:
                import termios

                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._input_settings)
            if self._console_mode is not None:
                kernel, handle, mode = self._console_mode
                kernel.SetConsoleMode(handle, mode)

    def key(self) -> str:
        if os.name == "nt":
            import msvcrt

            if msvcrt.kbhit():
                value = msvcrt.getwch()
                if value in ("\x00", "\xe0"):
                    if msvcrt.kbhit():
                        msvcrt.getwch()
                    return ""
                return value.lower()
        elif sys.stdin.isatty():
            import select

            if select.select([sys.stdin], [], [], 0)[0]:
                return sys.stdin.read(1).lower()
        return ""

    def draw(self, canvas: Canvas) -> None:
        resized = len(self.previous) != canvas.height or (self.previous and len(self.previous[0]) != canvas.width)
        chunks = ["\x1b[2J"] if resized else []
        background = f"\x1b[48;2;{BACKGROUND[0]};{BACKGROUND[1]};{BACKGROUND[2]}m" if self.color else ""
        for y, row in enumerate(canvas.rows):
            if resized or row != self.previous[y]:
                chunks.append(f"\x1b[{y + 1};1H" + background + canvas.ansi_row(y, self.color))
        sys.stdout.write("".join(chunks))
        sys.stdout.flush()
        self.previous = canvas.rows


def positive_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise argparse.ArgumentTypeError("use a finite number greater than zero")
    return result


def dimension(value: str) -> int:
    result = int(value)
    if not 1 <= result <= 500:
        raise argparse.ArgumentTypeError("use a size between 1 and 500")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--music", action="store_true", help="play a gentle Jingle Bells melody (Windows)")
    parser.add_argument("--speed", type=positive_float, default=1.0, help="animation speed multiplier (default: 1)")
    parser.add_argument("--fps", type=positive_float, default=24.0, help="frames per second (default: 24)")
    parser.add_argument("--once", action="store_true", help="finish after the build and eight seconds of snowfall")
    parser.add_argument("--loop", action="store_true", help="rebuild the tree after a festive pause")
    parser.add_argument("--no-color", action="store_true", help="use plain ASCII without ANSI colors")
    parser.add_argument("--snapshot", action="store_true", help="print a single frame and exit")
    parser.add_argument("--time", type=float, default=COMPLETE + 2, help="animation time for --snapshot (seconds)")
    parser.add_argument("--width", type=dimension, help="canvas columns (default: terminal width)")
    parser.add_argument("--height", type=dimension, help="canvas rows (default: terminal height)")
    parser.add_argument("--seed", type=int, default=25, help="snow and branch texture seed")
    args = parser.parse_args(argv)
    if not math.isfinite(args.time) or args.time < 0:
        parser.error("--time must be a finite number of seconds, at least zero")
    if args.once and args.loop:
        parser.error("choose either --once or --loop")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    color = not args.no_color and "NO_COLOR" not in os.environ
    if args.snapshot or not sys.stdout.isatty():
        size = shutil.get_terminal_size((100, 36))
        width, height = args.width or size.columns, args.height or size.lines
        if width < 40 or height < 22:
            print("Please use a terminal at least 40 columns wide and 22 rows tall.", file=sys.stderr)
            return 2
        canvas = Scene(width, height, args.seed).render(args.time)
        # Redirected output is useful as a plain-text Christmas card, too.
        if color and sys.stdout.isatty():
            print("\n".join(canvas.ansi_row(y) for y in range(height)))
        else:
            print(canvas.plain())
        return 0

    player = MusicPlayer()
    try:
        with Terminal(color) as terminal:
            if args.music:
                player.start()
            scene = None
            elapsed, paused = 0.0, False
            last = time.perf_counter()
            while True:
                frame_start = time.perf_counter()
                advance = (frame_start - last) * args.speed if not paused else 0.0
                elapsed += advance
                last = frame_start
                key = terminal.key()
                if key in ("q", "\x1b", "\x03"):
                    break
                if key == " ":
                    paused = not paused
                elif key == "r":
                    elapsed = 0.0
                elif key == "m":
                    player.toggle()
                if args.once and elapsed >= COMPLETE + 8:
                    break
                if args.loop and elapsed >= LOOP_DURATION:
                    elapsed %= LOOP_DURATION
                actual = shutil.get_terminal_size((100, 36))
                width = min(args.width or actual.columns, actual.columns, 240)
                height = min(args.height or actual.lines, actual.lines, 100)
                if width < 40 or height < 22:
                    canvas = Canvas(max(1, width), max(1, height))
                    if height >= 3:
                        canvas.centered(1, "Make the terminal larger", "gold_light")
                        canvas.centered(2, "40 columns x 22 rows minimum. Q quits.", "text")
                    terminal.draw(canvas)
                    # Give the build back its time when the window is usable again.
                    elapsed -= advance
                else:
                    if scene is None or (width, height) != (scene.layout.width, scene.layout.height):
                        scene = Scene(width, height, args.seed)
                    terminal.draw(scene.render(elapsed, paused, player.enabled, args.speed))
                time.sleep(max(0, 1 / args.fps - (time.perf_counter() - frame_start)))
    except (KeyboardInterrupt, BrokenPipeError):
        pass
    finally:
        player.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
