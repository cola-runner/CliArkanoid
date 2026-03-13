# CLI Pinball Prototype

The project is now pivoting toward a terminal pinball game inspired by classic space tables.

## Current Prototype

- Single-screen ASCII table tuned for `80x24` and playable at `60x24`
- Charged launch lane with a skill-shot window
- Two flippers with direct left / right control
- Three `I O N` targets that light the central reactor
- Reactor jackpot that increases the score multiplier
- Rescue lane, ball save, local high scores, and name entry

The previous brick-breaker still exists in `arkanoid.py`, but the main launcher now starts the pinball prototype in `pinball.py`.

## Run

```bash
python pinball.py
```

On this machine, the compatible Windows launcher is:

```powershell
.\run_game.ps1
```

## Controls

- `Space`: charge and release the launch lane, or start from the title screen
- `Left` / `A`: left flipper
- `Right` / `D`: right flipper
- `H`: open the leaderboard from the title screen
- `Q` / `Esc`: quit

## Requirements

- Terminal size of at least `60x24`
- A Python environment with `curses`
- On Windows, you will usually need `windows-curses`
