import curses
import time
import random
import json
import os
from math import copysign
from collections import deque

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FPS            = 60
FRAME_TIME     = 1.0 / FPS

BALL_SPEED_BASE = 22   # cells/second (initial)
MAX_VX_RATIO    = 1.5  # max |vx| relative to current ball_speed

PADDLE_WIDTH      = 10
PADDLE_SPEED_BASE = 20   # cells/s initial
PADDLE_SPEED_MAX  = 65   # cells/s max (reached after 0.5s hold)
PADDLE_ACCEL_TIME = 0.5  # seconds to reach max speed

BRICK_W    = 6    # chars per brick (▐████▌ = 6 chars)
BRICK_ROWS = 5

POWERUP_SPEED = 8  # cells/s

SCORES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scores.json')
MAX_SCORES  = 10

# curses color-pair IDs
CP_BORDER    = 1
CP_HUD       = 2
CP_HUD_BEST  = 3
CP_BRICK_0   = 4   # RED
CP_BRICK_1   = 5   # YELLOW
CP_BRICK_2   = 6   # GREEN
CP_BRICK_3   = 7   # CYAN
CP_BRICK_4   = 8   # MAGENTA
CP_PADDLE    = 9
CP_BALL      = 10
CP_TRAIL     = 11
CP_PU_E      = 12  # GREEN blink
CP_PU_PLUS   = 13  # YELLOW blink
CP_PU_S      = 14  # BLUE blink
CP_COUNTDOWN = 15
CP_TITLE     = 16
CP_GAMEOVER  = 17
CP_LEADERBD  = 18

CP_BRICK = [CP_BRICK_0, CP_BRICK_1, CP_BRICK_2, CP_BRICK_3, CP_BRICK_4]

TITLE_ART = [
    " ██████╗██╗     ██╗     ",
    "██╔════╝██║     ██║     ",
    "██║     ██║     ██║     ",
    "██║     ██║     ██║     ",
    "╚██████╗███████╗██║     ",
    " ╚═════╝╚══════╝╚═╝     ",
]
TITLE_ART2 = [
    "  █████╗ ██████╗ ██╗  ██╗ █████╗ ███╗  ██╗ ██████╗ ██╗██████╗  ",
    " ██╔══██╗██╔══██╗██║ ██╔╝██╔══██╗████╗ ██║██╔═══██╗██║██╔══██╗ ",
    " ███████║██████╔╝█████╔╝ ███████║██╔██╗██║██║   ██║██║██║  ██║ ",
    " ██╔══██║██╔══██╗██╔═██╗ ██╔══██║██║╚████║██║   ██║██║██║  ██║ ",
    " ██║  ██║██║  ██║██║  ██╗██║  ██║██║ ╚███║╚██████╔╝██║██████╔╝ ",
    " ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚══╝ ╚═════╝ ╚═╝╚═════╝  ",
]

# ---------------------------------------------------------------------------
# Leaderboard helpers
# ---------------------------------------------------------------------------
def load_scores():
    try:
        with open(SCORES_FILE, 'r') as f:
            data = json.load(f)
        # validate
        return [e for e in data if 'name' in e and 'score' in e and 'wave' in e]
    except Exception:
        return []

def save_scores(scores):
    try:
        with open(SCORES_FILE, 'w') as f:
            json.dump(scores, f, indent=2)
    except Exception:
        pass

def qualifies(scores, score):
    if len(scores) < MAX_SCORES:
        return True
    return score > scores[-1]['score']

def insert_score(scores, name, score, wave):
    scores.append({'name': name, 'score': score, 'wave': wave})
    scores.sort(key=lambda e: e['score'], reverse=True)
    return scores[:MAX_SCORES]

# ---------------------------------------------------------------------------
# Game objects
# ---------------------------------------------------------------------------
class Ball:
    def __init__(self, x, y, speed):
        self.x  = float(x)
        self.y  = float(y)
        angle   = random.uniform(-0.4, 0.4)   # slight random angle
        self.vx = speed * angle
        self.vy = -speed

    @property
    def ix(self): return int(round(self.x))
    @property
    def iy(self): return int(round(self.y))


class Paddle:
    def __init__(self, x, y, width):
        self.x     = float(x)
        self.y     = y
        self.width = width
        self.dir   = 0   # -1 left | 0 still | 1 right


class Brick:
    def __init__(self, x, y, row):
        self.x     = x
        self.y     = y
        self.row   = row
        self.alive = True


