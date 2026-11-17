// Render the system diagram and capture storyboard screens from the running prototype, using
// headless Microsoft Edge through the Chrome DevTools Protocol. Node 22+ (built-in fetch and
// WebSocket); no packages.
//
//   node tools/capture.mjs --diagram          docs/system_diagram.svg -> docs/system_diagram.png
//   node tools/capture.mjs --stories          app must run on http://localhost:8020 -> docs/screens/*.png
//   node tools/capture.mjs --stories s2       one story only
//
// The clicks are scripted; every request sends "X-Driver: capture-script", so the session log
// tells these runs apart from a person's. The system's responses on screen are real.

import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const EDGE = process.env.EDGE_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const APP = process.env.APP_URL || "http://localhost:8020";
const PORT = 9333;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Each story is a list of steps: one or more actions by the person, then what is on screen at that moment,
// captured as one frame. The requests are example chips, so the readings are the recorded Gemini replies.
// A frame names the parts of the page it shows: "scope" and "compose" are the Describe step, "request" is
// the request card with its badge (who drafted the rules, and that the reply is a recording), "retained"
// is the "Other answers kept" card that Back and Revisit show. frames.json records what the storyboard
// may leave out (marked) so that every frame keeps the same size: the repeated When / Only if / Then rows
// of a review card, and the scene of a question that an earlier frame already showed.
const STORIES = {
  // B: the Describe step; three readings narrowed by two answers, then a probe for an error all three share.
  s1: [
    { acts: [["example", "B"]], frame: ["scope", "compose"] },
    { acts: [["create"]], frame: ["question"] },
    { acts: [["choice", "question", "yes"], ["choice", "question", "yes"]], frame: ["question"] },
    { acts: [["choice", "question", "yes"]], frame: ["request", "repair"] },
    { acts: [["choice", "repair", "add"]], frame: ["confirm"] },
    { acts: [["choice", "confirm", "save"]], frame: ["saved"] },
  ],
  // E: No, an added arrival rule, Not sure about leaving (the review states the gap); Back to change that
  // answer; then Revisit of the first question, with the later answers kept.
  s2: [
    { acts: [["example", "E"], ["create"]], frame: ["question"] },
    { acts: [["choice", "question", "no"]], frame: ["question"] },
    { acts: [["choice", "question", "yes"], ["choice", "repair", "add"], ["choice", "question", "not_sure"]], frame: ["confirm"] },
    { acts: [["back"], ["choice", "question", "yes"]], frame: ["request", "repair"] },
    { acts: [["choice", "repair", "add"]], frame: ["confirm"] },
    { acts: [["event", "sunset"]], frame: ["retained", "question"] },
  ],
  // F then C: an out-of-scope request is declined. C gets a single reading, which probes still check;
  // the person keeps the light on when leaving, so nothing is added and the review says so.
  s3: [
    { acts: [["example", "F"], ["create"]], frame: ["request", "declined"] },
    { acts: [["choice", "declined", "edit"], ["example", "C"], ["create"]], frame: ["question"] },
    { acts: [["choice", "question", "yes"]], frame: ["repair"] },
    { acts: [["choice", "repair", "add"]], frame: ["question"] },
    { acts: [["choice", "question", "no"]], frame: ["confirm"] },
    { acts: [["choice", "confirm", "save"]], frame: ["saved"] },
  ],
};

