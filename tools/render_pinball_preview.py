from __future__ import annotations

import html
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pinball


class BufferScreen:
    def __init__(self, height: int = 30, width: int = 90) -> None:
        self.height = height
        self.width = width
        self.buffer = [[" "] * width for _ in range(height)]

    def getmaxyx(self) -> tuple[int, int]:
        return (self.height, self.width)

    def nodelay(self, flag: bool) -> None:
        return None

    def keypad(self, flag: bool) -> None:
        return None

    def getch(self) -> int:
        return -1

    def erase(self) -> None:
        self.buffer = [[" "] * self.width for _ in range(self.height)]

    def refresh(self) -> None:
        return None

    def addstr(self, y: int, x: int, text: str, attr: int = 0) -> None:
        for offset, char in enumerate(str(text)):
            if 0 <= y < self.height and 0 <= x + offset < self.width:
                self.buffer[y][x + offset] = char

    def addch(self, y: int, x: int, char: str, attr: int = 0) -> None:
        if 0 <= y < self.height and 0 <= x < self.width:
            self.buffer[y][x] = str(char)[0]

    def render_text(self) -> str:
        return "\n".join("".join(row).rstrip() for row in self.buffer)


def bootstrap_game() -> pinball.Game:
    pinball.curses.curs_set = lambda *_: None
    pinball.curses.noecho = lambda: None
    pinball.curses.has_colors = lambda: False
    return pinball.Game(BufferScreen())


def capture_title() -> str:
    screen = BufferScreen()
    game = bootstrap_game()
    game.screen = screen
    game._render()
    return screen.render_text()


def capture_gameplay() -> str:
    screen = BufferScreen()
    game = bootstrap_game()
    game.screen = screen
    game._start_new_game()
    for _ in range(24):
        game._update_playing(1 / 60, pinball.FrameInput(action_down=True), False, False)
    game._update_playing(1 / 60, pinball.FrameInput(action_down=False), False, True)
    for frame_index in range(110):
        frame = pinball.FrameInput(
            left_down=74 <= frame_index <= 86,
            right_down=92 <= frame_index <= 104,
        )
        game._update_playing(1 / 60, frame, False, False)
    game._render()
    return screen.render_text()


def capture_flippers_up() -> str:
    screen = BufferScreen()
    game = bootstrap_game()
    game.screen = screen
    game._start_new_game()
    game.target_lights = [True, True, True]
    game.message = "JACKPOT READY"
    game.message_timer = 2.0
    game.left_flipper.active = True
    game.right_flipper.active = True
    game.left_flipper.update(1 / 60)
    game.right_flipper.update(1 / 60)
    game._render()
    return screen.render_text()


def build_html(title_text: str, gameplay_text: str, flippers_text: str) -> str:
    cards = [
        ("Title", title_text),
        ("Gameplay Mid-Run", gameplay_text),
        ("Flippers Up", flippers_text),
    ]
    sections = []
    for label, text in cards:
        sections.append(
            f"""
            <section class="card">
              <h2>{html.escape(label)}</h2>
              <pre>{html.escape(text)}</pre>
            </section>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Pinball Preview</title>
  <style>
    :root {{
      --bg: #08111b;
      --panel: #102032;
      --line: #1c3956;
      --ink: #cde7ff;
      --accent: #ffd84d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Cascadia Mono", "Fira Code", Consolas, monospace;
      background:
        radial-gradient(circle at top, rgba(37, 114, 180, 0.35), transparent 40%),
        linear-gradient(180deg, #071019, #0d1723 60%, #060c14);
      color: var(--ink);
      min-height: 100vh;
      padding: 32px;
    }}
    h1 {{
      margin: 0 0 10px;
      color: var(--accent);
      font-size: 28px;
    }}
    p {{
      margin: 0 0 24px;
      max-width: 840px;
      color: #97b7d7;
      line-height: 1.5;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(520px, 1fr));
      gap: 20px;
    }}
    .card {{
      background: rgba(16, 32, 50, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.28);
    }}
    h2 {{
      margin: 0 0 12px;
      font-size: 14px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--accent);
    }}
    pre {{
      margin: 0;
      overflow: auto;
      padding: 16px;
      border-radius: 12px;
      background: #06101a;
      border: 1px solid #17324c;
      color: #d9ecff;
      line-height: 1.15;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <h1>CLI Pinball Snapshot</h1>
  <p>Generated from the current terminal renderer so layout, flippers, launch lane, and HUD can be critiqued in a browser before further gameplay work.</p>
  <div class="grid">
    {''.join(sections)}
  </div>
</body>
</html>
"""


def main() -> None:
    output_dir = ROOT / "preview"
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = output_dir / "pinball-preview.html"
    html_path.write_text(
        build_html(capture_title(), capture_gameplay(), capture_flippers_up()),
        encoding="utf-8",
    )
    print(html_path)


if __name__ == "__main__":
    main()
