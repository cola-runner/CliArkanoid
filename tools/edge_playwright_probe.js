import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

function parseArgs(argv) {
  const args = {
    url: null,
    actionsFile: null,
    screenshotDir: "output/web-game",
    iterations: 1,
    pauseMs: 250,
    headless: true,
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--url" && next) {
      args.url = next;
      i++;
    } else if (arg === "--actions-file" && next) {
      args.actionsFile = next;
      i++;
    } else if (arg === "--screenshot-dir" && next) {
      args.screenshotDir = next;
      i++;
    } else if (arg === "--iterations" && next) {
      args.iterations = Number.parseInt(next, 10) || 1;
      i++;
    } else if (arg === "--pause-ms" && next) {
      args.pauseMs = Number.parseInt(next, 10) || 250;
      i++;
    } else if (arg === "--headless" && next) {
      args.headless = next !== "0" && next !== "false";
      i++;
    }
  }

  if (!args.url) {
    throw new Error("--url is required");
  }
  if (!args.actionsFile) {
    throw new Error("--actions-file is required");
  }
  return args;
}

const KEY_MAP = {
  left: "ArrowLeft",
  right: "ArrowRight",
  up: "ArrowUp",
  down: "ArrowDown",
  space: "Space",
  a: "KeyA",
  d: "KeyD",
  e: "KeyE",
  one: "Digit1",
  two: "Digit2",
  three: "Digit3",
};

async function doSteps(page, steps) {
  for (const step of steps) {
    const buttons = step.buttons || [];
    for (const button of buttons) {
      const key = KEY_MAP[button];
      if (key) {
        await page.keyboard.down(key);
      }
    }

    const frames = step.frames || 1;
    for (let i = 0; i < frames; i++) {
      await page.evaluate(async () => {
        if (typeof window.advanceTime === "function") {
          await window.advanceTime(1000 / 60);
        }
      });
    }

    for (const button of buttons) {
      const key = KEY_MAP[button];
      if (key) {
        await page.keyboard.up(key);
      }
    }
  }
}

async function main() {
  const args = parseArgs(process.argv);
  const outDir = path.resolve(args.screenshotDir);
  fs.mkdirSync(outDir, { recursive: true });
  const actions = JSON.parse(fs.readFileSync(args.actionsFile, "utf8"));
  const steps = Array.isArray(actions) ? actions : actions.steps;

  const browser = await chromium.launch({
    executablePath: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    headless: args.headless,
    args: ["--use-angle=swiftshader"],
  });

  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push({ type: "console", text: msg.text() });
    }
  });
  page.on("pageerror", (err) => {
    errors.push({ type: "pageerror", text: String(err) });
  });

  await page.goto(args.url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(300);

  for (let i = 0; i < args.iterations; i++) {
    await doSteps(page, steps);
    await page.waitForTimeout(args.pauseMs);
    await page.screenshot({ path: path.join(outDir, `shot-${i}.png`), fullPage: true });
    const state = await page.evaluate(() => {
      if (typeof window.render_game_to_text === "function") {
        return window.render_game_to_text();
      }
      return null;
    });
    if (state) {
      fs.writeFileSync(path.join(outDir, `state-${i}.json`), state);
    }
  }

  if (errors.length) {
    fs.writeFileSync(path.join(outDir, "errors.json"), JSON.stringify(errors, null, 2));
  }

  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
