# Runebreaker Plan

## Vision

`Runebreaker` is a single-player browser game that combines pinball controls, boss-fight structure, and light roguelite progression.

The player is not chasing a raw score table. They are pushing through floors of a living citadel, using a pinball table as the battlefield. Every run should feel like:

1. launch into danger
2. earn momentum by lighting runes and farming resources
3. crack a visible boss weak point
4. take a relic and descend one floor deeper

## Design Pillars

### 1. One-screen readability

At a glance the player should always see:

- where the ball starts
- where the drain danger is
- where the high-value boss shot lives
- which side shots build progress
- current HP, mana, gold, relics, and boss health

### 2. Pinball first, RPG second

The RPG layer exists to strengthen the pinball loop, not replace it.

- primary verbs stay `launch`, `flip`, `save`, `shoot`, `cash in`
- progression should be visible and short-text
- no heavy menus, no inventory screen bloat, no dialogue interruptions during play

### 3. Fast first 30 seconds

Within one half-minute the player should experience:

- a charged launch
- one easy reward event
- one risky side-shot temptation
- one clear "boss is now vulnerable" moment
- one reason to want the next floor

### 4. "One more floor" retention

Runs should end with unfinished progress that feels recoverable:

- boss nearly broken
- one rune left
- enough gold for a stronger next floor
- a relic build beginning to click

## Core Fantasy

The table is a cursed arcane citadel.

- the ball is the player's soul-core
- side orbits are ritual channels
- bumpers are braziers / furnaces
- targets are runes
- central jackpot shot is the citadel heart
- relic rewards are loot taken from each broken floor guardian

## First Milestone

The first playable milestone should be one complete floor with:

- title screen
- one boss
- left and right flippers
- right launch lane with skill shot
- left and right orbit shots
- three runes: `I`, `O`, `N`
- central boss core that only becomes premium when runes are lit
- sentry enemies that drop gold / mana
- drain and ball-save rules
- one active spell
- relic selection after a floor clear
- game over and restart

## Primary Loop

### Combat loop

1. hold and release launch
2. hit a skill shot or orbit to gain early momentum
3. light runes and farm mana / gold
4. expose the boss core
5. hit the core for real damage
6. repeat until boss HP reaches zero

### Run loop

1. clear floor
2. pick one relic out of three
3. start next floor with stronger boss stats
4. build synergy over multiple floors

## Resources

### HP

- represents run health
- losing a ball costs HP if ball save is down
- relics can increase or restore HP

### Mana

- earned from rune lights, orbits, and sentries
- spent on one active spell
- capped to keep decisions readable

### Gold

- earned from side shots and enemy hits
- boosts score and can later support shop/reward design
- should visibly pop on the table when collected

## Systems

### Boss

- one boss per floor
- visible HP bar in HUD
- passive until runes are lit
- becomes vulnerable for a short window

### Rune bank

- three runes are the readable medium-term goal
- lit by direct hits and certain side-shot rewards
- reset after a successful core hit

### Sentries

- light enemy nodes in mid-table
- reward gold and mana
- create more to do during rallies

### Relics

First wave of relic themes:

- more core damage
- more orbit gold
- more rune mana
- longer ball save
- stronger flippers
- more max HP

Relics should be simple, stackable, and visible in the HUD.

### Spell

The first active spell should stay simple:

- `Arcane Surge`
- cost: 3 mana
- effect: temporary core vulnerability + sentry clear + safety buffer

This gives the RPG layer a tactical release valve without making the game menu-heavy.

## Visual Direction

### Mood

- cathedral-meets-arcane-engine
- warm gold against cold midnight blue
- bright ember moments on boss damage

### Composition

- boss heart centered high
- orbit rails clearly framing left/right ambitions
- flippers and drain reading large and unmistakable
- reward panels styled like treasure cards, not plain modal boxes

### HUD

Minimum persistent HUD:

- floor
- gold
- mana
- HP
- boss name
- boss HP
- recent relic names
- short callout text

## Technical Plan

### Stack

- plain `HTML + Canvas + JavaScript`
- no framework required for the first milestone
- deterministic fixed-step update loop
- browser-first debugging

### Runtime structure

Split responsibilities inside `game.js` first, then break files later if needed:

- state and progression
- input
- physics / collisions
- encounter rules
- rendering
- debug / automation hooks

### Required hooks

- `window.advanceTime(ms)` for deterministic automation
- `window.render_game_to_text()` for machine-readable state snapshots

## Milestone Roadmap

### Milestone 1

- stable first floor
- clean title screen
- complete launch / orbit / rune / boss / relic loop

### Milestone 2

- better enemy variety
- stronger relic synergies
- shop or heal room variant between floors
- richer screen juice and damage feedback

### Milestone 3

- multiple boss archetypes
- more spells
- deeper meta progression
- better win/lose summaries and retention framing

## Immediate Next Tasks

1. stabilize first-floor physics and make the rally more reliable
2. tune side shots so rune progression happens naturally
3. make boss damage windows feel dramatic
4. improve title, reward, and game-over panels
5. automate browser screenshots and state dumps with system Edge