async function launch(width, height) {
  const profile = join(os.tmpdir(), `iis-capture-${process.pid}`);
  const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--no-first-run", "--disable-gpu", "--hide-scrollbars", "--remote-allow-origins=*",
    `--window-size=${width},${height}`, "about:blank"], { stdio: "ignore" });
  let target;
  for (let i = 0; i < 60 && !target; i++) {
    await sleep(250);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      target = list.find((t) => t.type === "page");
    } catch { /* not up yet */ }
  }
  if (!target) throw new Error("Edge did not start (set EDGE_PATH if it is installed elsewhere)");
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  let next = 0;
  const pending = new Map();
  const events = [];
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
    else events.forEach((f) => f(msg));
  };
  const send = (method, params = {}) => new Promise((ok, fail) => {
    const id = ++next;
    pending.set(id, (msg) => (msg.error ? fail(new Error(`${method}: ${msg.error.message}`)) : ok(msg.result)));
    ws.send(JSON.stringify({ id, method, params }));
  });
  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", { width, height, deviceScaleFactor: 2, mobile: false });
  // Reduced motion makes the scene animations end at once, so every capture shows the same final frame.
  await send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
  const evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || expression);
    return r.result.value;
  };
  const navigate = async (url) => {
    const loaded = new Promise((ok) => {
      const f = (msg) => { if (msg.method === "Page.loadEventFired") { events.splice(events.indexOf(f), 1); ok(); } };
      events.push(f);
    });
    await send("Page.navigate", { url });
    await loaded;
    await sleep(500);
  };
  const shot = async (file, clip) => {
    const r = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true,
      ...(clip ? { clip: { ...clip, scale: 1 } } : {}) });
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, Buffer.from(r.data, "base64"));
    console.log("wrote", file.slice(ROOT.length + 1));
  };
  const close = async () => {
    try { await send("Browser.close"); } catch { /* already closed */ }
    ws.close();
    edge.kill();
    await sleep(500);
    try { rmSync(profile, { recursive: true, force: true }); } catch { /* left for the OS to clean */ }
  };
  return { evaluate, navigate, shot, close };
}

async function diagram() {
  const b = await launch(940, 1050);
  try {
    const file = join(ROOT, "docs", "system_diagram.svg");
    const [, width, height] = readFileSync(file, "utf8").match(/<svg[^>]* width="(\d+)" height="(\d+)"/).map(Number);
    await b.navigate(pathToFileURL(file).href);
    await b.shot(join(ROOT, "docs", "system_diagram.png"), { x: 0, y: 0, width, height });
  } finally { await b.close(); }
}

const ACT = {
  example: (id) => `document.querySelector('[data-example="${id}"]').click()`,
  type: (text) => `document.querySelector('#req').value = ${JSON.stringify(text)}`,
  create: () => `document.querySelector('#create').click()`,
  choice: (card, value) => `document.querySelector('[data-test="${card}"] button[data-choice="${value}"]').click()`,
  open: (card) => `document.querySelector('[data-test="${card}"] details').open = true`,
  back: () => `document.querySelector('.back-step').click()`,
  // Select an event in the review card's rule: Revisit of the one question asked about that event.
  event: (name) => `document.querySelector('[data-test="confirm"] button[data-event="${name}"]').click()`,
};
const WAITS = new Set(["create", "choice", "back", "event"]);   // actions that call the server and re-render

