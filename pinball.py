from __future__ import annotations

import ctypes
import curses
import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Deque, Dict, List, Optional, Sequence, Tuple


FPS = 60
FRAME_TIME = 1.0 / FPS

MIN_HEIGHT = 24
MIN_WIDTH = 60

STARTING_BALLS = 3
MAX_BALLS = 5
MAX_MULTIPLIER = 5
MAX_SCORES = 10

BALL_RADIUS = 0.34
BALL_GRAVITY = 22.0
BALL_TERMINAL_SPEED = 34.0
BALL_TRAIL_LENGTH = 12

PLUNGER_CHARGE_TIME = 0.85
PLUNGER_MIN_SPEED = 20.0
PLUNGER_MAX_SPEED = 34.0
SKILL_SHOT_WINDOW = 3.0
BALL_SAVE_TIME = 8.0

FLIPPER_LENGTH = 5.4
FLIPPER_REST_ANGLE = math.radians(16.0)
FLIPPER_ACTIVE_ANGLE = math.radians(56.0)
FLIPPER_SPEED = math.radians(620.0)

BUMPER_BOOST = 23.0
MESSAGE_TIME = 1.2

VISIBLE_SEGMENT_NAMES = {
    "left_wall",
    "top_wall",
    "left_orbit",
    "right_orbit",
    "left_upper_feed",
    "right_upper_feed",
    "left_reactor_guide",
    "right_reactor_guide",
    "main_right_wall",
    "plunger_outer",
    "plunger_inner",
    "left_lane",
    "right_lane",
    "left_sling",
    "right_sling",
}

SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scores.json")

TITLE_LINES = [
    "ORBITAL REACTOR",
    "Light I O N.",
    "Cash the core.",
]


CP_BORDER = 1
CP_HUD = 2
CP_BEST = 3
CP_TITLE = 4
CP_BALL = 5
CP_TRAIL = 6
CP_FLIPPER = 7
CP_BUMPER = 8
CP_TARGET = 9
CP_TARGET_LIT = 10
CP_REACTOR = 11
CP_REACTOR_HOT = 12
CP_ALERT = 13
CP_GOAL = 14
CP_SAVE = 15
CP_LEADERBOARD = 16
CP_PANEL = 17


VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_A = 0x41
VK_D = 0x44
VK_SPACE = 0x20


class Phase(str, Enum):
    TITLE = "title"
    PLAYING = "playing"
    GAME_OVER = "game_over"
    ENTER_NAME = "enter_name"
    LEADERBOARD = "leaderboard"


@dataclass
class ScoreEntry:
    name: str
    score: int
    mult: int

    @classmethod
    def from_dict(cls, data: object) -> Optional["ScoreEntry"]:
        if not isinstance(data, dict):
            return None

        try:
            score = int(data.get("score", 0))
            mult = int(data.get("mult", data.get("wave", 1)))
        except (TypeError, ValueError):
            return None

        raw_name = str(data.get("name", "???")).upper()
        name = raw_name[:3].ljust(3)
        return cls(name=name, score=max(0, score), mult=max(1, mult))

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "mult": self.mult}


class Leaderboard:
    def __init__(self, path: str, limit: int = MAX_SCORES) -> None:
        self.path = path
        self.limit = limit
        self.entries = self._load()

    def _load(self) -> List[ScoreEntry]:
        if not os.path.exists(self.path):
            return []

        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(raw, list):
            return []

        entries = []
        for item in raw:
            entry = ScoreEntry.from_dict(item)
            if entry is not None:
                entries.append(entry)

        entries.sort(key=lambda entry: (entry.score, entry.mult), reverse=True)
        return entries[: self.limit]

    def save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump([entry.to_dict() for entry in self.entries], handle, indent=2)
        except OSError:
            pass

    def best_score(self) -> int:
        return self.entries[0].score if self.entries else 0

    def qualifies(self, score: int) -> bool:
        if score <= 0:
            return False
        if len(self.entries) < self.limit:
            return True
        return score > self.entries[-1].score

    def add(self, name: str, score: int, mult: int) -> None:
        entry = ScoreEntry(name=name[:3].ljust(3).upper(), score=max(0, score), mult=max(1, mult))
        self.entries.append(entry)
        self.entries.sort(key=lambda item: (item.score, item.mult), reverse=True)
        self.entries = self.entries[: self.limit]
        self.save()

    def top(self, limit: int) -> List[ScoreEntry]:
        return self.entries[:limit]


@dataclass
class Ball:
    x: float
    y: float
    vx: float
    vy: float

    @property
    def ix(self) -> int:
        return int(round(self.x))

    @property
    def iy(self) -> int:
        return int(round(self.y))


@dataclass
class Segment:
    name: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float = 0.26


@dataclass
class CircleObject:
    name: str
    x: float
    y: float
    radius: float
    kind: str
    label: str = ""


@dataclass
class TriggerZone:
    name: str
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass
class Flipper:
    side: str
    pivot_x: float
    pivot_y: float
    length: float
    angle: float
    active: bool = False
    angular_velocity: float = 0.0

    def update(self, dt: float) -> None:
        previous = self.angle
        self.angle = FLIPPER_ACTIVE_ANGLE if self.active else FLIPPER_REST_ANGLE
        self.angular_velocity = (self.angle - previous) / dt if dt > 0 else 0.0

    def endpoints(self) -> Tuple[float, float, float, float]:
        dx = math.cos(self.angle) * self.length
        dy = math.sin(self.angle) * self.length
        if self.side == "left":
            return (self.pivot_x, self.pivot_y, self.pivot_x + dx, self.pivot_y - dy)
        return (self.pivot_x, self.pivot_y, self.pivot_x - dx, self.pivot_y - dy)


@dataclass
class TableLayout:
    left: float
    top: float
    right: float
    bottom: float
    main_right: float
    plunger_left: float
    plunger_right: float
    plunger_x: float
    launch_gate_y: float
    left_flipper_pivot: Tuple[float, float]
    right_flipper_pivot: Tuple[float, float]
    drain_left: float
    drain_right: float
    drain_y: float
    segments: List[Segment]
    bumpers: List[CircleObject]
    targets: List[CircleObject]
    posts: List[CircleObject]
    reactor: CircleObject
    rescue_zone: TriggerZone
    skill_zone: TriggerZone
    left_orbit_zone: TriggerZone
    right_orbit_zone: TriggerZone
    core_lane_zone: TriggerZone


@dataclass
class FrameInput:
    left_down: bool = False
    right_down: bool = False
    action_down: bool = False
    quit: bool = False
    enter: bool = False
    backspace: bool = False
    typed_char: Optional[str] = None
    open_scores: bool = False