class PowerUp:
    TYPES = ['E', '+', 'S']

    def __init__(self, x, y):
        self.x     = float(x)
        self.y     = float(y)
        self.kind  = random.choice(self.TYPES)
        self.alive = True


# ---------------------------------------------------------------------------
# Main game class
# ---------------------------------------------------------------------------
class Game:
    def __init__(self, scr):
        self.scr   = scr
        self._setup_curses()
        self.h, self.w = scr.getmaxyx()

        self.scores    = load_scores()
        self.state     = 'title'
        self.hold_time = 0.0

        # countdown
        self.cd_phase  = 0      # 0=3, 1=2, 2=1, 3=GO!
        self.cd_timer  = 0.0

        # enter_name
        self.name_buf  = ''
        self.pending_score = 0
        self.pending_wave  = 1

        # game state
        self.score      = 0
        self.wave       = 1
        self.ball_speed = float(BALL_SPEED_BASE)
        self.ball_trail = deque(maxlen=3)
        self._init_entities()

    # ------------------------------------------------------------------
    def _setup_curses(self):
        curses.curs_set(0)
        self.scr.nodelay(True)
        curses.start_color()
        curses.use_default_colors()

        curses.init_pair(CP_BORDER,   curses.COLOR_WHITE,   -1)
        curses.init_pair(CP_HUD,      curses.COLOR_CYAN,    -1)
        curses.init_pair(CP_HUD_BEST, curses.COLOR_YELLOW,  -1)
        curses.init_pair(CP_BRICK_0,  curses.COLOR_RED,     -1)
        curses.init_pair(CP_BRICK_1,  curses.COLOR_YELLOW,  -1)
        curses.init_pair(CP_BRICK_2,  curses.COLOR_GREEN,   -1)
        curses.init_pair(CP_BRICK_3,  curses.COLOR_CYAN,    -1)
        curses.init_pair(CP_BRICK_4,  curses.COLOR_MAGENTA, -1)
        curses.init_pair(CP_PADDLE,   curses.COLOR_WHITE,   -1)
        curses.init_pair(CP_BALL,     curses.COLOR_WHITE,   -1)
        curses.init_pair(CP_TRAIL,    curses.COLOR_WHITE,   -1)
        curses.init_pair(CP_PU_E,     curses.COLOR_GREEN,   -1)
        curses.init_pair(CP_PU_PLUS,  curses.COLOR_YELLOW,  -1)
        curses.init_pair(CP_PU_S,     curses.COLOR_BLUE,    -1)
        curses.init_pair(CP_COUNTDOWN,curses.COLOR_YELLOW,  -1)
        curses.init_pair(CP_TITLE,    curses.COLOR_CYAN,    -1)
        curses.init_pair(CP_GAMEOVER, curses.COLOR_RED,     -1)
        curses.init_pair(CP_LEADERBD, curses.COLOR_CYAN,    -1)

    # ------------------------------------------------------------------
    def _init_entities(self):
        """Build paddle, ball, and bricks for current wave (no score reset)."""
        h, w = self.h, self.w
        self.paddle   = Paddle(w // 2 - PADDLE_WIDTH // 2,
                               h - 3, PADDLE_WIDTH)
        self.ball     = Ball(w // 2, h - 4, self.ball_speed)
        self.powerups = []
        self.ball_trail.clear()
        self._build_bricks()

    def _build_bricks(self):
        h, w = self.h, self.w
        brick_cols = (w - 4) // BRICK_W
        total_w    = brick_cols * BRICK_W
        start_x    = (w - total_w) // 2
        self.bricks = [
            Brick(start_x + c * BRICK_W, 3 + r, r)
            for r in range(BRICK_ROWS)
            for c in range(brick_cols)
        ]

    def _best_score(self):
        if not self.scores:
            return 0
        return self.scores[0]['score']

    # ------------------------------------------------------------------
    def run(self):
        last = time.perf_counter()
        while True:
            now = time.perf_counter()
            dt  = min(now - last, 0.05)
            last = now

            if not self._handle_input():
                break

            if self.state == 'playing':
                self._update(dt)
            elif self.state == 'countdown':
                self._update_countdown(dt)

            self._render()

            leftover = FRAME_TIME - (time.perf_counter() - now)
            if leftover > 0:
                time.sleep(leftover)

    # ------------------------------------------------------------------
    def _handle_input(self):
        key = self.scr.getch()

        # Drain extra keys in queue but keep last directional key
        left_pressed  = False
        right_pressed = False
        space_pressed = False
        q_pressed     = False
        enter_pressed = False
        back_pressed  = False
        char_key      = None

        while key != -1:
            if key in (ord('q'), ord('Q'), 27):
                q_pressed = True
            elif key == curses.KEY_LEFT or key == ord('a') or key == ord('A'):
                left_pressed = True
            elif key == curses.KEY_RIGHT or key == ord('d') or key == ord('D'):
                right_pressed = True
            elif key == ord(' '):
                space_pressed = True
            elif key in (curses.KEY_ENTER, 10, 13):
                enter_pressed = True
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                back_pressed = True
            elif 32 <= key <= 126:
                char_key = chr(key).upper()
            key = self.scr.getch()

        if q_pressed:
            return False

        # --- State-specific input ---
        if self.state == 'title':
            if space_pressed:
                self._start_new_game()
        elif self.state == 'playing':
            if right_pressed:
                self.paddle.dir = 1
            elif left_pressed:
                self.paddle.dir = -1
            else:
                self.paddle.dir = 0
        elif self.state == 'countdown':
            if right_pressed:
                self.paddle.dir = 1
            elif left_pressed:
                self.paddle.dir = -1
            else:
                self.paddle.dir = 0
        elif self.state == 'game_over':
            if space_pressed:
                self._start_new_game()
        elif self.state == 'enter_name':
            if enter_pressed and self.name_buf:
                self._submit_name()
            elif back_pressed:
                self.name_buf = self.name_buf[:-1]
            elif char_key and len(self.name_buf) < 3 and char_key.isalpha():
                self.name_buf += char_key
        elif self.state == 'leaderboard':
            if space_pressed:
                self.state = 'title'

        return True

    def _start_new_game(self):
        self.score      = 0
        self.wave       = 1
        self.ball_speed = float(BALL_SPEED_BASE)
        self.hold_time  = 0.0
        self._init_entities()
        self._start_countdown()

    def _start_countdown(self):
        self.state    = 'countdown'
        self.cd_phase = 0
        self.cd_timer = 0.0
        # Pin ball to paddle
        self.ball.x  = self.paddle.x + self.paddle.width / 2
        self.ball.y  = float(self.paddle.y - 1)
        self.ball.vx = 0.0
        self.ball.vy = 0.0
        self.ball_trail.clear()

    def _submit_name(self):
        name = self.name_buf.upper().ljust(3)[:3]
        self.scores = insert_score(self.scores, name,
                                   self.pending_score, self.pending_wave)
        save_scores(self.scores)
        self.state = 'leaderboard'

    # ------------------------------------------------------------------
    def _update_countdown(self, dt):
        # Move paddle during countdown
        self._move_paddle(dt)

        # Pin ball above paddle
        self.ball.x = self.paddle.x + self.paddle.width / 2.0
        self.ball.y = float(self.paddle.y - 1)

        CD_DURATIONS = [0.7, 0.7, 0.7, 0.6]  # 3, 2, 1, GO!
        self.cd_timer += dt
        if self.cd_timer >= CD_DURATIONS[self.cd_phase]:
            self.cd_timer = 0.0
            self.cd_phase += 1
            if self.cd_phase >= 4:
                # Launch ball
                self.ball = Ball(int(self.paddle.x + self.paddle.width / 2),
                                 self.paddle.y - 1, self.ball_speed)
                self.state = 'playing'

    def _move_paddle(self, dt):
        """Shared paddle movement with acceleration."""
        paddle = self.paddle
        h, w   = self.h, self.w
        if paddle.dir != 0:
            self.hold_time = min(self.hold_time + dt, PADDLE_ACCEL_TIME)
        else:
            self.hold_time = 0.0
        t     = self.hold_time / PADDLE_ACCEL_TIME
        speed = PADDLE_SPEED_BASE + t * (PADDLE_SPEED_MAX - PADDLE_SPEED_BASE)
        if paddle.dir:
            paddle.x += paddle.dir * speed * dt
            paddle.x  = max(1.0, min(w - paddle.width - 1.0, paddle.x))

    # ------------------------------------------------------------------
    def _update(self, dt):
        h, w   = self.h, self.w
        ball   = self.ball
        paddle = self.paddle

        # --- Paddle ---
        self._move_paddle(dt)

        # --- Ball trail ---
        self.ball_trail.append((ball.ix, ball.iy))

        # --- Ball movement ---
        ball.x += ball.vx * dt
        ball.y += ball.vy * dt

        # Clamp horizontal speed
        lim     = self.ball_speed * MAX_VX_RATIO
        ball.vx = max(-lim, min(lim, ball.vx))

        # Min vertical speed (prevent horizontal drift)
        if abs(ball.vy) < 8:
            ball.vy = copysign(8, ball.vy)

        # Wall collisions
        if ball.x < 1:
            ball.x  = 1.0
            ball.vx = abs(ball.vx)
        elif ball.x >= w - 1:
            ball.x  = float(w - 2)
            ball.vx = -abs(ball.vx)

        if ball.y < 2:
            ball.y  = 2.0
            ball.vy = abs(ball.vy)

        # Paddle collision
        px = int(paddle.x)
        if (ball.iy == paddle.y and
                px <= ball.ix < px + paddle.width and
                ball.vy > 0):
            ball.vy  = -abs(ball.vy)
            ball.y   = float(paddle.y - 1)
            rel      = (ball.x - paddle.x) / paddle.width   # 0..1
            # Edge zones (±20%) get max angle, center gets small angle
            edge_rel = (rel - 0.5) * 2.0   # -1..1
            ball.vx  = self.ball_speed * edge_rel * 1.2

        # Brick collisions
        for brick in self.bricks:
            if not brick.alive:
                continue
            bx2 = brick.x + BRICK_W - 1
            if (ball.iy == brick.y and
                    brick.x <= ball.ix < bx2):
                brick.alive = False
                ball.vy    *= -1
                self.score += 10 * self.wave
                if random.random() < 0.2:
                    cx = brick.x + BRICK_W // 2
                    self.powerups.append(PowerUp(float(cx), float(brick.y)))

        # Power-ups
        for p in self.powerups:
            p.y += POWERUP_SPEED * dt
            if (int(p.y) == paddle.y and
                    int(paddle.x) <= int(p.x) < int(paddle.x) + paddle.width):
                p.alive = False
                if p.kind == 'E':
                    paddle.width = min(paddle.width + 4, 24)
                elif p.kind == 'S':
                    # Slow: reduce current speed 25%
                    factor      = 0.75
                    ball.vx    *= factor
                    ball.vy    *= factor
                # '+' life: no-op (1-life system)
        self.powerups = [p for p in self.powerups
                         if p.alive and p.y < h - 1]

        # Ball missed → game over (1 life)
        if ball.y >= h - 1:
            self._trigger_game_over()
            return

        # Wave clear
        if all(not b.alive for b in self.bricks):
            self.wave       += 1
            self.ball_speed *= 1.15
            self._init_entities()
            self._start_countdown()

    def _trigger_game_over(self):
        self.pending_score = self.score
        self.pending_wave  = self.wave
        if self.score > 0 and qualifies(self.scores, self.score):
            self.state    = 'enter_name'
            self.name_buf = ''
        else:
            self.state = 'game_over'

    # ------------------------------------------------------------------
    def _render(self):
        scr  = self.scr
        h, w = self.h, self.w
        scr.erase()

        self._draw_border()
        self._draw_hud()

        if self.state in ('playing', 'countdown'):
            self._draw_game()
            if self.state == 'countdown':
                self._draw_countdown()
        elif self.state == 'title':
            self._draw_title()
        elif self.state == 'game_over':
            self._draw_game()   # show final board
            self._draw_game_over()
        elif self.state == 'enter_name':
            self._draw_game()
            self._draw_enter_name()
        elif self.state == 'leaderboard':
            self._draw_leaderboard()

        try:
            scr.refresh()
        except curses.error:
            pass

    # ------------------------------------------------------------------
    def _draw_border(self):
        scr  = self.scr
        h, w = self.h, self.w
        bp   = curses.color_pair(CP_BORDER) | curses.A_DIM
        try:
            # Top bar: ╔═...═╗
            scr.addstr(0, 0, '╔' + '═' * (w - 2) + '╗', bp)
        except curses.error:
            pass
        try:
            # Separator after HUD: ╠═...═╣
            scr.addstr(1, 0, '╠' + '═' * (w - 2) + '╣', bp)
        except curses.error:
            pass
        # Side borders
        for y in range(2, h - 1):
            try:
                scr.addch(y, 0,     '║', bp)
                scr.addch(y, w - 1, '║', bp)
            except curses.error:
                pass
        # Bottom
        try:
            scr.addstr(h - 1, 0, '╚' + '═' * (w - 2) + '╝', bp)
        except curses.error:
            pass

    def _draw_hud(self):
        scr  = self.scr
        h, w = self.h, self.w
        best = self._best_score()

        score_str = f' SCORE: {self.score}'
        wave_str  = f'WAVE: {self.wave} '

        try:
            scr.addstr(0, 2, score_str,
                       curses.color_pair(CP_HUD) | curses.A_BOLD)
        except curses.error:
            pass

        best_str = f'BEST: {best}'
        bx = w // 2 - len(best_str) // 2
        try:
            scr.addstr(0, bx, best_str,
                       curses.color_pair(CP_HUD_BEST) | curses.A_BOLD)
        except curses.error:
            pass

        try:
            scr.addstr(0, w - len(wave_str) - 1, wave_str,
                       curses.color_pair(CP_HUD) | curses.A_BOLD)
        except curses.error:
            pass

    # ------------------------------------------------------------------
    def _draw_game(self):
        scr = self.scr

        # Bricks
        for brick in self.bricks:
            if not brick.alive:
                continue
            cp = curses.color_pair(CP_BRICK[brick.row % len(CP_BRICK)]) | curses.A_BOLD
            try:
                scr.addstr(brick.y, brick.x, '▐████▌', cp)
            except curses.error:
                pass

        # Power-ups
        for p in self.powerups:
            if p.kind == 'E':
                cp = curses.color_pair(CP_PU_E)    | curses.A_BOLD | curses.A_BLINK
            elif p.kind == '+':
                cp = curses.color_pair(CP_PU_PLUS) | curses.A_BOLD | curses.A_BLINK
            else:
                cp = curses.color_pair(CP_PU_S)    | curses.A_BOLD | curses.A_BLINK
            try:
                scr.addch(int(p.y), int(p.x), p.kind, cp)
            except curses.error:
                pass

        # Ball trail
        trail_list = list(self.ball_trail)
        trail_cp   = curses.color_pair(CP_TRAIL) | curses.A_DIM
        for tx, ty in trail_list[:-1]:   # older positions
            try:
                scr.addch(ty, tx, '·', trail_cp)
            except curses.error:
                pass

        # Paddle (reverse = block feel)
        pad_cp = curses.color_pair(CP_PADDLE) | curses.A_BOLD | curses.A_REVERSE
        try:
            scr.addstr(self.paddle.y, int(self.paddle.x),
                       ' ' * self.paddle.width, pad_cp)
        except curses.error:
            pass

        # Ball
        ball_cp = curses.color_pair(CP_BALL) | curses.A_BOLD
        try:
            scr.addch(self.ball.iy, self.ball.ix, '●', ball_cp)
        except curses.error:
            pass

    def _draw_countdown(self):
        scr  = self.scr
        h, w = self.h, self.w
        labels = ['3', '2', '1', 'GO!']
        text   = labels[self.cd_phase]
        cy     = h // 2
        cx     = w // 2 - len(text) // 2
        cp     = curses.color_pair(CP_COUNTDOWN) | curses.A_BOLD
        # Shadow box
        box_w = len(text) + 4
        box_x = w // 2 - box_w // 2
        try:
            scr.addstr(cy - 1, box_x, '┌' + '─' * (box_w - 2) + '┐', cp)
            scr.addstr(cy,     box_x, '│ ' + text + ' │', cp)
            scr.addstr(cy + 1, box_x, '└' + '─' * (box_w - 2) + '┘', cp)
        except curses.error:
            pass

    def _draw_game_over(self):
        scr  = self.scr
        h, w = self.h, self.w
        cp   = curses.color_pair(CP_GAMEOVER) | curses.A_BOLD
        lines = [
            '╔════════════════════════╗',
            '║       GAME  OVER       ║',
            f'║  Score: {self.score:<8}        ║',
            f'║  Wave:  {self.wave:<8}        ║',
            '║                        ║',
            '║  SPACE → Play again    ║',
            '║  Q/ESC → Quit          ║',
            '╚════════════════════════╝',
        ]
        sy = h // 2 - len(lines) // 2
        for i, line in enumerate(lines):
            x = w // 2 - len(line) // 2
            try:
                scr.addstr(sy + i, x, line, cp)
            except curses.error:
                pass

    def _draw_enter_name(self):
        scr  = self.scr
        h, w = self.h, self.w
        cp   = curses.color_pair(CP_COUNTDOWN) | curses.A_BOLD
        cursor  = '_' * (3 - len(self.name_buf))
        display = self.name_buf + cursor
        lines = [
            '╔════════════════════════╗',
            '║    NEW HIGH SCORE!     ║',
           f'║  Score: {self.pending_score:<8}        ║',
            '║                        ║',
            '║  Enter name (3 chars)  ║',
           f'║       [ {display:^3} ]          ║',
            '║  ENTER to confirm      ║',
            '╚════════════════════════╝',
        ]
        sy = h // 2 - len(lines) // 2
        for i, line in enumerate(lines):
            x = w // 2 - len(line) // 2
            try:
                scr.addstr(sy + i, x, line, cp)
            except curses.error:
                pass

    def _draw_leaderboard(self):
        scr  = self.scr
        h, w = self.h, self.w
        cp   = curses.color_pair(CP_LEADERBD) | curses.A_BOLD
        cp_h = curses.color_pair(CP_HUD_BEST) | curses.A_BOLD

        title = '─── LEADERBOARD ───'
        ty    = h // 2 - 7
        scr.addstr(ty, w // 2 - len(title) // 2, title, cp_h)

        top = self.scores[:10]
        for i, entry in enumerate(top):
            line = f"{i+1:>2}. {entry['name']:<3}  {entry['score']:>6}  W{entry['wave']}"
            x = w // 2 - len(line) // 2
            try:
                scr.addstr(ty + 2 + i, x, line, cp if i > 0 else cp_h)
            except curses.error:
                pass

        footer = 'SPACE → Title'
        try:
            scr.addstr(ty + 13, w // 2 - len(footer) // 2, footer,
                       curses.color_pair(CP_HUD) | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_title(self):
        scr  = self.scr
        h, w = self.h, self.w
        cp_t = curses.color_pair(CP_TITLE) | curses.A_BOLD
        cp_y = curses.color_pair(CP_HUD_BEST) | curses.A_BOLD
        cp_h = curses.color_pair(CP_HUD) | curses.A_BOLD

        # ASCII art (short version that fits most terminals)
        art = [
            "  ██████╗██╗     ██╗     █████╗ ██████╗ ██╗  ██╗ █████╗ ███╗   ██╗ ██████╗ ██╗██████╗  ",
            " ██╔════╝██║     ██║    ██╔══██╗██╔══██╗██║ ██╔╝██╔══██╗████╗  ██║██╔═══██╗██║██╔══██╗ ",
            " ██║     ██║     ██║    ███████║██████╔╝█████╔╝ ███████║██╔██╗ ██║██║   ██║██║██║  ██║ ",
            " ██║     ██║     ██║    ██╔══██║██╔══██╗██╔═██╗ ██╔══██║██║╚██╗██║██║   ██║██║██║  ██║ ",
            " ╚██████╗███████╗██║    ██║  ██║██║  ██║██║  ██╗██║  ██║██║ ╚████║╚██████╔╝██║██████╔╝ ",
            "  ╚═════╝╚══════╝╚═╝    ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝╚═════╝  ",
        ]

        art_start_y = 3
        for i, line in enumerate(art):
            x = max(1, w // 2 - len(line) // 2)
            try:
                scr.addstr(art_start_y + i, x, line[:w-2], cp_t)
            except curses.error:
                pass

        # Top scores preview
        top5_y = art_start_y + len(art) + 2
        hdr = '─── TOP SCORES ───'
        try:
            scr.addstr(top5_y, w // 2 - len(hdr) // 2, hdr, cp_y)
        except curses.error:
            pass

        top = self.scores[:5]
        if not top:
            try:
                scr.addstr(top5_y + 1, w // 2 - 8, '  No scores yet  ', cp_h)
            except curses.error:
                pass
        else:
            for i, entry in enumerate(top):
                line = f"{i+1}. {entry['name']:<3}  {entry['score']:>6}  W{entry['wave']}"
                x = w // 2 - len(line) // 2
                try:
                    scr.addstr(top5_y + 1 + i, x, line, cp_h)
                except curses.error:
                    pass

        # Controls
        ctrl_y = top5_y + 8
        controls = [
            'SPACE → Play   Q → Quit',
            '← / A → Move Left    → / D → Move Right',
        ]
        for i, line in enumerate(controls):
            x = w // 2 - len(line) // 2
            try:
                scr.addstr(ctrl_y + i, x, line, cp_h)
            except curses.error:
                pass


# ---------------------------------------------------------------------------
def main(scr):
    # Check terminal size
    h, w = scr.getmaxyx()
    if h < 24 or w < 60:
        scr.addstr(0, 0, f'Terminal too small! Need 60x24, got {w}x{h}')
        scr.refresh()
        time.sleep(3)
        return
    Game(scr).run()


if __name__ == '__main__':
    curses.wrapper(main)
