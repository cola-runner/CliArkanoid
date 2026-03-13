from __future__ import annotations

import curses
import json
import os
import random
import time
import ctypes
from collections import deque
from dataclasses import dataclass
from enum import Enum
from math import copysign
from typing import Deque, List, Optional, Sequence, Tuple


FPS = 60
FRAME_TIME = 1.0 / FPS

MIN_HEIGHT = 24
MIN_WIDTH = 60

BALL_SPEED_BASE = 22.0
MAX_VX_RATIO = 1.5
MIN_VERTICAL_SPEED = 8.0
WAVE_SPEED_MULTIPLIER = 1.15

PADDLE_WIDTH = 10
PADDLE_MAX_WIDTH = 24
PADDLE_SPEED = 48.0
INPUT_STICKY_TIME = 0.09

BRICK_WIDTH = 6
BRICK_ROWS = 5
BRICK_TOP = 3
BRICK_SPRITE = "[###]"

POWERUP_SPEED = 8.0
POWERUP_DROP_CHANCE = 0.2
POWERUP_TYPES = ("E", "+", "S")

STARTING_LIVES = 3
MAX_LIVES = 5
MAX_SCORES = 10
BALL_TRAIL_LENGTH = 4

COUNTDOWN_LABELS = ("3", "2", "1", "GO!")
COUNTDOWN_DURATIONS = (0.7, 0.7, 0.7, 0.6)

SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scores.json")

TITLE_ART = [
    "   ___   ____  _  __   _    _   _  ___  ___  ____ ",
    "  / _ | / __/ / |/ /  / |  / | / |/ _ \\ / _ \\/  _/",
    " / __ |/ _/  /    /  /  | /  |/ / /_/ / /_/ // /  ",
    "/_/ |_/_/   /_/|_/  /_/|_/_/|___/\\____/\\____/___/ ",
]


CP_BORDER = 1
CP_HUD = 2
CP_HUD_BEST = 3
CP_BRICK_0 = 4
CP_BRICK_1 = 5
CP_BRICK_2 = 6
CP_BRICK_3 = 7
CP_BRICK_4 = 8
CP_PADDLE = 9
CP_BALL = 10
CP_TRAIL = 11
CP_PU_E = 12
CP_PU_PLUS = 13
CP_PU_S = 14
CP_COUNTDOWN = 15
CP_TITLE = 16
CP_GAMEOVER = 17
CP_LEADERBOARD = 18

BRICK_COLOR_PAIRS = (CP_BRICK_0, CP_BRICK_1, CP_BRICK_2, CP_BRICK_3, CP_BRICK_4)

VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_A = 0x41
VK_D = 0x44


class GameState(str, Enum):
    TITLE = "title"
    COUNTDOWN = "countdown"
    PLAYING = "playing"
    GAME_OVER = "game_over"
    ENTER_NAME = "enter_name"
    LEADERBOARD = "leaderboard"


@dataclass
class ScoreEntry:
    name: str
    score: int
    wave: int

    @classmethod
    def from_dict(cls, data: object) -> Optional["ScoreEntry"]:
        if not isinstance(data, dict):
            return None

        try:
            score = int(data.get("score", 0))
            wave = int(data.get("wave", 1))
        except (TypeError, ValueError):
            return None

        raw_name = str(data.get("name", "???")).upper()
        name = raw_name[:3].ljust(3)
        return cls(name=name, score=max(0, score), wave=max(1, wave))

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "wave": self.wave}


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
                raw_data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(raw_data, list):
            return []

        entries = []
        for item in raw_data:
            entry = ScoreEntry.from_dict(item)
            if entry is not None:
                entries.append(entry)

        entries.sort(key=lambda entry: (entry.score, entry.wave), reverse=True)
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

    def add(self, name: str, score: int, wave: int) -> None:
        entry = ScoreEntry(name=name[:3].ljust(3).upper(), score=max(0, score), wave=max(1, wave))
        self.entries.append(entry)
        self.entries.sort(key=lambda item: (item.score, item.wave), reverse=True)
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

    @classmethod
    def launched(cls, x: float, y: float, speed: float) -> "Ball":
        angle = random.uniform(-0.4, 0.4)
        return cls(x=float(x), y=float(y), vx=speed * angle, vy=-speed)

    @classmethod
    def stationary(cls, x: float, y: float) -> "Ball":
        return cls(x=float(x), y=float(y), vx=0.0, vy=0.0)

    @property
    def ix(self) -> int:
        return int(round(self.x))

    @property
    def iy(self) -> int:
        return int(round(self.y))


