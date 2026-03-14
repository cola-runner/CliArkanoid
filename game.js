(() => {
  "use strict";

  const WIDTH = 1280;
  const HEIGHT = 720;
  const FLOOR_BOTTOM = 680;
  const FLOOR_LEFT = 86;
  const MAIN_RIGHT = 1092;
  const PLUNGER_LEFT = 1112;
  const PLUNGER_RIGHT = 1184;
  const PLUNGER_X = (PLUNGER_LEFT + PLUNGER_RIGHT) * 0.5;
  const GATE_Y = 222;
  const CENTER_X = (FLOOR_LEFT + MAIN_RIGHT) * 0.5;
  const DRAIN_LEFT = CENTER_X - 58;
  const DRAIN_RIGHT = CENTER_X + 58;
  const FIXED_DT = 1 / 60;
  const BALL_RADIUS = 11;
  const GRAVITY = 2350;
  const MAX_SPEED = 2100;
  const PLUNGER_CHARGE_TIME = 0.92;
  const PLUNGER_MIN_SPEED = 860;
  const PLUNGER_MAX_SPEED = 1460;
  const FLIPPER_REST_ANGLE = Math.PI * 0.12;
  const FLIPPER_ACTIVE_ANGLE = Math.PI * 0.34;
  const FLIPPER_SPEED = 18.5;
  const FLIPPER_LENGTH = 124;
  const BALL_SAVE_TIME = 4.2;
  const SKILL_SHOT_TIME = 3.2;
  const MAX_MANA = 6;
  const TRAIL_MAX = 18;

  const canvas = document.getElementById("game");
  const ctx = canvas.getContext("2d");

  const COLORS = {
    bg0: "#081019",
    bg1: "#0f1f2f",
    bg2: "#1e3041",
    gold: "#ffcf68",
    goldDeep: "#c89435",
    ember: "#ff7d4d",
    emberDim: "#8f4d33",
    jade: "#7ff0ce",
    frost: "#b7d8ff",
    parchment: "#efe1bf",
    ink: "#f5f0e2",
    boss: "#b84eff",
  };

  const bosses = [
    "Shard Warden",
    "Ash Bishop",
    "Mirror Beast",
    "Lantern Maw",
    "Rift Templar",
  ];

  const relicPool = [
    {
      id: "iron-heart",
      name: "Iron Heart",
      text: "+1 max HP and heal 1.",
      apply(game) {
        game.maxHp += 1;
        game.hp = Math.min(game.maxHp, game.hp + 1);
      },
    },
    {
      id: "ember-sigil",
      name: "Ember Sigil",
      text: "+4 core damage.",
      apply(game) {
        game.stats.coreDamage += 4;
      },
    },
    {
      id: "coin-magnet",
      name: "Coin Magnet",
      text: "Orbits drop +4 gold.",
      apply(game) {
        game.stats.orbitGold += 4;
      },
    },
    {
      id: "witch-glass",
      name: "Witchglass",
      text: "Rune lights grant +1 mana.",
      apply(game) {
        game.stats.runeMana += 1;
      },
    },
    {
      id: "guardian-halo",
      name: "Guardian Halo",
      text: "+1.5s ball save on each launch.",
      apply(game) {
        game.stats.ballSaveBonus += 1.5;
      },
    },
    {
      id: "storm-brace",
      name: "Storm Brace",
      text: "Flippers hit harder.",
      apply(game) {
        game.stats.flipperBoost += 0.18;
      },
    },
  ];

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function rand(min, max) {
    return min + Math.random() * (max - min);
  }

  function nearestPointOnSegment(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSq = dx * dx + dy * dy;
    if (lengthSq <= 0.0001) {
      return { x: x1, y: y1, t: 0 };
    }
    let t = ((px - x1) * dx + (py - y1) * dy) / lengthSq;
    t = clamp(t, 0, 1);
    return { x: x1 + dx * t, y: y1 + dy * t, t };
  }

  function segmentNormal(x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const length = Math.hypot(dx, dy) || 1;
    return { x: -dy / length, y: dx / length };
  }

  function roundRectPath(context, x, y, w, h, r) {
    const radius = Math.min(r, w * 0.5, h * 0.5);
    context.beginPath();
    context.moveTo(x + radius, y);
    context.arcTo(x + w, y, x + w, y + h, radius);
    context.arcTo(x + w, y + h, x, y + h, radius);
    context.arcTo(x, y + h, x, y, radius);
    context.arcTo(x, y, x + w, y, radius);
    context.closePath();
  }

  class RunebreakerGame {
    constructor(context, surface) {
      this.ctx = context;
      this.canvas = surface;
      this.keys = new Set();
      this.prevKeys = new Set();
      this.pointer = { x: 0, y: 0, down: false };
      this.realtimeEnabled = true;
      this.accumulator = 0;
      this.lastTime = performance.now();
      this.shake = 0;
      this.camera = { x: 0, y: 0 };
      this.titlePulse = 0;
      this.mode = "title";
      this.floor = 1;
      this.gold = 0;
      this.score = 0;
      this.maxHp = 5;
      this.hp = 5;
      this.mana = 0;
      this.stats = {
        coreDamage: 10,
        orbitGold: 8,
        runeMana: 1,
        ballSaveBonus: 0,
        flipperBoost: 0,
      };
      this.relics = [];
      this.relicOptions = [];
      this.rewardCards = [];
      this.message = "Press SPACE to begin";
      this.messageTimer = 999;
      this.skillShotReady = false;
      this.skillShotTimer = 0;
      this.ballSaveTimer = 0;
      this.vulnerableTimer = 0;
      this.charge = 0;
      this.ballInLaunchLane = true;
      this.ball = null;
      this.ballTrail = [];
      this.particles = [];
      this.floatingTexts = [];
      this.collisionCooldowns = new Map();
      this.bumperChargeHits = 0;
      this.runes = [false, false, false];
      this.table = this.buildTable();
      this.leftFlipper = this.makeFlipper("left");
      this.rightFlipper = this.makeFlipper("right");
      this.boss = this.makeBoss(this.floor);
      this.bindEvents();
      this.render();
      this.loop = this.loop.bind(this);
      requestAnimationFrame(this.loop);
    }

    buildTable() {
      const leftPivot = { x: CENTER_X - 138, y: FLOOR_BOTTOM - 54 };
      const rightPivot = { x: CENTER_X + 138, y: FLOOR_BOTTOM - 54 };
      return {
        leftPivot,
        rightPivot,
        core: { x: CENTER_X, y: 222, r: 54 },
        runes: [
          { x: CENTER_X - 180, y: 160, r: 28, letter: "I" },
          { x: CENTER_X, y: 142, r: 28, letter: "O" },
          { x: CENTER_X + 180, y: 160, r: 28, letter: "N" },
        ],
        braziers: [
          { x: CENTER_X - 150, y: 262, r: 26, kind: "brazier-left" },
          { x: CENTER_X, y: 232, r: 28, kind: "brazier-mid" },
          { x: CENTER_X + 150, y: 262, r: 26, kind: "brazier-right" },
        ],
        sentries: [
          { x: CENTER_X - 96, y: 340, r: 20, kind: "sentry-left", alive: true, respawn: 0 },
          { x: CENTER_X + 96, y: 340, r: 20, kind: "sentry-right", alive: true, respawn: 0 },
        ],
        coreLane: { left: CENTER_X - 70, right: CENTER_X + 70, top: 132, bottom: 312 },
        leftOrbit: { left: FLOOR_LEFT, right: FLOOR_LEFT + 126, top: 120, bottom: 300, name: "left-orbit" },
        rightOrbit: { left: MAIN_RIGHT - 126, right: MAIN_RIGHT, top: 120, bottom: 300, name: "right-orbit" },
        segments: [
          { name: "left-wall", x1: FLOOR_LEFT, y1: 116, x2: FLOOR_LEFT, y2: FLOOR_BOTTOM - 154, thickness: 10 },
          { name: "top-left", x1: FLOOR_LEFT + 28, y1: 116, x2: CENTER_X - 250, y2: 116, thickness: 10 },
          { name: "top-right", x1: CENTER_X + 250, y1: 116, x2: MAIN_RIGHT - 28, y2: 116, thickness: 10 },
          { name: "left-orbit-wall", x1: FLOOR_LEFT + 4, y1: 242, x2: FLOOR_LEFT + 96, y2: 116, thickness: 10 },
          { name: "right-orbit-wall", x1: MAIN_RIGHT - 96, y1: 116, x2: MAIN_RIGHT - 4, y2: 242, thickness: 10 },
          { name: "left-feed", x1: FLOOR_LEFT + 126, y1: 132, x2: CENTER_X - 242, y2: 196, thickness: 8 },
          { name: "right-feed", x1: CENTER_X + 242, y1: 196, x2: MAIN_RIGHT - 126, y2: 132, thickness: 8 },
          { name: "left-reactor-guide", x1: CENTER_X - 220, y1: 286, x2: CENTER_X - 76, y2: 346, thickness: 8 },
          { name: "right-reactor-guide", x1: CENTER_X + 76, y1: 346, x2: CENTER_X + 220, y2: 286, thickness: 8 },
          { name: "main-right-wall", x1: MAIN_RIGHT, y1: 236, x2: MAIN_RIGHT, y2: FLOOR_BOTTOM - 154, thickness: 10 },
          { name: "plunger-outer", x1: PLUNGER_RIGHT, y1: 116, x2: PLUNGER_RIGHT, y2: FLOOR_BOTTOM - 10, thickness: 10 },
          { name: "plunger-inner", x1: PLUNGER_LEFT, y1: GATE_Y, x2: PLUNGER_LEFT, y2: FLOOR_BOTTOM - 74, thickness: 10 },
          { name: "left-lane", x1: FLOOR_LEFT + 12, y1: FLOOR_BOTTOM - 8, x2: leftPivot.x - 94, y2: FLOOR_BOTTOM - 118, thickness: 8 },
          { name: "right-lane", x1: MAIN_RIGHT - 12, y1: FLOOR_BOTTOM - 8, x2: rightPivot.x + 94, y2: FLOOR_BOTTOM - 118, thickness: 8 },
          { name: "left-guard", x1: DRAIN_LEFT - 22, y1: FLOOR_BOTTOM - 6, x2: CENTER_X - 112, y2: FLOOR_BOTTOM - 120, thickness: 8 },
          { name: "right-guard", x1: DRAIN_RIGHT + 22, y1: FLOOR_BOTTOM - 6, x2: CENTER_X + 112, y2: FLOOR_BOTTOM - 120, thickness: 8 },
          { name: "left-sling", x1: CENTER_X - 36, y1: FLOOR_BOTTOM - 170, x2: leftPivot.x + 74, y2: FLOOR_BOTTOM - 102, thickness: 10 },
          { name: "right-sling", x1: CENTER_X + 36, y1: FLOOR_BOTTOM - 170, x2: rightPivot.x - 74, y2: FLOOR_BOTTOM - 102, thickness: 10 },
        ],
        posts: [
          { x: leftPivot.x - 44, y: FLOOR_BOTTOM - 104, r: 12 },
          { x: CENTER_X - 72, y: FLOOR_BOTTOM - 136, r: 12 },
          { x: CENTER_X + 72, y: FLOOR_BOTTOM - 136, r: 12 },
          { x: rightPivot.x + 44, y: FLOOR_BOTTOM - 104, r: 12 },
        ],
      };
    }

    makeFlipper(side) {
      const pivot = side === "left" ? this.table.leftPivot : this.table.rightPivot;
      return {
        side,
        pivotX: pivot.x,
        pivotY: pivot.y,
        angle: FLIPPER_REST_ANGLE,
        active: false,
        angularVelocity: 0,
      };
    }

    makeBoss(floor) {
      const maxHp = 34 + floor * 16;
      return {
        name: bosses[(floor - 1) % bosses.length],
        hp: maxHp,
        maxHp,
      };
    }

    bindEvents() {
      window.addEventListener("keydown", (event) => {
        if (["ArrowLeft", "ArrowRight", "Space", "KeyA", "KeyD", "KeyE", "Digit1", "Digit2", "Digit3", "KeyF"].includes(event.code)) {
          event.preventDefault();
        }
        if (event.code === "KeyF") {
          this.toggleFullscreen();
        }
        this.keys.add(event.code);
      });

      window.addEventListener("keyup", (event) => {
        this.keys.delete(event.code);
      });

      window.addEventListener("blur", () => {
        this.keys.clear();
      });

      window.addEventListener("resize", () => {
        this.render();
      });

      this.canvas.addEventListener("pointermove", (event) => {
        this.pointer = { ...this.pointer, ...this.toGameCoords(event) };
      });

      this.canvas.addEventListener("pointerdown", (event) => {
        this.pointer = { ...this.pointer, ...this.toGameCoords(event), down: true };
        this.handlePointerDown();
      });

      this.canvas.addEventListener("pointerup", () => {
        this.pointer.down = false;
      });
    }

    toGameCoords(event) {
      const rect = this.canvas.getBoundingClientRect();
      return {
        x: (event.clientX - rect.left) * (WIDTH / rect.width),
        y: (event.clientY - rect.top) * (HEIGHT / rect.height),
      };
    }

    toggleFullscreen() {
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
        return;
      }
      this.canvas.requestFullscreen?.().catch(() => {});
    }

    keyDown(code) {
      return this.keys.has(code);
    }

    keyPressed(code) {
      return this.keys.has(code) && !this.prevKeys.has(code);
    }

    keyReleased(code) {
      return !this.keys.has(code) && this.prevKeys.has(code);
    }

    handlePointerDown() {
      if (this.mode === "title" || this.mode === "gameover") {
        this.startRun();
        return;
      }
      if (this.mode !== "reward") {
        return;
      }
      const card = this.rewardCards.find((item) => {
        return this.pointer.x >= item.x && this.pointer.x <= item.x + item.w && this.pointer.y >= item.y && this.pointer.y <= item.y + item.h;
      });
      if (card) {
        this.applyRelicChoice(card.index);
      }
    }

    startRun() {
      this.floor = 1;
      this.gold = 0;
      this.score = 0;
      this.maxHp = 5;
      this.hp = 5;
      this.mana = 0;
      this.relics = [];
      this.stats = {
        coreDamage: 10,
        orbitGold: 8,
        runeMana: 1,
        ballSaveBonus: 0,
        flipperBoost: 0,
      };
      this.startFloor();
      this.showMessage("Light the runes. Break the core.", 3.2);
    }

    startFloor() {
      this.mode = "playing";
      this.boss = this.makeBoss(this.floor);
      this.runes = [false, false, false];
      this.vulnerableTimer = 0;
      this.ballSaveTimer = 0;
      this.skillShotTimer = 0;
      this.skillShotReady = false;
      this.collisionCooldowns.clear();
      this.ballTrail = [];
      this.particles = [];
      this.floatingTexts = [];
      this.bumperChargeHits = 0;
      this.table.sentries.forEach((sentry) => {
        sentry.alive = true;
        sentry.respawn = 0;
      });
      this.serveBall();
    }

    serveBall() {
      this.ball = {
        x: PLUNGER_X,
        y: FLOOR_BOTTOM - 44,
        vx: 0,
        vy: 0,
        r: BALL_RADIUS,
      };
      this.ballInLaunchLane = true;
      this.charge = 0;
      this.skillShotReady = false;
      this.skillShotTimer = 0;
      this.ballSaveTimer = BALL_SAVE_TIME + this.stats.ballSaveBonus;
      this.ballTrail = [];
    }

    launchBall() {
      if (!this.ball) {
        return;
      }
      const power = clamp(this.charge, 0.16, 1);
      const speed = lerp(PLUNGER_MIN_SPEED, PLUNGER_MAX_SPEED, power);
      this.ball.vx = 0;
      this.ball.vy = -speed;
      this.ballInLaunchLane = false;
      this.skillShotReady = true;
      this.skillShotTimer = SKILL_SHOT_TIME;
      this.charge = 0;
      this.showMessage("Skill shot lit", 1.2);
    }

    showMessage(text, duration = 1.6) {
      this.message = text;
      this.messageTimer = duration;
    }

    addFloatingText(text, x, y, color = COLORS.gold) {
      this.floatingTexts.push({ text, x, y, vy: -28, life: 0.85, color });
    }

    addParticles(x, y, count, color, speed = 140) {
      for (let i = 0; i < count; i++) {
        const angle = rand(0, Math.PI * 2);
        const force = rand(speed * 0.25, speed);
        this.particles.push({
          x,
          y,
          vx: Math.cos(angle) * force,
          vy: Math.sin(angle) * force,
          size: rand(3, 7),
          life: rand(0.24, 0.6),
          color,
        });
      }
    }

    earnGold(amount, x, y) {
      this.gold += amount;
      this.score += amount * 10;
      this.addFloatingText(`+${amount}g`, x, y, COLORS.gold);
      this.addParticles(x, y, 8, COLORS.gold, 110);
    }

    gainMana(amount, x, y) {
      const before = this.mana;
      this.mana = clamp(this.mana + amount, 0, MAX_MANA);
      if (this.mana !== before) {
        this.addFloatingText(`+${this.mana - before} mana`, x, y, COLORS.jade);
      }
    }

    lightRune(index, sourceX, sourceY) {
      if (this.runes[index]) {
        this.score += 60;
        return false;
      }
      this.runes[index] = true;
      this.score += 150;
      this.gainMana(this.stats.runeMana, sourceX, sourceY);
      this.addParticles(sourceX, sourceY, 10, COLORS.jade, 130);
      this.addFloatingText(`Rune ${this.table.runes[index].letter}`, sourceX, sourceY, COLORS.jade);
      if (this.runes.every(Boolean)) {
        this.vulnerableTimer = 10;
        this.showMessage("Core exposed", 1.4);
        this.shake = Math.max(this.shake, 12);
      } else {
        this.showMessage(`Rune ${this.table.runes[index].letter} lit`, 0.9);
      }
      return true;
    }

    lightNextRune(sourceX, sourceY) {
      const nextIndex = this.runes.findIndex((lit) => !lit);
      if (nextIndex === -1) {
        this.score += 80;
        return;
      }
      this.lightRune(nextIndex, sourceX, sourceY);
    }

    castSpell() {
      if (this.mode !== "playing" || this.ballInLaunchLane || this.mana < 3) {
        return;
      }
      this.mana -= 3;
      this.vulnerableTimer = Math.max(this.vulnerableTimer, 4.5);
      this.ballSaveTimer = Math.max(this.ballSaveTimer, 3.5);
      this.showMessage("Arcane surge", 1.1);
      this.addParticles(CENTER_X, 180, 24, COLORS.ember, 170);
      this.table.sentries.forEach((sentry) => {
        if (!sentry.alive) {
          return;
        }
        sentry.alive = false;
        sentry.respawn = 3.5;
        this.earnGold(6 + this.floor, sentry.x, sentry.y);
      });
    }

    winFloor() {
      this.mode = "reward";
      this.hp = Math.min(this.maxHp, this.hp + 1);
      this.relicOptions = this.makeRelicChoices();
      this.rewardCards = [];
      this.showMessage("Choose a relic", 999);
    }

    makeRelicChoices() {
      const available = relicPool.filter((relic) => !this.relics.some((owned) => owned.id === relic.id));
      const source = available.length >= 3 ? [...available] : [...relicPool];
      const picks = [];
      while (picks.length < 3 && source.length) {
        const index = Math.floor(Math.random() * source.length);
        picks.push(source.splice(index, 1)[0]);
      }
      return picks;
    }

    applyRelicChoice(index) {
      const relic = this.relicOptions[index];
      if (!relic) {
        return;
      }
      this.relics.push(relic);
      relic.apply(this);
      this.floor += 1;
      this.startFloor();
      this.showMessage(`${relic.name} claimed`, 1.2);
    }

    loseBall() {
      if (this.ballSaveTimer > 0) {
        this.serveBall();
        this.showMessage("Soul saved", 1.0);
        return;
      }
      this.hp -= 1;
      this.shake = Math.max(this.shake, 14);
      if (this.hp <= 0) {
        this.mode = "gameover";
        this.ball = null;
        this.showMessage("The citadel holds", 999);
        return;
      }
      this.serveBall();
      this.showMessage("Soul lost", 1.0);
    }

    getFlipperSegment(flipper) {
      const dx = Math.cos(flipper.angle) * FLIPPER_LENGTH;
      const dy = Math.sin(flipper.angle) * FLIPPER_LENGTH;
      if (flipper.side === "left") {
        return {
          x1: flipper.pivotX,
          y1: flipper.pivotY,
          x2: flipper.pivotX + dx,
          y2: flipper.pivotY - dy,
        };
      }
      return {
        x1: flipper.pivotX,
        y1: flipper.pivotY,
        x2: flipper.pivotX - dx,
        y2: flipper.pivotY - dy,
      };
    }

    updateFlipper(flipper, active, dt) {
      const target = active ? FLIPPER_ACTIVE_ANGLE : FLIPPER_REST_ANGLE;
      const previous = flipper.angle;
      if (flipper.angle < target) {
        flipper.angle = Math.min(target, flipper.angle + FLIPPER_SPEED * dt);
      } else {
        flipper.angle = Math.max(target, flipper.angle - FLIPPER_SPEED * dt);
      }
      flipper.active = active;
      flipper.angularVelocity = (flipper.angle - previous) / dt;
    }

    updateSentries(dt) {
      this.table.sentries.forEach((sentry) => {
        if (sentry.alive) {
          return;
        }
        sentry.respawn = Math.max(0, sentry.respawn - dt);
        if (sentry.respawn === 0) {
          sentry.alive = true;
          this.addParticles(sentry.x, sentry.y, 10, COLORS.ember, 110);
        }
      });
    }

    updateEffects(dt) {
      this.titlePulse += dt;
      this.shake = Math.max(0, this.shake - dt * 22);
      this.camera.x = rand(-this.shake, this.shake);
      this.camera.y = rand(-this.shake, this.shake);

      this.particles = this.particles.filter((particle) => {
        particle.life -= dt;
        particle.x += particle.vx * dt;
        particle.y += particle.vy * dt;
        particle.vx *= 0.98;
        particle.vy *= 0.98;
        return particle.life > 0;
      });

      this.floatingTexts = this.floatingTexts.filter((item) => {
        item.life -= dt;
        item.y += item.vy * dt;
        return item.life > 0;
      });

      this.collisionCooldowns.forEach((time, key) => {
        const next = Math.max(0, time - dt);
        if (next === 0) {
          this.collisionCooldowns.delete(key);
        } else {
          this.collisionCooldowns.set(key, next);
        }
      });

      if (this.messageTimer < 999) {
        this.messageTimer = Math.max(0, this.messageTimer - dt);
      }
    }

    cooldownActive(key) {
      return (this.collisionCooldowns.get(key) || 0) > 0;
    }

    setCooldown(key, duration) {
      this.collisionCooldowns.set(key, duration);
    }

    update(dt) {
      this.updateEffects(dt);

      if (this.mode === "title") {
        if (this.keyPressed("Space")) {
          this.startRun();
        }
      } else if (this.mode === "gameover") {
        if (this.keyPressed("Space")) {
          this.startRun();
        }
      } else if (this.mode === "reward") {
        if (this.keyPressed("Digit1")) {
          this.applyRelicChoice(0);
        } else if (this.keyPressed("Digit2")) {
          this.applyRelicChoice(1);
        } else if (this.keyPressed("Digit3")) {
          this.applyRelicChoice(2);
        }
      } else if (this.mode === "playing") {
        this.updatePlaying(dt);
      }

      this.prevKeys = new Set(this.keys);
    }

    updatePlaying(dt) {
      this.updateSentries(dt);
      this.vulnerableTimer = Math.max(0, this.vulnerableTimer - dt);
      this.skillShotTimer = Math.max(0, this.skillShotTimer - dt);
      this.ballSaveTimer = Math.max(0, this.ballSaveTimer - dt);

      const leftActive = this.keyDown("ArrowLeft") || this.keyDown("KeyA");
      const rightActive = this.keyDown("ArrowRight") || this.keyDown("KeyD");
      this.updateFlipper(this.leftFlipper, leftActive, dt);
      this.updateFlipper(this.rightFlipper, rightActive, dt);

      if (this.keyPressed("KeyE")) {
        this.castSpell();
      }

      if (!this.ball) {
        return;
      }

      if (this.ballInLaunchLane) {
        this.ball.x = PLUNGER_X;
        this.ball.y = FLOOR_BOTTOM - 44;
        this.ball.vx = 0;
        this.ball.vy = 0;
        if (this.keyDown("Space")) {
          this.charge = clamp(this.charge + dt / PLUNGER_CHARGE_TIME, 0, 1);
          this.showMessage(`Charge ${Math.round(this.charge * 100)}%`, 0.18);
          return;
        }
        if (this.keyReleased("Space") && this.charge > 0) {
          this.launchBall();
        }
        return;
      }

      this.ballTrail.push({ x: this.ball.x, y: this.ball.y });
      if (this.ballTrail.length > TRAIL_MAX) {
        this.ballTrail.shift();
      }

      const steps = Math.max(1, Math.floor((Math.abs(this.ball.vx) + Math.abs(this.ball.vy) + 420) / 720));
      const stepDt = dt / steps;
      for (let i = 0; i < steps; i++) {
        this.stepBall(stepDt);
        if (!this.ball || this.ballInLaunchLane || this.mode !== "playing") {
          break;
        }
      }
    }

    stepBall(dt) {
      if (!this.ball) {
        return;
      }

      this.ball.vy = clamp(this.ball.vy + GRAVITY * dt, -MAX_SPEED, MAX_SPEED);
      this.ball.x += this.ball.vx * dt;
      this.ball.y += this.ball.vy * dt;

      if (this.runes.every(Boolean) && this.ball.y < this.table.coreLane.bottom && this.ball.y > this.table.coreLane.top) {
        const offset = (this.table.core.x - this.ball.x) * 0.0018;
        this.ball.vx += offset * 80;
      }

      this.resolveSegmentCollisions();
      this.resolveCircleCollisions();
      this.resolveFlipperCollisions();
      this.handleTriggers();
      this.checkDrain();
    }

    resolveSegmentCollisions() {
      if (!this.ball) {
        return;
      }
      for (const segment of this.table.segments) {
        const point = nearestPointOnSegment(this.ball.x, this.ball.y, segment.x1, segment.y1, segment.x2, segment.y2);
        const dx = this.ball.x - point.x;
        const dy = this.ball.y - point.y;
        const distance = Math.hypot(dx, dy);
        const limit = this.ball.r + segment.thickness;
        if (distance >= limit) {
          continue;
        }
        let nx;
        let ny;
        if (distance <= 0.001) {
          const normal = segmentNormal(segment.x1, segment.y1, segment.x2, segment.y2);
          nx = normal.x;
          ny = normal.y;
        } else {
          nx = dx / distance;
          ny = dy / distance;
        }
        const penetration = limit - distance;
        this.ball.x += nx * penetration;
        this.ball.y += ny * penetration;
        const normalSpeed = this.ball.vx * nx + this.ball.vy * ny;
        if (normalSpeed < 0) {
          this.ball.vx -= 1.8 * normalSpeed * nx;
          this.ball.vy -= 1.8 * normalSpeed * ny;
        }
        if ((segment.name === "left-sling" || segment.name === "right-sling") && !this.cooldownActive(segment.name)) {
          this.setCooldown(segment.name, 0.12);
          this.ball.vx += segment.name === "left-sling" ? 220 : -220;
          this.ball.vy = Math.min(this.ball.vy, -980);
          this.score += 90;
          this.addParticles(this.ball.x, this.ball.y, 8, COLORS.ember, 150);
          this.showMessage("Slingshot", 0.45);
        }
      }
    }

    resolveCircleCollisions() {
      if (!this.ball) {
        return;
      }

      const colliders = [
        ...this.table.braziers,
        ...this.table.posts,
        ...this.table.runes,
        this.table.core,
        ...this.table.sentries.filter((sentry) => sentry.alive),
      ];

      for (const circle of colliders) {
        const dx = this.ball.x - circle.x;
        const dy = this.ball.y - circle.y;
        const distance = Math.hypot(dx, dy);
        const limit = this.ball.r + circle.r;
        if (distance >= limit) {
          continue;
        }
        let nx = dx / (distance || 1);
        let ny = dy / (distance || 1);
        if (distance < 0.0001) {
          nx = 0;
          ny = -1;
        }
        const penetration = limit - distance;
        this.ball.x += nx * penetration;
        this.ball.y += ny * penetration;
        const normalSpeed = this.ball.vx * nx + this.ball.vy * ny;
        if (normalSpeed < 0) {
          const bounce = circle === this.table.core ? 1.78 : 1.6;
          this.ball.vx -= bounce * normalSpeed * nx;
          this.ball.vy -= bounce * normalSpeed * ny;
        }

        if (circle.kind?.startsWith("brazier")) {
          this.handleBrazierHit(circle, nx, ny);
        } else if (circle.letter) {
          this.handleRuneHit(circle);
        } else if (circle === this.table.core) {
          this.handleCoreHit();
        } else if (circle.kind?.startsWith("sentry")) {
          this.handleSentryHit(circle);
        }
      }
    }

    handleBrazierHit(circle, nx, ny) {
      if (this.cooldownActive(circle.kind)) {
        return;
      }
      this.setCooldown(circle.kind, 0.1);
      this.bumperChargeHits += 1;
      this.ball.vx += nx * 260;
      this.ball.vy += ny * 260;
      this.score += 70;
      this.earnGold(2, circle.x, circle.y);
      if (!this.runes.every(Boolean) && this.bumperChargeHits % 4 === 0) {
        this.lightNextRune(circle.x, circle.y);
      } else {
        this.addFloatingText("Spark", circle.x, circle.y, COLORS.ember);
      }
      this.addParticles(circle.x, circle.y, 9, COLORS.ember, 140);
    }

    handleRuneHit(rune) {
      const index = this.table.runes.indexOf(rune);
      if (index === -1 || this.cooldownActive(`rune-${index}`)) {
        return;
      }
      this.setCooldown(`rune-${index}`, 0.18);
      this.lightRune(index, rune.x, rune.y);
    }

    handleSentryHit(sentry) {
      if (!sentry.alive || this.cooldownActive(sentry.kind)) {
        return;
      }
      this.setCooldown(sentry.kind, 0.25);
      sentry.alive = false;
      sentry.respawn = 5.2;
      this.earnGold(6 + Math.floor(this.floor * 0.5), sentry.x, sentry.y);
      this.gainMana(1, sentry.x, sentry.y);
      this.score += 180;
      this.addParticles(sentry.x, sentry.y, 14, COLORS.ember, 160);
      this.showMessage("Sentry shattered", 0.65);
    }

    handleCoreHit() {
      if (this.cooldownActive("core")) {
        return;
      }
      this.setCooldown("core", 0.3);
      if (this.vulnerableTimer > 0 || this.runes.every(Boolean)) {
        const damage = this.stats.coreDamage + Math.floor(this.gold * 0.02);
        this.boss.hp = Math.max(0, this.boss.hp - damage);
        this.score += damage * 60;
        this.addFloatingText(`-${damage}`, this.table.core.x, this.table.core.y, COLORS.ember);
        this.addParticles(this.table.core.x, this.table.core.y, 18, COLORS.ember, 180);
        this.shake = Math.max(this.shake, 16);
        this.runes = [false, false, false];
        this.vulnerableTimer = 0;
        this.showMessage("Core hit", 0.85);
        if (this.boss.hp <= 0) {
          this.winFloor();
        }
        return;
      }
      this.score += 70;
      this.addParticles(this.table.core.x, this.table.core.y, 8, COLORS.frost, 80);
      this.showMessage("Shielded", 0.5);
    }

    resolveFlipperCollisions() {
      if (!this.ball) {
        return;
      }
      for (const flipper of [this.leftFlipper, this.rightFlipper]) {
        const segment = this.getFlipperSegment(flipper);
        const point = nearestPointOnSegment(this.ball.x, this.ball.y, segment.x1, segment.y1, segment.x2, segment.y2);
        const dx = this.ball.x - point.x;
        const dy = this.ball.y - point.y;
        const distance = Math.hypot(dx, dy);
        const limit = this.ball.r + 18;
        if (distance >= limit) {
          continue;
        }
        let nx = dx / (distance || 1);
        let ny = dy / (distance || 1);
        if (distance < 0.0001) {
          const normal = segmentNormal(segment.x1, segment.y1, segment.x2, segment.y2);
          nx = normal.x;
          ny = normal.y;
        }
        if (ny < -0.1) {
          nx = -nx;
          ny = -ny;
        }
        const penetration = limit - distance;
        this.ball.x += nx * penetration;
        this.ball.y += ny * penetration;
        const normalSpeed = this.ball.vx * nx + this.ball.vy * ny;
        if (normalSpeed < 0) {
          this.ball.vx -= 1.85 * normalSpeed * nx;
          this.ball.vy -= 1.85 * normalSpeed * ny;
        }

        const side = flipper.side === "left" ? 1 : -1;
        const boost = 1 + this.stats.flipperBoost;
        if (flipper.active && flipper.angularVelocity !== 0) {
          this.ball.vx += side * (360 + 160 * (1 - point.t)) * boost;
          this.ball.vy = Math.min(this.ball.vy, -(980 + 180 * point.t) * boost);
        } else {
          this.ball.vx += side * 95 * boost;
          this.ball.vy = Math.min(this.ball.vy, -820 * boost);
        }
      }
    }

    handleTriggers() {
      if (!this.ball) {
        return;
      }

      if (this.ball.x >= this.table.leftOrbit.left && this.ball.x <= this.table.leftOrbit.right && this.ball.y >= this.table.leftOrbit.top && this.ball.y <= this.table.leftOrbit.bottom && this.ball.vy < 0 && !this.cooldownActive("left-orbit")) {
        this.setCooldown("left-orbit", 0.35);
        this.earnGold(this.stats.orbitGold, this.ball.x, this.ball.y);
        this.gainMana(1, this.ball.x, this.ball.y);
        this.lightNextRune(this.ball.x, this.ball.y);
        this.ball.vx = Math.max(this.ball.vx, 620);
        this.showMessage("Left orbit", 0.55);
      }

      if (this.ball.x >= this.table.rightOrbit.left && this.ball.x <= this.table.rightOrbit.right && this.ball.y >= this.table.rightOrbit.top && this.ball.y <= this.table.rightOrbit.bottom && this.ball.vy < 0 && !this.cooldownActive("right-orbit")) {
        this.setCooldown("right-orbit", 0.35);
        this.earnGold(this.stats.orbitGold, this.ball.x, this.ball.y);
        this.gainMana(1, this.ball.x, this.ball.y);
        this.lightNextRune(this.ball.x, this.ball.y);
        this.ball.vx = Math.min(this.ball.vx, -620);
        this.showMessage("Right orbit", 0.55);
      }

      if (this.skillShotReady && this.ball.x > PLUNGER_LEFT - 6 && this.ball.y < GATE_Y) {
        this.skillShotReady = false;
        this.earnGold(12, this.ball.x, this.ball.y);
        this.gainMana(2, this.ball.x, this.ball.y);
        this.lightNextRune(this.ball.x, this.ball.y);
        this.showMessage("Skill shot", 0.9);
        this.ball.vx = -700;
        this.ball.vy = Math.min(this.ball.vy, -880);
      }

      if (this.skillShotTimer <= 0) {
        this.skillShotReady = false;
      }
    }

    checkDrain() {
      if (!this.ball) {
        return;
      }
      if (this.ball.y < FLOOR_BOTTOM + 30) {
        return;
      }
      if ((this.ball.x >= DRAIN_LEFT && this.ball.x <= DRAIN_RIGHT) || this.ball.y > HEIGHT + 30) {
        this.loseBall();
      }
    }

    loop(time) {
      if (this.realtimeEnabled) {
        const delta = Math.min(0.05, (time - this.lastTime) / 1000);
        this.lastTime = time;
        this.accumulator += delta;
        while (this.accumulator >= FIXED_DT) {
          this.update(FIXED_DT);
          this.accumulator -= FIXED_DT;
        }
        this.render();
      }
      requestAnimationFrame(this.loop);
    }

    advance(ms) {
      this.realtimeEnabled = false;
      const steps = Math.max(1, Math.round(ms / (FIXED_DT * 1000)));
      for (let i = 0; i < steps; i++) {
        this.update(FIXED_DT);
      }
      this.render();
    }

    drawBackground() {
      const gradient = ctx.createLinearGradient(0, 0, 0, HEIGHT);
      gradient.addColorStop(0, COLORS.bg2);
      gradient.addColorStop(0.42, COLORS.bg1);
      gradient.addColorStop(1, COLORS.bg0);
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      ctx.fillStyle = "rgba(255, 208, 114, 0.08)";
      ctx.beginPath();
      ctx.arc(CENTER_X, 116, 280, Math.PI, 0, false);
      ctx.fill();

      ctx.fillStyle = "rgba(90, 230, 190, 0.06)";
      ctx.beginPath();
      ctx.arc(CENTER_X, 310, 250, Math.PI, 0, false);
      ctx.fill();
    }

    drawTable() {
      ctx.save();
      ctx.translate(this.camera.x, this.camera.y);

      roundRectPath(ctx, FLOOR_LEFT - 22, 104, PLUNGER_RIGHT - FLOOR_LEFT + 42, FLOOR_BOTTOM - 104 + 12, 28);
      const bodyGradient = ctx.createLinearGradient(0, 104, 0, FLOOR_BOTTOM);
      bodyGradient.addColorStop(0, "#112234");
      bodyGradient.addColorStop(0.5, "#14273b");
      bodyGradient.addColorStop(1, "#0b131f");
      ctx.fillStyle = bodyGradient;
      ctx.fill();

      ctx.lineWidth = 4;
      ctx.strokeStyle = "rgba(255, 207, 104, 0.35)";
      ctx.stroke();

      ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
      ctx.lineWidth = 1.5;
      this.table.segments.forEach((segment) => {
        ctx.beginPath();
        ctx.moveTo(segment.x1, segment.y1);
        ctx.lineTo(segment.x2, segment.y2);
        ctx.stroke();
      });

      ctx.strokeStyle = "rgba(127, 240, 206, 0.18)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(FLOOR_LEFT + 52, 138);
      ctx.lineTo(FLOOR_LEFT + 152, 262);
      ctx.lineTo(FLOOR_LEFT + 212, 312);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(MAIN_RIGHT - 52, 138);
      ctx.lineTo(MAIN_RIGHT - 152, 262);
      ctx.lineTo(MAIN_RIGHT - 212, 312);
      ctx.stroke();

      ctx.fillStyle = "rgba(255, 207, 104, 0.12)";
      ctx.beginPath();
      ctx.moveTo(CENTER_X - 96, 404);
      ctx.lineTo(CENTER_X - 216, 510);
      ctx.lineTo(CENTER_X - 92, 510);
      ctx.closePath();
      ctx.fill();
      ctx.beginPath();
      ctx.moveTo(CENTER_X + 96, 404);
      ctx.lineTo(CENTER_X + 216, 510);
      ctx.lineTo(CENTER_X + 92, 510);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = "rgba(255, 125, 77, 0.15)";
      ctx.beginPath();
      ctx.moveTo(DRAIN_LEFT - 42, FLOOR_BOTTOM - 16);
      ctx.lineTo(CENTER_X, FLOOR_BOTTOM - 54);
      ctx.lineTo(DRAIN_RIGHT + 42, FLOOR_BOTTOM - 16);
      ctx.lineTo(DRAIN_RIGHT, FLOOR_BOTTOM + 10);
      ctx.lineTo(DRAIN_LEFT, FLOOR_BOTTOM + 10);
      ctx.closePath();
      ctx.fill();

      ctx.fillStyle = COLORS.parchment;
      ctx.font = "600 18px Trebuchet MS";
      ctx.fillText("LEFT ORBIT", FLOOR_LEFT + 60, 372);
      ctx.fillText("RIGHT ORBIT", MAIN_RIGHT - 160, 372);
      ctx.fillText("LAUNCH", PLUNGER_LEFT + 4, 146);
      ctx.fillText("ARCANE DRAIN", CENTER_X - 72, FLOOR_BOTTOM - 4);

      this.drawBoss();
      this.drawRunes();
      this.drawBraziers();
      this.drawSentries();
      this.drawPosts();
      this.drawFlipper(this.leftFlipper);
      this.drawFlipper(this.rightFlipper);
      this.drawBall();
      this.drawEffects();
      ctx.restore();
    }

    drawBoss() {
      const core = this.table.core;
      const hot = this.vulnerableTimer > 0 || this.runes.every(Boolean);
      ctx.save();
      ctx.translate(core.x, core.y);
      ctx.shadowColor = hot ? "rgba(255, 125, 77, 0.7)" : "rgba(184, 78, 255, 0.5)";
      ctx.shadowBlur = hot ? 26 : 18;
      ctx.fillStyle = hot ? "rgba(255, 125, 77, 0.35)" : "rgba(184, 78, 255, 0.22)";
      ctx.beginPath();
      ctx.arc(0, 0, core.r + 18 + Math.sin(this.titlePulse * 3) * 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.shadowBlur = 0;
      ctx.strokeStyle = hot ? COLORS.ember : COLORS.boss;
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.arc(0, 0, core.r, 0, Math.PI * 2);
      ctx.stroke();

      ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(0, 0, core.r + 18, Math.PI * 0.1, Math.PI * 1.9);
      ctx.stroke();

      ctx.fillStyle = hot ? COLORS.ember : COLORS.parchment;
      ctx.font = "800 28px Trebuchet MS";
      ctx.textAlign = "center";
      ctx.fillText(hot ? "BREAK" : "CORE", 0, 10);
      if (hot) {
        ctx.font = "700 16px Trebuchet MS";
        ctx.fillText("VULNERABLE", 0, 34);
      }
      ctx.restore();
    }

    drawRunes() {
      this.table.runes.forEach((rune, index) => {
        const lit = this.runes[index];
        ctx.save();
        ctx.translate(rune.x, rune.y);
        ctx.rotate(this.titlePulse * 0.25 + index * 0.4);
        ctx.strokeStyle = lit ? COLORS.jade : "rgba(255,255,255,0.25)";
        ctx.fillStyle = lit ? "rgba(127, 240, 206, 0.18)" : "rgba(255,255,255,0.05)";
        ctx.lineWidth = 3;
        ctx.beginPath();
        for (let side = 0; side < 6; side++) {
          const angle = Math.PI / 3 * side;
          const x = Math.cos(angle) * rune.r;
          const y = Math.sin(angle) * rune.r;
          if (side === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = lit ? COLORS.jade : COLORS.parchment;
        ctx.font = "800 24px Trebuchet MS";
        ctx.textAlign = "center";
        ctx.fillText(rune.letter, 0, 9);
        ctx.restore();
      });
    }

    drawBraziers() {
      this.table.braziers.forEach((brazier) => {
        ctx.save();
        ctx.translate(brazier.x, brazier.y);
        ctx.fillStyle = "rgba(255, 125, 77, 0.14)";
        ctx.beginPath();
        ctx.arc(0, 0, brazier.r + 18, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = COLORS.emberDim;
        ctx.beginPath();
        ctx.arc(0, 0, brazier.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = COLORS.gold;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(0, 0, brazier.r - 4, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = COLORS.gold;
        ctx.beginPath();
        ctx.moveTo(-12, 6);
        ctx.quadraticCurveTo(0, -18 - Math.sin(this.titlePulse * 5 + brazier.x) * 6, 12, 6);
        ctx.quadraticCurveTo(0, -6, -12, 6);
        ctx.fill();
        ctx.restore();
      });
    }

    drawSentries() {
      this.table.sentries.forEach((sentry) => {
        if (!sentry.alive) {
          return;
        }
        ctx.save();
        ctx.translate(sentry.x, sentry.y);
        ctx.fillStyle = "rgba(183, 216, 255, 0.12)";
        ctx.beginPath();
        ctx.arc(0, 0, sentry.r + 16, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = COLORS.frost;
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.arc(0, 0, sentry.r, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = COLORS.frost;
        ctx.font = "800 18px Trebuchet MS";
        ctx.textAlign = "center";
        ctx.fillText("X", 0, 7);
        ctx.restore();
      });
    }

    drawPosts() {
      ctx.fillStyle = COLORS.parchment;
      this.table.posts.forEach((post) => {
        ctx.beginPath();
        ctx.arc(post.x, post.y, post.r, 0, Math.PI * 2);
        ctx.fill();
      });
    }

    drawFlipper(flipper) {
      const segment = this.getFlipperSegment(flipper);
      const dx = segment.x2 - segment.x1;
      const dy = segment.y2 - segment.y1;
      const angle = Math.atan2(dy, dx);
      ctx.save();
      ctx.translate(segment.x1, segment.y1);
      ctx.rotate(angle);
      const length = Math.hypot(dx, dy);
      roundRectPath(ctx, 0, -14, length, 28, 14);
      const gradient = ctx.createLinearGradient(0, 0, length, 0);
      gradient.addColorStop(0, "#ffe4a0");
      gradient.addColorStop(0.45, COLORS.gold);
      gradient.addColorStop(1, COLORS.goldDeep);
      ctx.fillStyle = gradient;
      ctx.fill();
      ctx.strokeStyle = "rgba(20, 20, 20, 0.28)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(0, 0, 16, 0, Math.PI * 2);
      ctx.fillStyle = COLORS.parchment;
      ctx.fill();
      ctx.restore();
    }

    drawBall() {
      if (!this.ball) {
        return;
      }
      this.ballTrail.forEach((point, index) => {
        const t = (index + 1) / this.ballTrail.length;
        ctx.fillStyle = `rgba(255, 255, 255, ${t * 0.22})`;
        ctx.beginPath();
        ctx.arc(point.x, point.y, this.ball.r * t * 0.9, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.save();
      ctx.shadowColor = "rgba(255, 255, 255, 0.7)";
      ctx.shadowBlur = 18;
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(this.ball.x, this.ball.y, this.ball.r, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    drawEffects() {
      this.particles.forEach((particle) => {
        ctx.globalAlpha = clamp(particle.life * 1.8, 0, 1);
        ctx.fillStyle = particle.color;
        ctx.beginPath();
        ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.globalAlpha = 1;

      this.floatingTexts.forEach((item) => {
        ctx.globalAlpha = clamp(item.life * 1.3, 0, 1);
        ctx.fillStyle = item.color;
        ctx.font = "800 20px Trebuchet MS";
        ctx.textAlign = "center";
        ctx.fillText(item.text, item.x, item.y);
      });
      ctx.globalAlpha = 1;
    }

    drawHud() {
      roundRectPath(ctx, 24, 18, WIDTH - 48, 60, 22);
      ctx.fillStyle = "rgba(8, 15, 23, 0.82)";
      ctx.fill();
      ctx.strokeStyle = "rgba(255, 207, 104, 0.22)";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = COLORS.parchment;
      ctx.font = "700 22px Trebuchet MS";
      ctx.fillText(`Floor ${this.floor}`, 54, 56);
      ctx.fillText(`Gold ${this.gold}`, 186, 56);
      ctx.fillText(`Mana ${this.mana}/${MAX_MANA}`, 326, 56);

      ctx.fillText("HP", 470, 56);
      for (let i = 0; i < this.maxHp; i++) {
        ctx.fillStyle = i < this.hp ? COLORS.ember : "rgba(255,255,255,0.12)";
        ctx.beginPath();
        ctx.moveTo(522 + i * 28, 47);
        ctx.arc(516 + i * 28, 47, 6, 0, Math.PI * 2);
        ctx.arc(528 + i * 28, 47, 6, 0, Math.PI * 2);
        ctx.lineTo(522 + i * 28, 62);
        ctx.closePath();
        ctx.fill();
      }

      ctx.fillStyle = COLORS.parchment;
      ctx.font = "700 18px Trebuchet MS";
      ctx.fillText(this.boss.name.toUpperCase(), 710, 42);
      roundRectPath(ctx, 660, 48, 330, 16, 8);
      ctx.fillStyle = "rgba(255,255,255,0.08)";
      ctx.fill();
      roundRectPath(ctx, 660, 48, 330 * (this.boss.hp / this.boss.maxHp), 16, 8);
      ctx.fillStyle = this.vulnerableTimer > 0 ? COLORS.ember : COLORS.boss;
      ctx.fill();

      const relicText = this.relics.slice(-3).map((relic) => relic.name).join("  |  ") || "No relics yet";
      ctx.fillStyle = "rgba(242, 234, 216, 0.74)";
      ctx.font = "600 15px Trebuchet MS";
      ctx.textAlign = "right";
      ctx.fillText(relicText, WIDTH - 54, 56);

      if (this.mode === "playing" && this.messageTimer > 0) {
        ctx.textAlign = "center";
        ctx.font = "800 24px Trebuchet MS";
        ctx.fillStyle = this.vulnerableTimer > 0 ? COLORS.ember : COLORS.gold;
        ctx.fillText(this.message, WIDTH * 0.5, 106);
      }
      ctx.textAlign = "left";
    }

    drawTitleOverlay() {
      roundRectPath(ctx, 422, 162, 436, 366, 28);
      ctx.fillStyle = "rgba(8, 12, 20, 0.76)";
      ctx.fill();
      ctx.strokeStyle = "rgba(255, 207, 104, 0.26)";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.textAlign = "center";
      ctx.fillStyle = COLORS.gold;
      ctx.font = "800 20px Trebuchet MS";
      ctx.fillText("RUNEBREAKER", WIDTH * 0.5, 226);

      ctx.fillStyle = COLORS.parchment;
      ctx.font = "600 18px Trebuchet MS";
      ctx.fillText("One ball. One boss. One more floor.", WIDTH * 0.5, 254);

      const lines = [
        "RIGHT SHOT   skill shot + fast start",
        "ORBITS       light I O N and mint gold",
        "SENTRIES     drop mana and treasure",
        "HOT CORE     deal boss damage",
        "E            cast Arcane Surge",
        "",
        "SPACE to start   A / D or arrows to flip",
        "1 2 3 pick relics   F fullscreen",
      ];

      ctx.font = "600 17px Trebuchet MS";
      ctx.fillStyle = "rgba(242, 234, 216, 0.86)";
      lines.forEach((line, index) => {
        ctx.fillText(line, WIDTH * 0.5, 310 + index * 30);
      });
      ctx.textAlign = "left";
    }

    drawRewardOverlay() {
      ctx.fillStyle = "rgba(0, 0, 0, 0.42)";
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      ctx.textAlign = "center";
      ctx.fillStyle = COLORS.gold;
      ctx.font = "800 34px Trebuchet MS";
      ctx.fillText("Citadel floor broken", WIDTH * 0.5, 156);
      ctx.fillStyle = COLORS.parchment;
      ctx.font = "600 18px Trebuchet MS";
      ctx.fillText("Choose one relic and descend deeper.", WIDTH * 0.5, 186);

      const cardY = 232;
      const cardW = 282;
      const gap = 26;
      const startX = (WIDTH - (cardW * 3 + gap * 2)) * 0.5;
      this.rewardCards = [];

      this.relicOptions.forEach((relic, index) => {
        const x = startX + index * (cardW + gap);
        this.rewardCards.push({ x, y: cardY, w: cardW, h: 264, index });
        roundRectPath(ctx, x, cardY, cardW, 264, 24);
        ctx.fillStyle = index === 1 ? "rgba(255, 207, 104, 0.18)" : "rgba(17, 27, 40, 0.94)";
        ctx.fill();
        ctx.strokeStyle = "rgba(255, 207, 104, 0.26)";
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = COLORS.gold;
        ctx.font = "700 18px Trebuchet MS";
        ctx.fillText(`[${index + 1}]`, x + cardW * 0.5, cardY + 42);
        ctx.fillStyle = COLORS.parchment;
        ctx.font = "800 28px Trebuchet MS";
        ctx.fillText(relic.name, x + cardW * 0.5, cardY + 98);
        ctx.font = "600 18px Trebuchet MS";
        wrapText(ctx, relic.text, x + 32, cardY + 146, cardW - 64, 26);
      });

      ctx.textAlign = "left";
    }

    drawGameOverOverlay() {
      ctx.fillStyle = "rgba(0, 0, 0, 0.48)";
      ctx.fillRect(0, 0, WIDTH, HEIGHT);
      roundRectPath(ctx, 450, 204, 380, 268, 28);
      ctx.fillStyle = "rgba(14, 20, 30, 0.92)";
      ctx.fill();
      ctx.strokeStyle = "rgba(255, 125, 77, 0.24)";
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.textAlign = "center";
      ctx.fillStyle = COLORS.ember;
      ctx.font = "800 34px Trebuchet MS";
      ctx.fillText("Run over", WIDTH * 0.5, 264);
      ctx.fillStyle = COLORS.parchment;
      ctx.font = "600 20px Trebuchet MS";
      ctx.fillText(`You reached floor ${this.floor}`, WIDTH * 0.5, 308);
      ctx.fillText(`Gold ${this.gold}   Score ${this.score}`, WIDTH * 0.5, 340);
      ctx.fillText(`Relics ${this.relics.length}`, WIDTH * 0.5, 372);
      ctx.fillStyle = COLORS.gold;
      ctx.fillText("Press SPACE to try again", WIDTH * 0.5, 426);
      ctx.textAlign = "left";
    }

    render() {
      ctx.clearRect(0, 0, WIDTH, HEIGHT);
      this.drawBackground();
      this.drawTable();
      this.drawHud();
      if (this.mode === "title") {
        this.drawTitleOverlay();
      } else if (this.mode === "reward") {
        this.drawRewardOverlay();
      } else if (this.mode === "gameover") {
        this.drawGameOverOverlay();
      }
    }

    renderToText() {
      return JSON.stringify({
        mode: this.mode,
        note: "origin top-left; x increases right; y increases down",
        floor: this.floor,
        player: {
          hp: this.hp,
          maxHp: this.maxHp,
          gold: this.gold,
          mana: this.mana,
          relics: this.relics.map((relic) => relic.id),
        },
        boss: {
          name: this.boss.name,
          hp: this.boss.hp,
          maxHp: this.boss.maxHp,
          vulnerable: this.vulnerableTimer > 0 || this.runes.every(Boolean),
        },
        runes: this.table.runes.map((rune, index) => ({ letter: rune.letter, lit: this.runes[index] })),
        ball: this.ball
          ? {
              x: Math.round(this.ball.x),
              y: Math.round(this.ball.y),
              vx: Math.round(this.ball.vx),
              vy: Math.round(this.ball.vy),
              inLaunchLane: this.ballInLaunchLane,
              ballSave: Number(this.ballSaveTimer.toFixed(2)),
              skillShot: Number(this.skillShotTimer.toFixed(2)),
            }
          : null,
        sentries: this.table.sentries.map((sentry) => ({
          x: sentry.x,
          y: sentry.y,
          alive: sentry.alive,
          respawn: Number(sentry.respawn.toFixed(2)),
        })),
        message: this.message,
      });
    }
  }

  function wrapText(context, text, x, y, maxWidth, lineHeight) {
    const words = text.split(" ");
    let line = "";
    let lineY = y;
    for (const word of words) {
      const next = line ? `${line} ${word}` : word;
      if (context.measureText(next).width > maxWidth && line) {
        context.fillText(line, x + maxWidth * 0.5, lineY);
        line = word;
        lineY += lineHeight;
      } else {
        line = next;
      }
    }
    if (line) {
      context.fillText(line, x + maxWidth * 0.5, lineY);
    }
  }

  const game = new RunebreakerGame(ctx, canvas);
  window.advanceTime = async (ms) => {
    game.advance(ms);
  };
  window.render_game_to_text = () => game.renderToText();
})();
