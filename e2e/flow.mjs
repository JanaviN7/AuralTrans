// End-to-end browser test against the REAL stack and the REAL language model configured in
// backend/.env: upload -> processing -> workspace -> Insights -> cited Ask -> abstention ->
// citation seek -> reload/history -> stale insights -> delete.
//
// Assertions are structural and checked against the API's own transcript, never exact model
// wording, so they hold for any competent model. See e2e/README.md.
import { spawn, execSync } from "node:child_process";
import { mkdirSync, openSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..");
const OUT = path.resolve(process.env.E2E_OUT ?? path.join(HERE, "out"));
const SHOTS = process.env.E2E_SHOTS ? path.resolve(process.env.E2E_SHOTS) : path.join(OUT, "shots");
mkdirSync(SHOTS, { recursive: true });
const BASE = "http://127.0.0.1:5173";
const API = "http://127.0.0.1:8765";
const PYTHON = process.env.PYTHON ?? "python";
const env = { ...process.env, ASR_MODEL: process.env.ASR_MODEL ?? "tiny", PYTHONWARNINGS: "ignore", HF_HUB_DISABLE_SYMLINKS_WARNING: "1" };

const children = [];
const start = (cmd, args, cwd, name) => {
  const log = openSync(path.join(OUT, `${name}.log`), "w");
  children.push(spawn(cmd, args, { cwd, env, stdio: ["ignore", log, log], windowsHide: true }));
};
const stopAll = () =>
  children.forEach((p) => {
    try {
      execSync(process.platform === "win32" ? `taskkill /pid ${p.pid} /T /F` : `kill -9 -${p.pid}`, { stdio: "ignore" });
    } catch {}
  });
const results = [];
const check = (name, ok, detail = "") => {
  results.push(!!ok);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  -> " + detail : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const getJson = async (u) => (await fetch(u)).json();
async function waitFor(url, ms = 90000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { if ((await fetch(url)).ok) return true; } catch {}
    await sleep(400);
  }
  return false;
}
const norm = (t) => t.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
const shot = (page, name, full = false) => page.screenshot({ path: path.join(SHOTS, name), fullPage: full });
const uv = (...args) => [`-m`, `uv`, `run`, `--extra`, `speech`, ...args];

let browser, recId;
try {
  mkdirSync(OUT, { recursive: true });
  const backend = path.join(REPO, "backend");
  start(PYTHON, uv("uvicorn", "auraltrans.api.app:app", "--port", "8765"), backend, "api");
  start(PYTHON, uv("python", "-m", "auraltrans.worker"), backend, "worker");
  start("node", [path.join(REPO, "web", "node_modules", "vite", "bin", "vite.js"), "--host", "127.0.0.1", "--port", "5173", "--strictPort"], path.join(REPO, "web"), "vite");
  check("servers start", (await waitFor(API + "/api/health")) && (await waitFor(BASE + "/api/health")));
  const health = await getJson(BASE + "/api/health");
  check("language model configured (Insights and Ask enabled)", health.features.insights && health.features.ask, "set LLM_* in backend/.env");
  if (!(health.features.insights && health.features.ask)) throw new Error("no language model configured");

  browser = await chromium.launch(process.env.E2E_BROWSER ? { channel: process.env.E2E_BROWSER, headless: true } : { headless: true });
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const problems = [];
  page.on("console", (m) => m.type() === "error" && problems.push("console: " + m.text()));
  page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
  page.on("response", (r) => r.status() >= 400 && problems.push(`HTTP ${r.status()}: ${r.url()}`));

  // ---------- Library -> New recording -> upload -> processing -> workspace ----------
  await page.goto(BASE + "/");
  await page.waitForSelector(".empty, .rec");
  await shot(page, "01-library.png");
  await page.click("text=New recording");
  await page.waitForSelector(".dropzone");
  await page.locator("[data-testid=file-input]").setInputFiles(path.join(HERE, "fixtures", "conversation.wav"));
  await page.fill("label:has-text('Title') input", "Product launch Q&A");
  await shot(page, "02-new-recording.png");
  await page.click("button[type=submit]");
  await page.waitForURL(/\/recordings\/[0-9a-f-]+$/);
  recId = page.url().split("/").pop();
  await page.waitForSelector(".steps");
  check("processing page shows 5 stages", (await page.locator(".step").count()) === 5);
  let shotProcessing = false;
  const t0 = Date.now();
  while (Date.now() - t0 < 600000 && !(await page.locator("[role=tablist]").count())) {
    if (!shotProcessing && (await page.locator(".step.running").count()) && (await page.locator(".step.done").count())) {
      await shot(page, "03-processing.png");
      shotProcessing = true;
    }
    await sleep(400);
  }
  check("workspace opens automatically after processing", (await page.locator("[role=tablist]").count()) === 1, `${Math.round((Date.now() - t0) / 1000)}s`);
  await page.waitForSelector(".utt");
  const tr = await getJson(`${API}/api/recordings/${recId}/transcript`);
  const byUid = new Map(tr.utterances.map((u) => [u.uid, u]));
  check("transcript has speaker-labelled utterances", tr.utterances.length >= 2 && (await page.locator(".utt .speaker-label").count()) === tr.utterances.length, `${tr.utterances.length} utterances, ${tr.speakers.length} speakers`);
  await page.waitForSelector("audio", { state: "attached" });
  await page.waitForFunction(() => document.querySelector("audio")?.readyState >= 1);

  // synchronized playback: the active utterance follows the playhead
  await page.waitForFunction(() => document.querySelector("audio")?.readyState >= 3, null, { timeout: 30000 });
  await page.click("button[aria-label=Play]");
  const playing = await page
    .waitForFunction(() => document.querySelector("audio").currentTime > 0.5 && document.querySelector("audio").currentTime, null, { timeout: 15000 })
    .then((h) => h.jsonValue())
    .catch(() => 0);
  check("playback advances and highlights the active utterance", playing > 0.5 && (await page.locator(".utt.active").count()) >= 1, `t=${playing.toFixed(1)}s`);
  await shot(page, "04-transcript-playing.png");
  await page.click("button[aria-label=Pause]");

  await page.click("[role=tab]:has-text('Speakers')");
  await page.waitForSelector(".speaker-card");
  check("speakers tab shows per-speaker analytics", (await page.locator(".speaker-card").count()) === tr.speakers.length);
  await shot(page, "05-speakers.png");

  // ---------- Insights ----------
  await page.click("[role=tab]:has-text('Insights')");
  await page.waitForSelector("button:has-text('Generate insights')");
  const tg = Date.now();
  await page.click("button:has-text('Generate insights')");
  await page.waitForSelector(".insights .summary-card", { timeout: 180000 });
  console.log(`      insights generated in ${((Date.now() - tg) / 1000).toFixed(1)}s`);
  const ins = await getJson(`${API}/api/recordings/${recId}/insights`);
  check("insights finished with the configured model and are not stale", ins.status === "done" && ins.stale === false, `${ins.status} ${ins.model}`);
  check("summary is non-empty and cites real utterances", ins.data.summary?.text.length > 10 && ins.data.summary.evidence.length >= 1 && ins.data.summary.evidence.every((e) => byUid.has(e.utterance_id)));
  const allEvidence = [...(ins.data.key_points ?? []), ...(ins.data.decisions ?? []), ...(ins.data.open_questions ?? []), ...(ins.data.action_items ?? [])].flatMap((i) => i.evidence);
  check("every citation in every section resolves to a real utterance", allEvidence.length >= 1 && allEvidence.every((e) => byUid.has(e.utterance_id)), `${allEvidence.length} citations`);
  check("chapters reference real, ordered utterances", ins.data.chapters.length >= 1 && ins.data.chapters.every((c) => byUid.has(c.start_uid) && byUid.has(c.end_uid) && byUid.get(c.start_uid).idx <= byUid.get(c.end_uid).idx));
  check("validation report is present", ins.validation && "sections" in ins.validation, JSON.stringify({ chunks: ins.validation.chunks, repaired: ins.validation.repaired_calls }));
  check("UI renders evidence chips", (await page.locator(".ev-chip").count()) >= 1);
  await shot(page, "06-insights.png", true);

  const lastCited = byUid.get(ins.data.summary.evidence.at(-1).utterance_id);
  await page.evaluate(() => { document.querySelector("audio").currentTime = 0; });
  await page.locator(".summary-card .ev-chip").last().click();
  await sleep(500);
  const t = await page.evaluate(() => document.querySelector("audio").currentTime);
  check("evidence chip seeks to the cited utterance", Math.abs(t - lastCited.start_s) < 1.5, `cited ${lastCited.uid} at ${lastCited.start_s.toFixed(2)}s, player at ${t.toFixed(2)}s`);
  await page.click("button[aria-label=Pause]").catch(() => {});

  // ---------- Ask ----------
  await page.click("[role=tab]:has-text('Ask')");
  await page.waitForSelector(".ask");
  check("Ask starts empty", (await page.locator(".qa").count()) === 0);
  const ask = async (q) => {
    const n = await page.locator(".qa").count();
    await page.fill("input[aria-label=Question]", q);
    await page.click(".ask-form button");
    await page.waitForFunction((k) => document.querySelectorAll(".qa").length > k && !document.querySelector(".thinking"), n, { timeout: 180000 });
    return page.locator(".qa").last();
  };

  const q1 = await ask("What does air pollution mean?");
  check("grounded question is answered with citations", (await q1.locator(".a.abstain").count()) === 0 && (await q1.locator(".cite").count()) >= 1);
  const t1 = (await getJson(`${API}/api/recordings/${recId}/ask`)).at(-1);
  check("every citation quote occurs in the cited utterance", t1.citations.length >= 1 && t1.citations.every((c) => norm(byUid.get(c.uid).text).includes(norm(c.quote).split(" ").slice(0, 4).join(" "))), t1.citations.map((c) => `${c.uid}:"${c.quote.slice(0, 40)}"`).join(" | "));
  check("answer is non-empty and not the abstain message", t1.answer.length > 5 && !t1.abstained);
  const cite = t1.citations[0];
  await page.evaluate(() => { document.querySelector("audio").currentTime = 14; });
  await sleep(300);
  await q1.locator(".cite").first().click();
  await sleep(500);
  const tc = await page.evaluate(() => document.querySelector("audio").currentTime);
  check("citation click seeks to the cited utterance", Math.abs(tc - cite.start_s) < 1.5, `cite ${cite.uid} at ${cite.start_s.toFixed(2)}s, player ${tc.toFixed(2)}s`);

  const q2 = await ask("What is the annual salary of the company's CEO?");
  check("unsupported question abstains in the UI", (await q2.locator(".a.abstain").count()) === 1 && (await q2.locator(".cite").count()) === 0);
  const t2 = (await getJson(`${API}/api/recordings/${recId}/ask`)).at(-1);
  check("abstention is stored with a reason and no citations", t2.abstained === true && !!t2.abstain_reason && t2.citations.length === 0, t2.abstain_reason);

  await ask("Who will send the report, and by when?");
  const t3 = (await getJson(`${API}/api/recordings/${recId}/ask`)).at(-1);
  check("third question is cited or cleanly abstained, never uncited", t3.abstained ? t3.citations.length === 0 : t3.citations.length >= 1, t3.abstained ? `abstained: ${t3.abstain_reason}` : `answered: ${t3.answer.slice(0, 60)}`);
  await shot(page, "07-ask.png", true);

  // ---------- Reload, history, persistence ----------
  const history = await getJson(`${API}/api/recordings/${recId}/ask`);
  await page.reload();
  await page.click("[role=tab]:has-text('Ask')");
  await page.waitForSelector(".qa");
  check("Q&A history persists across reload (UI matches API)", (await page.locator(".qa").count()) === history.length && history.length === 3, `${history.length} turns`);
  check("history preserves abstentions", (await page.locator(".a.abstain").count()) === history.filter((h) => h.abstained).length);
  await page.click("[role=tab]:has-text('Insights')");
  await page.waitForSelector(".insights .summary-card");
  const ins2 = await getJson(`${API}/api/recordings/${recId}/insights`);
  check("insights persist across reload without regenerating", ins2.version === ins.version && (await page.locator(".summary-card").innerText()).includes(ins.data.summary.text.slice(0, 20)));

  // ---------- Exports, mobile, dark ----------
  await page.click("button:has-text('Export')");
  await page.waitForSelector(".modal");
  await shot(page, "08-export.png");
  await page.keyboard.press("Escape");
  await page.setViewportSize({ width: 390, height: 800 });
  await sleep(300);
  check("no horizontal scroll on a phone-width screen", await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await shot(page, "09-mobile.png");
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ colorScheme: "dark" });
  await sleep(200);
  await shot(page, "10-insights-dark.png");
  await page.emulateMedia({ colorScheme: "light" });

  // ---------- Editing the transcript marks insights stale ----------
  const first = tr.utterances[0];
  const res = await fetch(`${API}/api/utterances/${first.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: first.text + " Edited." }) });
  check("transcript edit is accepted", res.ok);
  await page.reload();
  await page.click("[role=tab]:has-text('Insights')");
  await page.waitForSelector(".notice");
  check("insights are flagged stale after a transcript edit", /edited after these insights/.test(await page.locator(".notice").innerText()));

  check("no console errors or failed responses during the whole flow", problems.length === 0, problems.join(" | "));
} catch (e) {
  console.log("TEST ERROR:", e.message.split("\n")[0]);
  results.push(false);
} finally {
  try {
    if (recId) {
      const d = await fetch(`${API}/api/recordings/${recId}`, { method: "DELETE" });
      const gone = await fetch(`${API}/api/recordings/${recId}`);
      check("delete removes the recording (204, then 404)", d.status === 204 && gone.status === 404, `DELETE ${d.status}, GET ${gone.status}`);
    }
  } catch (e) {
    check("delete cleanup", false, e.message);
  }
  await browser?.close();
  stopAll();
  const passed = results.filter(Boolean).length;
  console.log(`\n${passed}/${results.length} checks passed`);
  process.exitCode = passed === results.length ? 0 : 1;
}