@dataclass
class Paddle:
    x: float
    y: int
    width: int
    direction: int = 0


@dataclass
class Brick:
    x: int
    y: int
    row: int
    alive: bool = True


@dataclass
class PowerUp:
    x: float
    y: float
    kind: str
    alive: bool = True

    @classmethod
    def spawn(cls, x: float, y: float) -> "PowerUp":
        return cls(x=float(x), y=float(y), kind=random.choice(POWERUP_TYPES))


@dataclass
class FrameInput:
    left: bool = False
    right: bool = False
    direction: int = 0
    action: bool = False
    quit: bool = False
    enter: bool = False
    backspace: bool = False
    typed_char: Optional[str] = None


class DirectionPoller:
    """Poll physical key state on Windows to avoid terminal key-repeat delay."""

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

    def get_direction(self) -> int:
        left_pressed = self._is_pressed(VK_LEFT, VK_A)
        right_pressed = self._is_pressed(VK_RIGHT, VK_D)

        if left_pressed == right_pressed:
            return 0
        return -1 if left_pressed else 1


class Game:
    def __init__(self, screen: "curses._CursesWindow") -> None:
        self.screen = screen
        self.height, self.width = self.screen.getmaxyx()
        self.colors_enabled = False
        self.direction_poller = DirectionPoller()

        self.leaderboard = Leaderboard(SCORES_FILE)
        self.phase = GameState.TITLE

        self.score = 0
        self.wave = 1
        self.lives = STARTING_LIVES
        self.ball_speed = BALL_SPEED_BASE
        self.last_direction_press_at = 0.0

        self.countdown_phase = 0
        self.countdown_timer = 0.0

        self.pending_score = 0
        self.pending_wave = 1
        self.name_buffer = ""

        self.ball_trail: Deque[Tuple[int, int]] = deque(maxlen=BALL_TRAIL_LENGTH)
        self.paddle = Paddle(x=1.0, y=1, width=PADDLE_WIDTH)
        self.ball = Ball.stationary(1.0, 1.0)
        self.bricks: List[Brick] = []
        self.powerups: List[PowerUp] = []

        self._configure_curses()
        self._setup_wave(reset_bricks=True)
        self.phase = GameState.TITLE

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
        curses.init_pair(CP_HUD_BEST, curses.COLOR_YELLOW, -1)
        curses.init_pair(CP_BRICK_0, curses.COLOR_RED, -1)
        curses.init_pair(CP_BRICK_1, curses.COLOR_YELLOW, -1)
        curses.init_pair(CP_BRICK_2, curses.COLOR_GREEN, -1)
        curses.init_pair(CP_BRICK_3, curses.COLOR_CYAN, -1)
        curses.init_pair(CP_BRICK_4, curses.COLOR_MAGENTA, -1)
        curses.init_pair(CP_PADDLE, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_BALL, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_TRAIL, curses.COLOR_WHITE, -1)
        curses.init_pair(CP_PU_E, curses.COLOR_GREEN, -1)
        curses.init_pair(CP_PU_PLUS, curses.COLOR_YELLOW, -1)
        curses.init_pair(CP_PU_S, curses.COLOR_BLUE, -1)
        curses.init_pair(CP_COUNTDOWN, curses.COLOR_YELLOW, -1)
        curses.init_pair(CP_TITLE, curses.COLOR_CYAN, -1)
        curses.init_pair(CP_GAMEOVER, curses.COLOR_RED, -1)
        curses.init_pair(CP_LEADERBOARD, curses.COLOR_CYAN, -1)

    def _attr(self, pair_id: int, *flags: int) -> int:
        attr = curses.color_pair(pair_id) if self.colors_enabled else 0
        for flag in flags:
            attr |= flag
        return attr

    def _sync_screen_size(self) -> None:
        self.height, self.width = self.screen.getmaxyx()

    def run(self) -> None:
        last_frame = time.perf_counter()

        while True:
            now = time.perf_counter()
            dt = min(now - last_frame, 0.05)
            last_frame = now

            self._sync_screen_size()
            frame_input = self._poll_input()
            if not self._handle_input(frame_input, now):
                break

            if self.height >= MIN_HEIGHT and self.width >= MIN_WIDTH:
                if self.phase == GameState.COUNTDOWN:
                    self._update_countdown(dt)
                elif self.phase == GameState.PLAYING:
                    self._update_playing(dt)

            self._render()

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
                frame.left = True
                frame.direction = -1
            elif key in (curses.KEY_RIGHT, ord("d"), ord("D")):
                frame.right = True
                frame.direction = 1
            elif key == ord(" "):
                frame.action = True
            elif key in (curses.KEY_ENTER, 10, 13):
                frame.enter = True
            elif key in (curses.KEY_BACKSPACE, 8, 127):
                frame.backspace = True
            elif key == curses.KEY_RESIZE:
                self._sync_screen_size()
            elif 32 <= key <= 126:
                frame.typed_char = chr(key).upper()

        return frame

    def _handle_input(self, frame: FrameInput, now: float) -> bool:
        if frame.quit:
            return False

        if self.phase == GameState.TITLE:
            if frame.action or frame.enter:
                self._start_new_game()
            return True

        if self.phase in (GameState.COUNTDOWN, GameState.PLAYING):
            self._update_paddle_direction(frame, now)
            return True

        if self.phase == GameState.GAME_OVER:
            if frame.action or frame.enter:
                self._start_new_game()
            return True

        if self.phase == GameState.ENTER_NAME:
            if frame.enter and self.name_buffer:
                self._submit_score()
            elif frame.backspace:
                self.name_buffer = self.name_buffer[:-1]
            elif frame.typed_char and len(self.name_buffer) < 3 and frame.typed_char.isalpha():
                self.name_buffer += frame.typed_char
            return True

        if self.phase == GameState.LEADERBOARD and (frame.action or frame.enter):
            self.phase = GameState.TITLE

        return True

    def _update_paddle_direction(self, frame: FrameInput, now: float) -> None:
        physical_direction = self.direction_poller.get_direction()
        if physical_direction != 0:
            self.paddle.direction = physical_direction
            self.last_direction_press_at = now
            return

        if frame.direction != 0:
            self.paddle.direction = frame.direction
            self.last_direction_press_at = now
            return

        if now - self.last_direction_press_at > INPUT_STICKY_TIME:
            self.paddle.direction = 0

    def _start_new_game(self) -> None:
        self.score = 0
        self.wave = 1
        self.lives = STARTING_LIVES
        self.ball_speed = BALL_SPEED_BASE
        self.last_direction_press_at = 0.0
        self.pending_score = 0
        self.pending_wave = 1
        self.name_buffer = ""

        self._setup_wave(reset_bricks=True)
        self._start_countdown()

    def _setup_wave(self, reset_bricks: bool) -> None:
        self._spawn_paddle_and_ball()
        self.powerups = []
        self.ball_trail.clear()

        if reset_bricks:
            self.bricks = self._build_bricks()

    def _spawn_paddle_and_ball(self) -> None:
        paddle_x = max(1.0, float(self.width // 2 - PADDLE_WIDTH // 2))
        paddle_y = max(3, self.height - 3)
        self.paddle = Paddle(x=paddle_x, y=paddle_y, width=PADDLE_WIDTH)
        self.ball = Ball.stationary(self.paddle.x + self.paddle.width / 2.0, self.paddle.y - 1)

    def _build_bricks(self) -> List[Brick]:
        brick_columns = max(4, (self.width - 4) // BRICK_WIDTH)
        total_width = brick_columns * BRICK_WIDTH
        start_x = max(1, (self.width - total_width) // 2)

        return [
            Brick(x=start_x + column * BRICK_WIDTH, y=BRICK_TOP + row, row=row)
            for row in range(BRICK_ROWS)
            for column in range(brick_columns)
        ]

    def _start_countdown(self) -> None:
        self.phase = GameState.COUNTDOWN
        self.countdown_phase = 0
        self.countdown_timer = 0.0
        self._pin_ball_to_paddle()

    def _pin_ball_to_paddle(self) -> None:
        self.ball.x = self.paddle.x + self.paddle.width / 2.0
        self.ball.y = float(self.paddle.y - 1)
        self.ball.vx = 0.0
        self.ball.vy = 0.0

    def _submit_score(self) -> None:
        name = self.name_buffer[:3].ljust(3).upper()
        self.leaderboard.add(name=name, score=self.pending_score, wave=self.pending_wave)
        self.phase = GameState.LEADERBOARD

    def _update_countdown(self, dt: float) -> None:
        self._move_paddle(dt)
        self._pin_ball_to_paddle()

        self.countdown_timer += dt
        if self.countdown_timer < COUNTDOWN_DURATIONS[self.countdown_phase]:
            return

        self.countdown_timer = 0.0
        self.countdown_phase += 1
        if self.countdown_phase < len(COUNTDOWN_LABELS):
            return

        launch_x = self.paddle.x + self.paddle.width / 2.0
        launch_y = self.paddle.y - 1
        self.ball = Ball.launched(launch_x, launch_y, self.ball_speed)
        self.phase = GameState.PLAYING

    def _move_paddle(self, dt: float) -> None:
        self.paddle.x += self.paddle.direction * PADDLE_SPEED * dt

        max_x = max(1.0, self.width - self.paddle.width - 1.0)
        self.paddle.x = max(1.0, min(max_x, self.paddle.x))

    def _update_playing(self, dt: float) -> None:
        self._move_paddle(dt)
        self.ball_trail.append((self.ball.ix, self.ball.iy))

        previous_y = self.ball.y

        self.ball.x += self.ball.vx * dt
        self.ball.y += self.ball.vy * dt

        self._limit_ball_velocity()
        self._bounce_off_walls()
        self._bounce_off_paddle(previous_y)
        self._handle_brick_hits(previous_y)
        self._update_powerups(dt)

        if self.ball.y >= self.height - 1:
            self._lose_life()
            return

        if all(not brick.alive for brick in self.bricks):
            self._advance_wave()

    def _limit_ball_velocity(self) -> None:
        limit = self.ball_speed * MAX_VX_RATIO
        self.ball.vx = max(-limit, min(limit, self.ball.vx))

        if 0.0 < abs(self.ball.vy) < MIN_VERTICAL_SPEED:
            self.ball.vy = copysign(MIN_VERTICAL_SPEED, self.ball.vy)

    def _bounce_off_walls(self) -> None:
        if self.ball.x < 1:
            self.ball.x = 1.0
            self.ball.vx = abs(self.ball.vx)
        elif self.ball.x > self.width - 2:
            self.ball.x = float(self.width - 2)
            self.ball.vx = -abs(self.ball.vx)

        if self.ball.y < 2:
            self.ball.y = 2.0
            self.ball.vy = abs(self.ball.vy)

    def _bounce_off_paddle(self, previous_y: float) -> None:
        paddle_left = int(self.paddle.x)
        paddle_right = paddle_left + self.paddle.width
        crossed_paddle = previous_y <= self.paddle.y - 1 <= self.ball.y

        if not (self.ball.vy > 0 and crossed_paddle):
            return
        if not (paddle_left <= self.ball.ix < paddle_right):
            return

        self.ball.y = float(self.paddle.y - 1)
        self.ball.vy = -abs(self.ball.vy)

        relative = (self.ball.x - self.paddle.x) / max(1, self.paddle.width)
        relative = max(0.0, min(1.0, relative))
        edge_bias = (relative - 0.5) * 2.0
        self.ball.vx = self.ball_speed * edge_bias * 1.2

    def _handle_brick_hits(self, previous_y: float) -> None:
        for brick in self.bricks:
            if not brick.alive:
                continue

            brick_right = brick.x + BRICK_WIDTH - 1
            in_column = brick.x <= self.ball.ix <= brick_right
            crossed_row = min(previous_y, self.ball.y) <= brick.y <= max(previous_y, self.ball.y)

            if not (in_column and crossed_row):
                continue

            brick.alive = False
            self.ball.vy *= -1
            self.score += 10 * self.wave

            if random.random() < POWERUP_DROP_CHANCE:
                center_x = brick.x + BRICK_WIDTH / 2.0
                self.powerups.append(PowerUp.spawn(center_x, brick.y))
            break

    def _update_powerups(self, dt: float) -> None:
        for powerup in self.powerups:
            powerup.y += POWERUP_SPEED * dt

            caught = (
                int(powerup.y) == self.paddle.y
                and int(self.paddle.x) <= int(powerup.x) < int(self.paddle.x) + self.paddle.width
            )
            if not caught:
                continue

            powerup.alive = False
            self._apply_powerup(powerup.kind)

        self.powerups = [powerup for powerup in self.powerups if powerup.alive and powerup.y < self.height - 1]

    def _apply_powerup(self, kind: str) -> None:
        if kind == "E":
            self.paddle.width = min(PADDLE_MAX_WIDTH, self.paddle.width + 4)
            max_x = max(1.0, self.width - self.paddle.width - 1.0)
            self.paddle.x = min(self.paddle.x, max_x)
            return

        if kind == "+":
            self.lives = min(MAX_LIVES, self.lives + 1)
            return

        if kind == "S":
            self.ball.vx *= 0.75
            self.ball.vy *= 0.75
            self._limit_ball_velocity()

    def _lose_life(self) -> None:
        self.lives -= 1
        self.powerups = []
        self.ball_trail.clear()

        if self.lives > 0:
            self._setup_wave(reset_bricks=False)
            self._start_countdown()
            return

        self._trigger_game_over()

    def _advance_wave(self) -> None:
        self.wave += 1
        self.ball_speed *= WAVE_SPEED_MULTIPLIER
        self._setup_wave(reset_bricks=True)
        self._start_countdown()

    def _trigger_game_over(self) -> None:
        self.pending_score = self.score
        self.pending_wave = self.wave

        if self.leaderboard.qualifies(self.score):
            self.phase = GameState.ENTER_NAME
            self.name_buffer = ""
            return

        self.phase = GameState.GAME_OVER

    def _render(self) -> None:
        self.screen.erase()
        self._sync_screen_size()

        if self.height < MIN_HEIGHT or self.width < MIN_WIDTH:
            self._draw_resize_warning()
            self._refresh_screen()
            return

        self._draw_hud()
        self._draw_border()

        if self.phase in (GameState.PLAYING, GameState.COUNTDOWN, GameState.GAME_OVER, GameState.ENTER_NAME):
            self._draw_playfield()

        if self.phase == GameState.TITLE:
            self._draw_title()
        elif self.phase == GameState.COUNTDOWN:
            self._draw_countdown()
        elif self.phase == GameState.GAME_OVER:
            self._draw_game_over()
        elif self.phase == GameState.ENTER_NAME:
            self._draw_enter_name()
        elif self.phase == GameState.LEADERBOARD:
            self._draw_leaderboard()

        self._refresh_screen()

    def _refresh_screen(self) -> None:
        try:
            self.screen.refresh()
        except curses.error:
            pass

    def _draw_resize_warning(self) -> None:
        warning = f"Terminal too small. Need at least {MIN_WIDTH}x{MIN_HEIGHT}, got {self.width}x{self.height}."
        controls = "Resize the window, or press Q / ESC to quit."
        self._center_text(self.height // 2 - 1, warning, self._attr(CP_GAMEOVER, curses.A_BOLD))
        self._center_text(self.height // 2 + 1, controls, self._attr(CP_HUD, curses.A_BOLD))

    def _draw_hud(self) -> None:
        left = f" SCORE: {self.score} "
        center = f" BEST: {self.leaderboard.best_score()} "
        right = f" WAVE: {self.wave}  LIVES: {self.lives} "

        hud_attr = self._attr(CP_HUD, curses.A_BOLD)
        best_attr = self._attr(CP_HUD_BEST, curses.A_BOLD)

        self._safe_addstr(0, 1, left[: max(0, self.width - 2)], hud_attr)
        self._center_text(0, center, best_attr)
        self._safe_addstr(0, max(1, self.width - len(right) - 1), right[: max(0, self.width - 2)], hud_attr)

    def _draw_border(self) -> None:
        border_attr = self._attr(CP_BORDER, curses.A_DIM)
        horizontal = "+" + "-" * (self.width - 2) + "+"

        self._safe_addstr(1, 0, horizontal, border_attr)
        for y in range(2, self.height - 1):
            self._safe_addch(y, 0, "|", border_attr)
            self._safe_addch(y, self.width - 1, "|", border_attr)
        self._safe_addstr(self.height - 1, 0, horizontal, border_attr)

    def _draw_playfield(self) -> None:
        for brick in self.bricks:
            if not brick.alive:
                continue
            brick_attr = self._attr(BRICK_COLOR_PAIRS[brick.row % len(BRICK_COLOR_PAIRS)], curses.A_BOLD)
            self._safe_addstr(brick.y, brick.x, BRICK_SPRITE, brick_attr)

        for powerup in self.powerups:
            powerup_attr = self._powerup_attr(powerup.kind)
            self._safe_addch(int(powerup.y), int(powerup.x), powerup.kind, powerup_attr)

        trail_attr = self._attr(CP_TRAIL, curses.A_DIM)
        for trail_x, trail_y in list(self.ball_trail)[:-1]:
            self._safe_addch(trail_y, trail_x, ".", trail_attr)

        paddle_attr = self._attr(CP_PADDLE, curses.A_BOLD)
        self._safe_addstr(self.paddle.y, int(self.paddle.x), "=" * self.paddle.width, paddle_attr)

        ball_attr = self._attr(CP_BALL, curses.A_BOLD)
        self._safe_addch(self.ball.iy, self.ball.ix, "O", ball_attr)

    def _powerup_attr(self, kind: str) -> int:
        if kind == "E":
            return self._attr(CP_PU_E, curses.A_BOLD, curses.A_BLINK)
        if kind == "+":
            return self._attr(CP_PU_PLUS, curses.A_BOLD, curses.A_BLINK)
        return self._attr(CP_PU_S, curses.A_BOLD, curses.A_BLINK)

    def _draw_countdown(self) -> None:
        label = COUNTDOWN_LABELS[min(self.countdown_phase, len(COUNTDOWN_LABELS) - 1)]
        self._draw_panel("", [label], self._attr(CP_COUNTDOWN, curses.A_BOLD))

    def _draw_game_over(self) -> None:
        lines = [
            f"Score: {self.score}",
            f"Wave:  {self.wave}",
            "",
            "Press SPACE to play again",
            "Press Q or ESC to quit",
        ]
        self._draw_panel("GAME OVER", lines, self._attr(CP_GAMEOVER, curses.A_BOLD))

    def _draw_enter_name(self) -> None:
        display = (self.name_buffer + "_" * 3)[:3]
        lines = [
            f"Score: {self.pending_score}",
            f"Wave:  {self.pending_wave}",
            "",
            f"Name: [{display}]",
            "Type 3 letters and press ENTER",
        ]
        self._draw_panel("NEW HIGH SCORE", lines, self._attr(CP_COUNTDOWN, curses.A_BOLD))

    def _draw_leaderboard(self) -> None:
        entries = self.leaderboard.top(MAX_SCORES)
        if entries:
            lines = [
                f"{index + 1:>2}. {entry.name:<3}  {entry.score:>6}  W{entry.wave}"
                for index, entry in enumerate(entries)
            ]
        else:
            lines = ["No scores yet."]

        lines.append("")
        lines.append("Press SPACE to return to the title screen")
        self._draw_panel("LEADERBOARD", lines, self._attr(CP_LEADERBOARD, curses.A_BOLD))

    def _draw_title(self) -> None:
        title_attr = self._attr(CP_TITLE, curses.A_BOLD)
        info_attr = self._attr(CP_HUD, curses.A_BOLD)
        highlight_attr = self._attr(CP_HUD_BEST, curses.A_BOLD)

        art_y = 3
        for index, line in enumerate(TITLE_ART):
            self._center_text(art_y + index, line, title_attr)

        self._center_text(art_y + len(TITLE_ART) + 1, "Terminal brick breaker with waves, power-ups, and local high scores.", info_attr)
        self._center_text(art_y + len(TITLE_ART) + 2, "Clear every brick and keep the ball alive.", info_attr)

        scores_y = art_y + len(TITLE_ART) + 4
        self._center_text(scores_y, "Top Scores", highlight_attr)

        preview = self.leaderboard.top(5)
        if preview:
            for index, entry in enumerate(preview):
                line = f"{index + 1}. {entry.name:<3}  {entry.score:>6}  W{entry.wave}"
                self._center_text(scores_y + 1 + index, line, info_attr)
        else:
            self._center_text(scores_y + 1, "No scores yet.", info_attr)

        controls_y = scores_y + 7
        self._center_text(controls_y, "SPACE or ENTER: Start", highlight_attr)
        self._center_text(controls_y + 1, "Left / Right or A / D: Move paddle", info_attr)
        self._center_text(controls_y + 2, "Power-ups: E = expand, + = extra life, S = slow ball", info_attr)
        self._center_text(controls_y + 3, "Q or ESC: Quit", info_attr)

    def _draw_panel(self, title: str, lines: Sequence[str], attr: int) -> None:
        content_width = max([len(title)] + [len(line) for line in lines] + [18])
        box_width = min(content_width + 4, self.width - 4)
        inner_width = box_width - 2

        rendered_lines = []
        if title:
            rendered_lines.append(title.center(inner_width))
        rendered_lines.extend(line[:inner_width].center(inner_width) for line in lines)

        box_height = len(rendered_lines) + 2
        start_y = max(3, self.height // 2 - box_height // 2)
        start_x = max(2, self.width // 2 - box_width // 2)

        self._safe_addstr(start_y, start_x, "+" + "-" * (box_width - 2) + "+", attr)
        for index, line in enumerate(rendered_lines, start=1):
            self._safe_addstr(start_y + index, start_x, "|" + line[:inner_width].ljust(inner_width) + "|", attr)
        self._safe_addstr(start_y + box_height - 1, start_x, "+" + "-" * (box_width - 2) + "+", attr)

    def _center_text(self, y: int, text: str, attr: int = 0) -> None:
        x = max(0, self.width // 2 - len(text) // 2)
        self._safe_addstr(y, x, text, attr)

    def _safe_addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        if y < 0 or y >= self.height:
            return
        if not text:
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


def main(screen: "curses._CursesWindow") -> None:
    game = Game(screen)
    game.run()


if __name__ == "__main__":
    curses.wrapper(main)