class KeyPoller:
    def __init__(self) -> None:
        self._get_async_key_state = None
        if os.name != "nt":
            return

        user32 = ctypes.windll.user32
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = ctypes.c_short
        self._get_async_key_state = user32.GetAsyncKeyState

    def _is_pressed(self, *keys: int) -> bool:
        if self._get_async_key_state is None:
            return False
        return any(self._get_async_key_state(key) & 0x8000 for key in keys)

    def poll(self, left: bool, right: bool, action: bool) -> Tuple[bool, bool, bool]:
        if self._get_async_key_state is None:
            return left, right, action

        return (
            left or self._is_pressed(VK_LEFT, VK_A),
            right or self._is_pressed(VK_RIGHT, VK_D),
            action or self._is_pressed(VK_SPACE),
        )


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def nearest_point_on_segment(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> Tuple[float, float, float]:
    dx = x2 - x1
    dy = y2 - y1
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-6:
        return x1, y1, 0.0

    t = ((px - x1) * dx + (py - y1) * dy) / length_sq
    t = clamp(t, 0.0, 1.0)
    return x1 + dx * t, y1 + dy * t, t


class Game:
    def __init__(self, screen: "curses._CursesWindow") -> None:
        self.screen = screen
        self.height, self.width = self.screen.getmaxyx()
        self.colors_enabled = False
        self.key_poller = KeyPoller()
        self.leaderboard = Leaderboard(SCORES_FILE)

        self.phase = Phase.TITLE
        self.layout = self._build_layout()
        self.left_flipper = Flipper("left", *self.layout.left_flipper_pivot, FLIPPER_LENGTH, FLIPPER_REST_ANGLE)
        self.right_flipper = Flipper("right", *self.layout.right_flipper_pivot, FLIPPER_LENGTH, FLIPPER_REST_ANGLE)

        self.score = 0
        self.balls = STARTING_BALLS
        self.multiplier = 1
        self.peak_multiplier = 1
        self.jackpots = 0
        self.target_lights = [False, False, False]

        self.ball: Optional[Ball] = None
        self.ball_trail: Deque[Tuple[int, int]] = deque(maxlen=BALL_TRAIL_LENGTH)
        self.ball_in_launch_lane = False
        self.plunger_charge = 0.0
        self.launch_redirect_done = False
        self.skill_shot_timer = 0.0
        self.skill_shot_ready = False
        self.ball_save_timer = 0.0
        self.combo_count = 0
        self.combo_timer = 0.0
        self.bumper_charge_hits = 0

        self.message = "PRESS SPACE TO START"
        self.message_timer = 999.0

        self.flash_timers: Dict[str, float] = {}
        self.hit_cooldowns: Dict[str, float] = {}
        self.pending_score = 0
        self.pending_mult = 1
        self.name_buffer = ""

        self.last_action_down = False
        self.last_size = (self.height, self.width)

        self._configure_curses()

    def _configure_curses(self) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        self.screen.nodelay(True)
        self.screen.keypad(True)

        try:
            curses.noecho()
        except curses.error:
            pass

        if not curses.has_colors():
            return

        self.colors_enabled = True
        curses.start_color()
        try:
            curses.use_default_colors()
        except curses.error:
            pass

        curses.init_pair(CP_BORDER, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_HUD, curses.COLOR_CYAN, -1)
        curses.init_pair(CP_BEST, curses.COLOR_YELLOW, -1)
        curses.init_pair(CP_TITLE, curses.COLOR_CYAN, -1)
        curses.init_pair(CP_BALL, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_TRAIL, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_FLIPPER, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_BUMPER, curses.COLOR_MAGENTA, -1)
        curses.init_pair(CP_TARGET, curses.COLOR_BLUE, -1)
        curses.init_pair(CP_TARGET_LIT, curses.COLOR_YELLOW, -1)
        curses.init_pair(CP_REACTOR, curses.COLOR_CYAN, -1)
        curses.init_pair(CP_REACTOR_HOT, curses.COLOR_RED, -1)
        curses.init_pair(CP_ALERT, curses.COLOR_RED, -1)
        curses.init_pair(CP_GOAL, curses.COLOR_GREEN, -1)
        curses.init_pair(CP_SAVE, curses.COLOR_GREEN, -1)
        curses.init_pair(CP_LEADERBOARD, curses.COLOR_CYAN, -1)
        curses.init_pair(CP_PANEL, curses.COLOR_WHITE, -1)

    def _attr(self, pair_id: int, *flags: int) -> int:
        attr = curses.color_pair(pair_id) if self.colors_enabled else 0
        for flag in flags:
            attr |= flag
        return attr

    def _sync_screen_size(self) -> None:
        self.height, self.width = self.screen.getmaxyx()
        if (self.height, self.width) == self.last_size:
            return

        self.last_size = (self.height, self.width)
        if self.height < MIN_HEIGHT or self.width < MIN_WIDTH:
            return

        self.layout = self._build_layout()
        left_active = self.left_flipper.active
        right_active = self.right_flipper.active
        self.left_flipper = Flipper("left", *self.layout.left_flipper_pivot, FLIPPER_LENGTH, FLIPPER_REST_ANGLE)
        self.right_flipper = Flipper("right", *self.layout.right_flipper_pivot, FLIPPER_LENGTH, FLIPPER_REST_ANGLE)
        self.left_flipper.active = left_active
        self.right_flipper.active = right_active

        if self.phase == Phase.PLAYING:
            self._serve_ball()
            self._show_message("TABLE RECALIBRATED")

    def run(self) -> None:
        last_frame = time.perf_counter()

        while True:
            now = time.perf_counter()
            dt = min(now - last_frame, 0.05)
            last_frame = now

            self._sync_screen_size()
            frame = self._poll_input()
            action_pressed = frame.action_down and not self.last_action_down
            action_released = self.last_action_down and not frame.action_down

            if not self._handle_input(frame, action_pressed):
                break

            if self.height >= MIN_HEIGHT and self.width >= MIN_WIDTH:
                if self.phase == Phase.PLAYING:
                    self._update_playing(dt, frame, action_pressed, action_released)
                else:
                    self._update_flippers(dt, frame)
                    self._tick_timers(dt)

            self._render()
            self.last_action_down = frame.action_down

            leftover = FRAME_TIME - (time.perf_counter() - now)
            if leftover > 0:
                time.sleep(leftover)

    def _poll_input(self) -> FrameInput:
        frame = FrameInput()

        while True:
            key = self.screen.getch()
            if key == -1:
                break

            if key in (ord("q"), ord("Q"), 27):
                frame.quit = True
            elif key in (curses.KEY_LEFT, ord("a"), ord("A")):
                frame.left_down = True
            elif key in (curses.KEY_RIGHT, ord("d"), ord("D")):
                frame.right_down = True
            elif key == ord(" "):
                frame.action_down = True
            elif key in (curses.KEY_ENTER, 10, 13):
                frame.enter = True
            elif key in (curses.KEY_BACKSPACE, 8, 127):
                frame.backspace = True
            elif key in (ord("h"), ord("H"), ord("l"), ord("L")):
                frame.open_scores = True
            elif key == curses.KEY_RESIZE:
                self._sync_screen_size()
            elif 32 <= key <= 126:
                frame.typed_char = chr(key).upper()

        frame.left_down, frame.right_down, frame.action_down = self.key_poller.poll(
            frame.left_down, frame.right_down, frame.action_down
        )
        return frame

    def _handle_input(self, frame: FrameInput, action_pressed: bool) -> bool:
        if frame.quit:
            return False

        if self.phase == Phase.TITLE:
            if frame.open_scores:
                self.phase = Phase.LEADERBOARD
            elif action_pressed or frame.enter:
                self._start_new_game()
            return True

        if self.phase == Phase.PLAYING:
            return True

        if self.phase == Phase.GAME_OVER:
            if action_pressed or frame.enter:
                self.phase = Phase.TITLE
                self.message = "PRESS SPACE TO START"
                self.message_timer = 999.0
            return True

        if self.phase == Phase.ENTER_NAME:
            if frame.enter and self.name_buffer:
                self._submit_score()
            elif frame.backspace:
                self.name_buffer = self.name_buffer[:-1]
            elif frame.typed_char and len(self.name_buffer) < 3 and frame.typed_char.isalpha():
                self.name_buffer += frame.typed_char
            return True

        if self.phase == Phase.LEADERBOARD and (action_pressed or frame.enter or frame.open_scores):
            self.phase = Phase.TITLE
            return True

        return True

    def _start_new_game(self) -> None:
        self.score = 0
        self.balls = STARTING_BALLS
        self.multiplier = 1
        self.peak_multiplier = 1
        self.jackpots = 0
        self.target_lights = [False, False, False]
        self.flash_timers.clear()
        self.hit_cooldowns.clear()
        self.combo_count = 0
        self.combo_timer = 0.0
        self.bumper_charge_hits = 0
        self.ball_save_timer = 0.0
        self.name_buffer = ""
        self.pending_score = 0
        self.pending_mult = 1
        self.phase = Phase.PLAYING
        self._serve_ball()
        self._show_message("CHARGE PLUNGER", 999.0)

    def _serve_ball(self) -> None:
        self.ball = Ball(self.layout.plunger_x, self.layout.bottom - 2.0, 0.0, 0.0)
        self.ball_trail.clear()
        self.ball_in_launch_lane = True
        self.plunger_charge = 0.0
        self.launch_redirect_done = False
        self.skill_shot_timer = 0.0
        self.skill_shot_ready = False
        self.combo_count = 0
        self.combo_timer = 0.0

    def _launch_ball(self) -> None:
        if self.ball is None:
            return

        charge = clamp(self.plunger_charge, 0.12, 1.0)
        launch_speed = PLUNGER_MIN_SPEED + (PLUNGER_MAX_SPEED - PLUNGER_MIN_SPEED) * charge
        self.ball.vx = 0.0
        self.ball.vy = -launch_speed
        self.ball_in_launch_lane = False
        self.skill_shot_timer = SKILL_SHOT_WINDOW
        self.skill_shot_ready = True
        self.ball_save_timer = BALL_SAVE_TIME
        self._show_message("SKILL SHOT OPEN", 0.9)
        self.plunger_charge = 0.0

    def _submit_score(self) -> None:
        name = self.name_buffer[:3].ljust(3).upper()
        self.leaderboard.add(name=name, score=self.pending_score, mult=self.pending_mult)
        self.phase = Phase.LEADERBOARD

    def _trigger_game_over(self) -> None:
        self.pending_score = self.score
        self.pending_mult = self.peak_multiplier
        if self.leaderboard.qualifies(self.score):
            self.phase = Phase.ENTER_NAME
            self.name_buffer = ""
            return

        self.phase = Phase.GAME_OVER

    def _update_playing(
        self, dt: float, frame: FrameInput, action_pressed: bool, action_released: bool
    ) -> None:
        self._update_flippers(dt, frame)
        self._tick_timers(dt)

        if self.ball is None:
            return

        if self.ball_in_launch_lane:
            self._update_plunger(dt, frame, action_pressed, action_released)
            self.ball_trail.clear()
            return

        self.ball_trail.append((self.ball.ix, self.ball.iy))

        steps = max(1, int((abs(self.ball.vx) + abs(self.ball.vy) + 12.0) / 18.0))
        step_dt = dt / steps
        for _ in range(steps):
            self._step_ball(step_dt)
            if self.ball is None or self.ball_in_launch_lane:
                return

        if self.ball_save_timer > 0:
            self.ball_save_timer = max(0.0, self.ball_save_timer - dt)
        if self.skill_shot_timer > 0:
            self.skill_shot_timer = max(0.0, self.skill_shot_timer - dt)

    def _update_plunger(
        self, dt: float, frame: FrameInput, action_pressed: bool, action_released: bool
    ) -> None:
        if self.ball is None:
            return

        self.ball.x = self.layout.plunger_x
        self.ball.y = self.layout.bottom - 2.0
        self.ball.vx = 0.0
        self.ball.vy = 0.0

        if frame.action_down:
            self.plunger_charge = clamp(self.plunger_charge + dt / PLUNGER_CHARGE_TIME, 0.0, 1.0)
            self._show_message("CHARGE " + str(int(self.plunger_charge * 100)).rjust(3) + "%", 0.2)
            return

        if action_released:
            self._launch_ball()
            return

    def _update_flippers(self, dt: float, frame: FrameInput) -> None:
        self.left_flipper.active = frame.left_down
        self.right_flipper.active = frame.right_down
        self.left_flipper.update(dt)
        self.right_flipper.update(dt)

    def _tick_timers(self, dt: float) -> None:
        self.message_timer = max(0.0, self.message_timer - dt)
        if self.combo_timer > 0:
            self.combo_timer = max(0.0, self.combo_timer - dt)
            if self.combo_timer == 0:
                self.combo_count = 0

        for name in list(self.flash_timers):
            self.flash_timers[name] = max(0.0, self.flash_timers[name] - dt)
            if self.flash_timers[name] == 0:
                del self.flash_timers[name]

        for name in list(self.hit_cooldowns):
            self.hit_cooldowns[name] = max(0.0, self.hit_cooldowns[name] - dt)
            if self.hit_cooldowns[name] == 0:
                del self.hit_cooldowns[name]

    def _step_ball(self, dt: float) -> None:
        if self.ball is None:
            return

        self.ball.vy = clamp(self.ball.vy + BALL_GRAVITY * dt, -BALL_TERMINAL_SPEED, BALL_TERMINAL_SPEED)
        self.ball.x += self.ball.vx * dt
        self.ball.y += self.ball.vy * dt

        self._resolve_segment_collisions()
        self._resolve_circle_collisions()
        self._resolve_flipper_collisions()
        self._handle_triggers()
        self._check_skill_shot_gate()
        self._check_drain()

    def _resolve_segment_collisions(self) -> None:
        if self.ball is None:
            return

        for segment in self.layout.segments:
            qx, qy, _ = nearest_point_on_segment(
                self.ball.x, self.ball.y, segment.x1, segment.y1, segment.x2, segment.y2
            )
            dx = self.ball.x - qx
            dy = self.ball.y - qy
            distance = math.hypot(dx, dy)
            limit = BALL_RADIUS + segment.thickness
            if distance >= limit:
                continue

            if distance <= 1e-6:
                nx, ny = self._segment_normal(segment.x1, segment.y1, segment.x2, segment.y2)
            else:
                nx = dx / distance
                ny = dy / distance

            penetration = limit - distance
            self.ball.x += nx * penetration
            self.ball.y += ny * penetration

            normal_speed = self.ball.vx * nx + self.ball.vy * ny
            if normal_speed < 0:
                self.ball.vx -= (1.75 * normal_speed) * nx
                self.ball.vy -= (1.75 * normal_speed) * ny

            if segment.name in {"left_sling", "right_sling"} and not self._cooldown_active(segment.name):
                self.hit_cooldowns[segment.name] = 0.12
                self.flash_timers[segment.name] = 0.16
                self.ball.vx += -4.5 if segment.name == "right_sling" else 4.5
                self.ball.vy = min(self.ball.vy, -15.0)
                self._add_score(180)
                self._show_message("SLING", 0.45)

    def _resolve_circle_collisions(self) -> None:
        if self.ball is None:
            return

        for circle in self.layout.posts + self.layout.bumpers + [self.layout.reactor] + self.layout.targets:
            dx = self.ball.x - circle.x
            dy = self.ball.y - circle.y
            distance = math.hypot(dx, dy)
            limit = BALL_RADIUS + circle.radius
            if distance >= limit:
                continue

            if distance <= 1e-6:
                nx, ny = 0.0, -1.0
            else:
                nx = dx / distance
                ny = dy / distance

            penetration = limit - distance
            self.ball.x += nx * penetration
            self.ball.y += ny * penetration

            normal_speed = self.ball.vx * nx + self.ball.vy * ny
            if normal_speed < 0:
                bounce = 1.6 if circle.kind in {"bumper", "reactor"} else 1.45
                self.ball.vx -= bounce * normal_speed * nx
                self.ball.vy -= bounce * normal_speed * ny

            if circle.kind == "bumper":
                self.ball.vx += nx * BUMPER_BOOST
                self.ball.vy += ny * BUMPER_BOOST
                self._handle_bumper_hit(circle)
            elif circle.kind == "target":
                self._handle_target_hit(circle)
            elif circle.kind == "reactor":
                self._handle_reactor_hit(circle)

    def _resolve_flipper_collisions(self) -> None:
        if self.ball is None:
            return

        for flipper in (self.left_flipper, self.right_flipper):
            x1, y1, x2, y2 = flipper.endpoints()
            qx, qy, t = nearest_point_on_segment(self.ball.x, self.ball.y, x1, y1, x2, y2)
            dx = self.ball.x - qx
            dy = self.ball.y - qy
            distance = math.hypot(dx, dy)
            limit = BALL_RADIUS + 0.46
            if distance >= limit:
                continue

            if distance <= 1e-6:
                nx, ny = self._segment_normal(x1, y1, x2, y2)
            else:
                nx = dx / distance
                ny = dy / distance
            if ny < -0.15:
                nx, ny = -nx, -ny

            penetration = limit - distance
            self.ball.x += nx * penetration
            self.ball.y += ny * penetration

            normal_speed = self.ball.vx * nx + self.ball.vy * ny
            if normal_speed < 0:
                self.ball.vx -= 1.8 * normal_speed * nx
                self.ball.vy -= 1.8 * normal_speed * ny

            flip_power = max(0.0, flipper.angular_velocity)
            side_push = -1.0 if flipper.side == "right" else 1.0
            if flipper.active and flip_power > 0:
                self.ball.vx += side_push * (8.8 + 11.5 * (1.0 - t))
                self.ball.vy = min(self.ball.vy, -(21.0 + 13.0 * t))
            else:
                self.ball.vx += side_push * 2.7
                self.ball.vy = min(self.ball.vy, -13.0)

    def _handle_bumper_hit(self, circle: CircleObject) -> None:
        if self._cooldown_active(circle.name):
            return

        self.hit_cooldowns[circle.name] = 0.08
        self.flash_timers[circle.name] = 0.16
        self.combo_count = min(5, self.combo_count + 1 if self.combo_timer > 0 else 1)
        self.combo_timer = 1.15
        self.bumper_charge_hits += 1
        points = 90 * self.combo_count
        self._add_score(points)

        if not all(self.target_lights) and self.bumper_charge_hits % 4 == 0:
            self._light_next_target()
            if all(self.target_lights):
                self.flash_timers[self.layout.reactor.name] = 0.7
                self._show_message("REACTOR HOT", 1.1)
            else:
                self._show_message("ION CHARGED", 0.8)
            return

        self._show_message(f"BUMPER x{self.combo_count}", 0.55)

    def _handle_target_hit(self, circle: CircleObject) -> None:
        if self._cooldown_active(circle.name):
            return

        self.hit_cooldowns[circle.name] = 0.18
        self.flash_timers[circle.name] = 0.18

        index = int(circle.label[-1])
        if not self.target_lights[index]:
            self.target_lights[index] = True
            self._add_score(350)
            if all(self.target_lights):
                self._show_message("REACTOR HOT", 1.1)
                self.flash_timers[self.layout.reactor.name] = 0.6
            else:
                self._show_message(f"LIT {circle.label[0]}", 0.75)
            return

        self._add_score(60)

    def _handle_reactor_hit(self, circle: CircleObject) -> None:
        if self._cooldown_active(circle.name):
            return

        self.hit_cooldowns[circle.name] = 0.24
        self.flash_timers[circle.name] = 0.28

        if all(self.target_lights):
            self.target_lights = [False, False, False]
            self.jackpots += 1
            self.multiplier = min(MAX_MULTIPLIER, self.multiplier + 1)
            self.peak_multiplier = max(self.peak_multiplier, self.multiplier)
            self._add_score(2200)
            self._show_message("JACKPOT", 1.2)

            if self.jackpots % 3 == 0 and self.balls < MAX_BALLS:
                self.balls += 1
                self._show_message("EXTRA BALL", 1.3)
            self.ball_save_timer = max(self.ball_save_timer, 3.0)
            return

        self._add_score(180)
        self._show_message("CHARGE ION", 0.7)

    def _handle_triggers(self) -> None:
        if self.ball is None:
            return

        if (
            self.ball.vy < -2.0
            and self.layout.rescue_zone.contains(self.ball.x, self.ball.y)
            and not self._cooldown_active(self.layout.rescue_zone.name)
        ):
            self.hit_cooldowns[self.layout.rescue_zone.name] = 0.8
            self.ball_save_timer = max(self.ball_save_timer, BALL_SAVE_TIME)
            self._add_score(550)
            self._show_message("RESCUE ONLINE", 1.0)

        if (
            self.layout.left_orbit_zone.contains(self.ball.x, self.ball.y)
            and self.ball.vy < 0
            and not self._cooldown_active(self.layout.left_orbit_zone.name)
        ):
            self.hit_cooldowns[self.layout.left_orbit_zone.name] = 0.35
            self.ball_save_timer = max(self.ball_save_timer, 2.0)
            self.ball.vx = max(self.ball.vx, 13.5)
            self._add_score(240)
            lit_index = self._light_next_target() if not all(self.target_lights) else None
            if lit_index is not None and all(self.target_lights):
                self.flash_timers[self.layout.reactor.name] = 0.7
                self._show_message("REACTOR HOT", 1.1)
            elif lit_index is not None:
                self._show_message(f"LIT {self.layout.targets[lit_index].label[0]}", 0.65)
            else:
                self._show_message("LEFT ORBIT", 0.6)

        if (
            self.layout.right_orbit_zone.contains(self.ball.x, self.ball.y)
            and self.ball.vy < 0
            and not self._cooldown_active(self.layout.right_orbit_zone.name)
        ):
            self.hit_cooldowns[self.layout.right_orbit_zone.name] = 0.35
            self.ball.vx = min(self.ball.vx, -13.5)
            self._add_score(240)
            lit_index = self._light_next_target() if not all(self.target_lights) else None
            if lit_index is not None and all(self.target_lights):
                self.flash_timers[self.layout.reactor.name] = 0.7
                self._show_message("REACTOR HOT", 1.1)
            elif lit_index is not None:
                self._show_message(f"LIT {self.layout.targets[lit_index].label[0]}", 0.65)
            else:
                self._show_message("RIGHT ORBIT", 0.6)

        if (
            self.layout.core_lane_zone.contains(self.ball.x, self.ball.y)
            and self.ball.vy < 0
            and not self._cooldown_active(self.layout.core_lane_zone.name)
        ):
            self.hit_cooldowns[self.layout.core_lane_zone.name] = 0.25
            if all(self.target_lights):
                self.ball.x = (self.ball.x * 2.0 + self.layout.reactor.x) / 3.0
                self._handle_reactor_hit(self.layout.reactor)
                return
            self.flash_timers[self.layout.reactor.name] = max(
                self.flash_timers.get(self.layout.reactor.name, 0.0),
                0.18,
            )
            self._add_score(140)
            self._show_message("CORE LINE", 0.45)

    def _check_skill_shot_gate(self) -> None:
        if self.ball is None:
            return
        if self.launch_redirect_done:
            return

        if self.ball.x < self.layout.plunger_left - 0.4:
            return
        if self.ball.y > self.layout.launch_gate_y + 0.5:
            return

        if self.skill_shot_ready:
            self.skill_shot_ready = False
            self._add_score(1500)
            self._light_next_target()
            self._show_message("SKILL SHOT", 1.0)

        self.launch_redirect_done = True
        self.ball.x = min(self.ball.x, self.layout.main_right - 1.4)
        self.ball.vx = -max(16.0, abs(self.ball.vy) * 0.9)
        self.ball.vy = min(self.ball.vy, -14.2)

    def _check_drain(self) -> None:
        if self.ball is None:
            return

        if self.ball.y < self.layout.bottom + 0.8:
            return

        if self.layout.drain_left <= self.ball.x <= self.layout.drain_right or self.ball.y > self.layout.bottom + 2.0:
            if self.ball_save_timer > 0:
                self.ball_save_timer = 0.0
                self._serve_ball()
                self._show_message("BALL SAVED", 1.0)
                return

            self.balls -= 1
            if self.balls > 0:
                self._serve_ball()
                self._show_message("BALL LOST", 1.0)
                return

            self.ball = None
            self._trigger_game_over()

    def _add_score(self, base_points: int) -> None:
        self.score += base_points * self.multiplier

    def _light_next_target(self) -> Optional[int]:
        for index, lit in enumerate(self.target_lights):
            if not lit:
                self.target_lights[index] = True
                self.flash_timers[self.layout.targets[index].name] = 0.35
                return index
        return None

    def _show_message(self, text: str, duration: float = MESSAGE_TIME) -> None:
        self.message = text
        self.message_timer = duration

    def _cooldown_active(self, name: str) -> bool:
        return self.hit_cooldowns.get(name, 0.0) > 0

    def _goal_text(self) -> str:
        if self.phase != Phase.PLAYING:
            return "PRESS SPACE"
        if self.ball_in_launch_lane:
            return "HOLD SPACE AND RELEASE"
        if all(self.target_lights):
            return "GOAL JACKPOT"
        if self.skill_shot_ready and self.skill_shot_timer > 0:
            return "GOAL SKILL SHOT"
        return "GOAL ORBITS > ION > CORE"

    def _ion_bank_text(self) -> str:
        letters = [target.label[0] if lit else "_" for target, lit in zip(self.layout.targets, self.target_lights)]
        return "".join(letters)

    def _save_text(self) -> str:
        if self.phase != Phase.PLAYING:
            return ""
        status = f"BALLS {self.balls}  x{self.multiplier}  ION {self._ion_bank_text()}"
        if self.ball_in_launch_lane:
            return status
        if self.ball_save_timer > 0:
            return f"{status}  SAVE {int(math.ceil(self.ball_save_timer))}"
        return status

    def _render(self) -> None:
        self.screen.erase()
        self._sync_screen_size()

        if self.height < MIN_HEIGHT or self.width < MIN_WIDTH:
            self._draw_resize_warning()
            self._refresh_screen()
            return

        self._draw_hud()
        self._draw_border()
        if self.phase in (Phase.TITLE, Phase.PLAYING, Phase.GAME_OVER, Phase.ENTER_NAME):
            self._draw_playfield()

        if self.phase == Phase.TITLE:
            self._draw_title()
        elif self.phase == Phase.GAME_OVER:
            self._draw_game_over()
        elif self.phase == Phase.ENTER_NAME:
            self._draw_enter_name()
        elif self.phase == Phase.LEADERBOARD:
            self._draw_leaderboard()

        self._refresh_screen()

    def _draw_hud(self) -> None:
        left = f" SCORE {self.score:07d} "
        best = f" BEST {self.leaderboard.best_score():07d} "
        center = self.message if self.message_timer > 0 else self._goal_text()
        right = f" {self._save_text()} "

        hud_attr = self._attr(CP_HUD, curses.A_BOLD)
        best_attr = self._attr(CP_BEST, curses.A_BOLD)
        goal_pair = CP_BEST if self.message_timer > 0 else CP_GOAL
        goal_attr = self._attr(goal_pair, curses.A_BOLD)

        self._safe_addstr(0, 1, left[: max(0, self.width - 2)], hud_attr)
        self._center_text(0, best, best_attr)
        if center:
            self._center_text(1, center, goal_attr)
        self._safe_addstr(0, max(1, self.width - len(right) - 1), right[: max(0, self.width - 2)], hud_attr)

    def _draw_border(self) -> None:
        border_attr = self._attr(CP_BORDER, curses.A_DIM)
        horizontal = "+" + "-" * (self.width - 2) + "+"
        self._safe_addstr(2, 0, horizontal, border_attr)
        for y in range(3, self.height - 1):
            self._safe_addch(y, 0, "|", border_attr)
            self._safe_addch(y, self.width - 1, "|", border_attr)
        self._safe_addstr(self.height - 1, 0, horizontal, border_attr)

    def _draw_playfield(self) -> None:
        rail_attr = self._attr(CP_BORDER, curses.A_DIM)
        for segment in self.layout.segments:
            if segment.name not in VISIBLE_SEGMENT_NAMES:
                continue
            self._draw_segment(segment.x1, segment.y1, segment.x2, segment.y2, self._segment_char(segment), rail_attr)

        self._draw_playfield_art()
        self._draw_static_labels()
        self._draw_targets()
        self._draw_bumpers()
        self._draw_posts()
        self._draw_reactor()
        self._draw_flipper(self.left_flipper)
        self._draw_flipper(self.right_flipper)
        self._draw_ball_and_trail()

    def _draw_playfield_art(self) -> None:
        rail_attr = self._attr(CP_BORDER, curses.A_DIM)
        accent_attr = self._attr(CP_HUD, curses.A_BOLD)
        hot_attr = self._attr(CP_BEST, curses.A_BOLD)
        alert_attr = self._attr(CP_ALERT, curses.A_BOLD)

        center = int(round(self.layout.reactor.x))
        top = int(round(self.layout.top))
        reactor_y = int(round(self.layout.reactor.y))
        main_right = int(round(self.layout.main_right))
        left = int(round(self.layout.left))
        bottom = int(round(self.layout.bottom))
        target_y = int(round(self.layout.targets[1].y))
        bumper_y = int(round(self.layout.bumpers[1].y))

        self._safe_addstr(target_y - 2, center - 13, "/------.---^---.------\\", hot_attr)
        self._safe_addstr(target_y - 1, center - 14, "/      /         \\      \\", rail_attr)
        self._safe_addstr(target_y + 1, center - 12, "\\_____/  .---.  \\_____/", rail_attr)
        self._safe_addstr(reactor_y + 2, center - 8, "<== CORE ==>", accent_attr)
        self._safe_addstr(reactor_y + 5, center - 15, "/\\                    /\\", rail_attr)
        self._safe_addstr(reactor_y + 6, center - 18, "/  \\                /  \\", rail_attr)
        self._safe_addstr(bottom - 4, center - 14, "____/            \\____", rail_attr)
        self._safe_addstr(bottom - 3, center - 6, "\\___ ___/", alert_attr)

        for y in range(top + 2, bumper_y + 7):
            self._safe_addch(y, left + 1, "|", rail_attr)
            self._safe_addch(y, left + 2, "|", rail_attr)
            self._safe_addch(y, main_right - 1, "|", rail_attr)

    def _draw_static_labels(self) -> None:
        lane_attr = self._attr(CP_HUD, curses.A_BOLD)
        save_attr = self._attr(CP_SAVE, curses.A_BOLD)
        self._safe_addstr(int(self.layout.top) + 1, int(self.layout.left) + 2, "RESCUE", save_attr)
        self._safe_addstr(int(self.layout.top) + 1, int(self.layout.plunger_left) - 1, "LAUNCH", lane_attr)
        self._safe_addstr(int(self.layout.top) + 5, int(self.layout.main_right) - 1, "R", lane_attr)
        self._safe_addstr(int(self.layout.launch_gate_y) - 1, int(self.layout.plunger_left) + 1, "SHOT", lane_attr)

        if self.phase == Phase.PLAYING and self.ball_in_launch_lane:
            fill = int(round(self.plunger_charge * 6))
            for index in range(6):
                char = "#" if index < fill else "."
                self._safe_addch(int(self.layout.bottom) - 2 - index, int(self.layout.plunger_right) - 1, char, lane_attr)

        drain_attr = self._attr(CP_ALERT, curses.A_BOLD)
        for x in range(int(self.layout.drain_left), int(self.layout.drain_right) + 1):
            self._safe_addch(int(self.layout.drain_y), x, "V", drain_attr)

    def _draw_targets(self) -> None:
        for index, target in enumerate(self.layout.targets):
            lit = self.target_lights[index]
            flash = self.flash_timers.get(target.name, 0.0) > 0
            attr = self._attr(CP_TARGET_LIT if lit or flash else CP_TARGET, curses.A_BOLD)
            text = f"[{target.label[0]}]" if lit or flash else f"({target.label[0]})"
            self._safe_addstr(int(round(target.y)), int(round(target.x)) - 1, text, attr)

    def _draw_bumpers(self) -> None:
        for bumper in self.layout.bumpers:
            flash = self.flash_timers.get(bumper.name, 0.0) > 0
            attr = self._attr(CP_BEST if flash else CP_BUMPER, curses.A_BOLD)
            self._safe_addstr(int(round(bumper.y)), int(round(bumper.x)) - 1, "{O}", attr)

    def _draw_posts(self) -> None:
        post_attr = self._attr(CP_BORDER)
        for post in self.layout.posts:
            self._safe_addch(int(round(post.y)), int(round(post.x)), "o", post_attr)

    def _draw_reactor(self) -> None:
        hot = all(self.target_lights)
        flash = self.flash_timers.get(self.layout.reactor.name, 0.0) > 0
        pair = CP_REACTOR_HOT if hot or flash else CP_REACTOR
        attr = self._attr(pair, curses.A_BOLD)
        text = "{@}" if hot or flash else "[#]"
        self._safe_addstr(int(round(self.layout.reactor.y)), int(round(self.layout.reactor.x)) - 1, text, attr)
        if hot:
            self._safe_addstr(int(round(self.layout.reactor.y)) + 1, int(round(self.layout.reactor.x)) - 1, "HOT", attr)

    def _draw_flipper(self, flipper: Flipper) -> None:
        attr = self._attr(CP_FLIPPER, curses.A_BOLD)
        pivot_x = int(round(flipper.pivot_x))
        pivot_y = int(round(flipper.pivot_y))

        if flipper.side == "left":
            cells = (
                [
                    (pivot_x, pivot_y, "("),
                    (pivot_x + 1, pivot_y, "="),
                    (pivot_x + 2, pivot_y, "="),
                    (pivot_x + 3, pivot_y, "="),
                    (pivot_x + 4, pivot_y, ">"),
                ]
                if not flipper.active
                else [
                    (pivot_x, pivot_y, "("),
                    (pivot_x + 1, pivot_y - 1, "\\"),
                    (pivot_x + 2, pivot_y - 2, "="),
                    (pivot_x + 3, pivot_y - 2, "="),
                    (pivot_x + 4, pivot_y - 3, ">"),
                ]
            )
        else:
            cells = (
                [
                    (pivot_x, pivot_y, ")"),
                    (pivot_x - 1, pivot_y, "="),
                    (pivot_x - 2, pivot_y, "="),
                    (pivot_x - 3, pivot_y, "="),
                    (pivot_x - 4, pivot_y, "<"),
                ]
                if not flipper.active
                else [
                    (pivot_x, pivot_y, ")"),
                    (pivot_x - 1, pivot_y - 1, "/"),
                    (pivot_x - 2, pivot_y - 2, "="),
                    (pivot_x - 3, pivot_y - 2, "="),
                    (pivot_x - 4, pivot_y - 3, "<"),
                ]
            )

        for x, y, char in cells:
            self._safe_addch(y, x, char, attr)

    def _draw_ball_and_trail(self) -> None:
        trail_points = list(self.ball_trail)[:-1]
        for index, (x, y) in enumerate(trail_points):
            if index < len(trail_points) - 6:
                char = "."
                attr = self._attr(CP_TRAIL, curses.A_DIM)
            elif index < len(trail_points) - 3:
                char = ":"
                attr = self._attr(CP_TRAIL)
            else:
                char = "*"
                attr = self._attr(CP_BEST)
            self._safe_addch(y, x, char, attr)

        if self.ball is None:
            return

        ball_speed = abs(self.ball.vx) + abs(self.ball.vy)
        ball_attr = self._attr(CP_BALL, curses.A_BOLD)
        self._safe_addch(self.ball.iy, self.ball.ix, "@" if ball_speed > 22 else "o", ball_attr)

    def _draw_title(self) -> None:
        title_attr = self._attr(CP_TITLE, curses.A_BOLD)
        info_attr = self._attr(CP_HUD, curses.A_BOLD)
        hot_attr = self._attr(CP_BEST, curses.A_BOLD)

        lines = list(TITLE_LINES)
        lines.append("")
        lines.append("RIGHT SHOT  skill shot")
        lines.append("ORBITS      light ION")
        lines.append("HOT CORE    jackpot + mult")
        lines.append("3 JACKPOTS  extra ball")
        lines.append("")
        lines.append("SPACE  start / launch")
        lines.append("A D    flip     H scores     Q quit")
        lines.append("")

        preview = self.leaderboard.top(3)
        if preview:
            lines.append("TOP PILOTS")
            for index, entry in enumerate(preview):
                lines.append(f"{index + 1:>2}. {entry.name:<3}  {entry.score:>7}  x{entry.mult}")
        else:
            lines.append("No scores yet. Be the first.")

        self._draw_panel("CLI PINBALL", lines, title_attr)
        self._center_text(5, "One screen. One ball. One more run.", hot_attr)
        self._center_text(6, "Shoot right. Light I O N. Hit the core.", info_attr)

    def _draw_game_over(self) -> None:
        next_letter = next((target.label[0] for target, lit in zip(self.layout.targets, self.target_lights) if not lit), None)
        next_goal = "Shoot the core." if next_letter is None else f"Light {next_letter}."
        lines = [
            f"Score:      {self.score}",
            f"Peak mult:  x{self.peak_multiplier}",
            f"Jackpots:   {self.jackpots}",
            f"Ion bank:   {self._ion_bank_text()}",
            f"Next goal:  {next_goal}",
            "",
            "Press SPACE to return to title",
            "Press Q or ESC to quit",
        ]
        self._draw_panel("RUN OVER", lines, self._attr(CP_ALERT, curses.A_BOLD))

    def _draw_enter_name(self) -> None:
        display = (self.name_buffer + "_" * 3)[:3]
        lines = [
            f"Score:      {self.pending_score}",
            f"Peak mult:  x{self.pending_mult}",
            "",
            f"Name: [{display}]",
            "Type 3 letters and press ENTER",
        ]
        self._draw_panel("NEW HIGH SCORE", lines, self._attr(CP_BEST, curses.A_BOLD))

    def _draw_leaderboard(self) -> None:
        entries = self.leaderboard.top(MAX_SCORES)
        if entries:
            lines = [
                f"{index + 1:>2}. {entry.name:<3}  {entry.score:>7}  x{entry.mult}"
                for index, entry in enumerate(entries)
            ]
        else:
            lines = ["No scores yet."]

        lines.append("")
        lines.append("Press SPACE or H to return")
        self._draw_panel("LEADERBOARD", lines, self._attr(CP_LEADERBOARD, curses.A_BOLD))

    def _draw_panel(self, title: str, lines: Sequence[str], attr: int) -> None:
        content_width = max([len(title)] + [len(line) for line in lines] + [20])
        box_width = min(content_width + 4, self.width - 10)
        inner_width = box_width - 2

        rendered_lines = []
        if title:
            rendered_lines.append(title.center(inner_width))
        rendered_lines.extend(line[:inner_width].center(inner_width) for line in lines)

        box_height = len(rendered_lines) + 2
        start_y = max(5, self.height // 2 - box_height // 2)
        start_x = max(5, self.width // 2 - box_width // 2)

        self._safe_addstr(start_y, start_x, "+" + "-" * (box_width - 2) + "+", attr)
        for index, line in enumerate(rendered_lines, start=1):
            self._safe_addstr(start_y + index, start_x, "|" + line[:inner_width].ljust(inner_width) + "|", attr)
        self._safe_addstr(start_y + box_height - 1, start_x, "+" + "-" * (box_width - 2) + "+", attr)

    def _draw_resize_warning(self) -> None:
        warning = f"Terminal too small. Need at least {MIN_WIDTH}x{MIN_HEIGHT}, got {self.width}x{self.height}."
        controls = "Resize the window, or press Q / ESC to quit."
        self._center_text(self.height // 2 - 1, warning, self._attr(CP_ALERT, curses.A_BOLD))
        self._center_text(self.height // 2 + 1, controls, self._attr(CP_HUD, curses.A_BOLD))

    def _draw_segment(self, x1: float, y1: float, x2: float, y2: float, char: str, attr: int) -> None:
        for x, y in self._segment_points(x1, y1, x2, y2):
            self._safe_addch(y, x, char, attr)

    def _segment_points(self, x1: float, y1: float, x2: float, y2: float) -> List[Tuple[int, int]]:
        start_x = int(round(x1))
        start_y = int(round(y1))
        end_x = int(round(x2))
        end_y = int(round(y2))

        points: List[Tuple[int, int]] = []
        dx = abs(end_x - start_x)
        dy = -abs(end_y - start_y)
        sx = 1 if start_x < end_x else -1
        sy = 1 if start_y < end_y else -1
        error = dx + dy
        x = start_x
        y = start_y

        while True:
            if not points or points[-1] != (x, y):
                points.append((x, y))
            if x == end_x and y == end_y:
                break
            e2 = 2 * error
            if e2 >= dy:
                error += dy
                x += sx
            if e2 <= dx:
                error += dx
                y += sy
        return points

    def _segment_char(self, segment: Segment) -> str:
        dx = segment.x2 - segment.x1
        dy = segment.y2 - segment.y1
        if abs(dx) > abs(dy) * 1.6:
            return "-"
        if abs(dy) > abs(dx) * 1.6:
            return "|"
        return "/" if dx * dy < 0 else "\\"

    def _segment_normal(self, x1: float, y1: float, x2: float, y2: float) -> Tuple[float, float]:
        dx = x2 - x1
        dy = y2 - y1
        nx = -dy
        ny = dx
        length = math.hypot(nx, ny)
        if length <= 1e-6:
            return 0.0, -1.0
        nx /= length
        ny /= length
        return nx, ny

    def _center_text(self, y: int, text: str, attr: int = 0) -> None:
        x = max(0, self.width // 2 - len(text) // 2)
        self._safe_addstr(y, x, text, attr)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        if y < 0 or y >= self.height or not text:
            return

        if x < 0:
            text = text[-x:]
            x = 0

        if x >= self.width:
            return

        clipped = text[: self.width - x]
        if not clipped:
            return

        try:
            self.screen.addstr(y, x, clipped, attr)
        except curses.error:
            pass

    def _safe_addch(self, y: int, x: int, char: str, attr: int = 0) -> None:
        if y < 0 or y >= self.height or x < 0 or x >= self.width:
            return

        try:
            self.screen.addch(y, x, char, attr)
        except curses.error:
            pass

    def _refresh_screen(self) -> None:
        try:
            self.screen.refresh()
        except curses.error:
            pass

    def _build_layout(self) -> TableLayout:
        left = 2.0
        top = 3.0
        right = float(self.width - 2)
        bottom = float(self.height - 2)

        plunger_width = 6.0 if self.width >= 72 else 5.0
        plunger_right = right - 1.0
        plunger_left = plunger_right - plunger_width
        main_right = plunger_left - 1.6

        center_x = (left + main_right) / 2.0
        left_pivot = (center_x - 5.8, bottom - 2.3)
        right_pivot = (center_x + 5.8, bottom - 2.3)
        launch_gate_y = top + 9.2

        drain_left = center_x - 1.05
        drain_right = center_x + 1.05
        drain_y = bottom - 0.2

        segments = [
            Segment("left_wall", left, top + 1.0, left, bottom - 6.5),
            Segment("top_wall", left + 7.0, top, main_right - 7.0, top),
            Segment("left_orbit", left + 1.0, top + 6.0, left + 7.0, top + 0.8),
            Segment("right_orbit", main_right - 7.0, top + 0.8, main_right - 1.0, top + 6.0),
            Segment("left_upper_feed", left + 8.0, top + 1.0, center_x - 8.8, top + 6.0),
            Segment("right_upper_feed", center_x + 8.8, top + 6.0, main_right - 8.0, top + 1.0),
            Segment("left_reactor_guide", center_x - 12.0, top + 10.6, center_x - 4.2, top + 13.3),
            Segment("right_reactor_guide", center_x + 4.2, top + 13.3, center_x + 12.0, top + 10.6),
            Segment("main_right_wall", main_right, top + 6.0, main_right, bottom - 6.5),
            Segment("plunger_outer", plunger_right, top, plunger_right, bottom - 1.0),
            Segment("plunger_inner", plunger_left, launch_gate_y, plunger_left, bottom - 2.0),
            Segment("left_lane", left + 0.5, bottom - 1.0, left_pivot[0] - 3.6, bottom - 5.4),
            Segment("left_inlane_guard", drain_left - 0.3, bottom - 0.7, center_x - 4.2, bottom - 6.0),
            Segment("right_lane", main_right - 0.4, bottom - 1.0, right_pivot[0] + 3.6, bottom - 5.4),
            Segment("right_inlane_guard", drain_right + 0.3, bottom - 0.7, center_x + 4.2, bottom - 6.0),
            Segment("left_sling", center_x - 2.0, bottom - 8.2, left_pivot[0] + 2.5, bottom - 5.0),
            Segment("right_sling", center_x + 2.0, bottom - 8.2, right_pivot[0] - 2.5, bottom - 5.0),
        ]

        bumpers = [
            CircleObject("bumper_left", center_x - 9.0, top + 10.2, 1.22, "bumper"),
            CircleObject("bumper_mid", center_x, top + 8.7, 1.22, "bumper"),
            CircleObject("bumper_right", center_x + 9.0, top + 10.2, 1.22, "bumper"),
        ]

        targets = [
            CircleObject("target_0", center_x - 10.0, top + 5.4, 0.98, "target", "I0"),
            CircleObject("target_1", center_x, top + 4.7, 0.98, "target", "O1"),
            CircleObject("target_2", center_x + 10.0, top + 5.4, 0.98, "target", "N2"),
        ]

        posts = [
            CircleObject("post_left_outer", left_pivot[0] - 1.7, bottom - 4.8, 0.5, "post"),
            CircleObject("post_left_inner", center_x - 3.0, bottom - 6.2, 0.5, "post"),
            CircleObject("post_right_inner", center_x + 3.0, bottom - 6.2, 0.5, "post"),
            CircleObject("post_right_outer", right_pivot[0] + 1.7, bottom - 4.8, 0.5, "post"),
            CircleObject("post_upper_left", center_x - 6.0, top + 12.2, 0.42, "post"),
            CircleObject("post_upper_right", center_x + 6.0, top + 12.2, 0.42, "post"),
            CircleObject("post_orbit_left", center_x - 12.6, top + 8.8, 0.42, "post"),
            CircleObject("post_orbit_right", center_x + 12.6, top + 8.8, 0.42, "post"),
        ]

        reactor = CircleObject("reactor", center_x, top + 12.3, 1.46, "reactor")

        rescue_zone = TriggerZone("rescue_lane", left - 0.1, top + 0.8, left + 2.8, top + 5.4)
        skill_zone = TriggerZone(
            "skill_gate",
            plunger_left - 0.2,
            launch_gate_y - 2.2,
            plunger_right + 0.2,
            launch_gate_y + 0.6,
        )
        left_orbit_zone = TriggerZone("left_orbit", left + 0.8, top + 2.0, left + 6.8, top + 9.0)
        right_orbit_zone = TriggerZone("right_orbit", main_right - 6.0, top + 2.0, main_right - 0.6, top + 11.5)
        core_lane_zone = TriggerZone("core_lane", center_x - 2.3, top + 9.0, center_x + 2.3, top + 15.0)

        return TableLayout(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            main_right=main_right,
            plunger_left=plunger_left,
            plunger_right=plunger_right,
            plunger_x=(plunger_left + plunger_right) / 2.0,
            launch_gate_y=launch_gate_y,
            left_flipper_pivot=left_pivot,
            right_flipper_pivot=right_pivot,
            drain_left=drain_left,
            drain_right=drain_right,
            drain_y=drain_y,
            segments=segments,
            bumpers=bumpers,
            targets=targets,
            posts=posts,
            reactor=reactor,
            rescue_zone=rescue_zone,
            skill_zone=skill_zone,
            left_orbit_zone=left_orbit_zone,
            right_orbit_zone=right_orbit_zone,
            core_lane_zone=core_lane_zone,
        )


def main(screen: "curses._CursesWindow") -> None:
    game = Game(screen)
    game.run()


if __name__ == "__main__":
    curses.wrapper(main)
