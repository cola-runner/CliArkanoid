# Runebreaker Prototype

The project is pivoting from a terminal prototype toward a single-player browser game that mixes pinball, boss fights, and light roguelite progression.

## Current Direction

- `Runebreaker` is a one-screen `Canvas` game
- the ball is your soul-core inside an arcane citadel
- side shots light runes and mint resources
- a central boss heart becomes vulnerable after setup
- floor clears award one relic out of three

The older experiments still exist:

- `arkanoid.py`: legacy CLI brick-breaker
- `pinball.py`: legacy CLI pinball prototype

## Web Prototype Files

- `index.html`
- `styles.css`
- `game.js`

## Design Plan

The current gameplay plan is documented in `docs/runebreaker-plan.md`.

## Intended Controls

- `Space`: start, charge, and launch
- `A` / `D` or arrow keys: left / right flippers
- `E`: cast the active spell
- `1` / `2` / `3`: choose a relic reward
- `F`: toggle fullscreen

## Status

The browser prototype is in active design / implementation, with focus currently on:

- first-floor readability
- stable rally physics
- boss vulnerability loop
- relic reward flow