async function story(b, name, steps, meta) {
  await b.navigate(APP);
  // The page restores its last session from sessionStorage; every story starts from a clean page.
  await b.evaluate("sessionStorage.clear()");
  await b.navigate(APP);
  // Mark every request from this page as scripted, for the session log.
  await b.evaluate(`(() => { const f = window.fetch; window.fetch = (u, o = {}) =>
    f(u, { ...o, headers: { ...(o.headers || {}), "X-Driver": "capture-script" } }); return true; })()`);
  for (const [n, step] of steps.entries()) {
    for (const [kind, ...args] of step.acts) {
      const before = await b.evaluate(`document.querySelector('#thread').innerHTML`);
      await b.evaluate(ACT[kind](...args));
      if (WAITS.has(kind)) {
        for (let i = 0; i < 120; i++) {   // wait for the response to render (a live call can take seconds)
          await sleep(250);
          const ready = await b.evaluate(`!document.querySelector('.spin') && document.querySelector('#thread').innerHTML !== ${JSON.stringify(before)}`);
          if (ready) break;
        }
      }
      await sleep(350);
    }
    const found = await b.evaluate(`(() => {
      window.scrollTo(0, 0);
      const els = ${JSON.stringify(step.frame)}.map((t) => document.querySelector('[data-test="' + t + '"]'))
        .filter((e) => e && e.getBoundingClientRect().height > 0);
      if (!els.length) return null;
      const rs = els.map((e) => e.getBoundingClientRect());
      const top = Math.min(...rs.map((r) => r.top)) - 8, bottom = Math.max(...rs.map((r) => r.bottom)) + 8;
      const left = Math.min(...rs.map((r) => r.left)) - 8, right = Math.max(...rs.map((r) => r.right)) + 8;
      // A review card lists each rule as When / Only if / Then rows, then restates the same rules in a
      // sentence. Record the rows after the first "When" row (which shows that events can be selected to
      // revisit an answer), in CSS px from the frame's top, so the storyboard can leave them out.
      const confirm = els.find((e) => e.dataset.test === "confirm");
      const flows = confirm ? [...confirm.querySelectorAll(".rule-flow")] : [];
      let elide = null;
      if (flows.length) {
        const when = flows[0].children[0].getBoundingClientRect(), next = flows[0].children[1].getBoundingClientRect();
        const last = flows[flows.length - 1].getBoundingClientRect();
        const after = flows[flows.length - 1].nextElementSibling.getBoundingClientRect();
        elide = { from: Math.round((when.bottom + next.top) / 2 - top),
                  to: Math.round((last.bottom + after.top) / 2 - top), rules: flows.length,
                  note: "more When / Only if / Then rows left out here" };
      }
      // A reopened question (Revisit) comes with the "Other answers kept" card. Its scene and facts were
      // shown in an earlier frame, so the storyboard may leave them out to keep the frame size.
      const kept = els.find((e) => e.dataset.test === "retained");
      const asked = els.find((e) => e.dataset.test === "question");
      if (kept && asked) {
        const scene = asked.querySelector(".scene-visual").getBoundingClientRect();
        const facts = asked.querySelector(".scene").getBoundingClientRect();
        elide = { from: Math.round(scene.top - 6 - top), to: Math.round(facts.bottom + 6 - top),
                  note: "scene left out here: the moment of frame 1" };
      }
      // Where a review card speaks about leaving home: the answer line, the "never" note and the last rule.
      // tools/make_storyboards.py outlines and magnifies these on storyboard 2.
      const marks = {};
      if (confirm) {
        const box = (e) => { const r = e.getBoundingClientRect();
          return { x: Math.round(r.left - left), y: Math.round(r.top - top), w: Math.round(r.width), h: Math.round(r.height) }; };
        const leave = [...confirm.querySelectorAll("ul.confirmed li")].find((e) => e.textContent.includes("leave at 23:30"));
        const never = confirm.querySelector(".never");
        const rules = confirm.querySelectorAll(".rule > div");
        if (leave) marks.leave = box(leave);
        if (never) marks.never = box(never);
        if (rules.length) marks.lastrule = box(rules[rules.length - 1]);
      }
      return { clip: { x: left + scrollX, y: top + scrollY, width: right - left, height: bottom - top }, elide, marks };
    })()`);
    if (!found) throw new Error(`${name} step ${n + 1}: none of ${step.frame.join(", ")} is on screen`);
    const file = `${name}_${n + 1}.png`;
    await b.shot(join(ROOT, "docs", "screens", file), found.clip);
    meta[file] = { height: Math.round(found.clip.height), elide: found.elide, marks: found.marks };
  }
}

async function stories(only) {
  const metaFile = join(ROOT, "docs", "screens", "frames.json");
  let meta = {};
  try { meta = JSON.parse(readFileSync(metaFile, "utf8")); } catch { /* first run */ }
  const b = await launch(430, 1600);
  try {
    for (const [name, steps] of Object.entries(STORIES)) {
      if (only && only !== name) continue;
      try {
        await story(b, name, steps, meta);
      } catch (error) {   // a slow response can outrun the waits; one retry from a fresh page
        console.log(`${name} failed (${error.message}); retrying once`);
        await story(b, name, steps, meta);
      }
    }
  } finally { await b.close(); }
  const sorted = Object.fromEntries(Object.keys(meta).sort().map((k) => [k, meta[k]]));
  writeFileSync(metaFile, JSON.stringify(sorted, null, 1) + "\n");
  console.log("wrote", metaFile.slice(ROOT.length + 1));
}

const [flag, arg] = process.argv.slice(2);
if (flag === "--diagram") await diagram();
else if (flag === "--stories") await stories(arg);
else console.log("usage: node tools/capture.mjs --diagram | --stories [name]");
