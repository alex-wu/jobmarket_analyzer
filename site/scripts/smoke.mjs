// Headless browser smoke test.
// Phase 1: dev server (127.0.0.1:3000) — single page render + filter interaction + narrow viewport
// Phase 2: static dist/ (served on 127.0.0.1:4173 with /jobmarket_analyzer/ base) — verify the prod build
import puppeteer from "puppeteer";
import http from "node:http";
import {readFile} from "node:fs/promises";
import {extname, join, resolve} from "node:path";

const MIMES = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".parquet": "application/octet-stream",
  ".wasm": "application/wasm",
  ".svg": "image/svg+xml",
  ".png": "image/png"
};

async function staticServer(root, port, basePrefix) {
  const absRoot = resolve(root);
  return new Promise((resolveSrv) => {
    const srv = http.createServer(async (req, res) => {
      let p = decodeURI(req.url.split("?")[0]);
      if (basePrefix && p.startsWith(basePrefix)) p = p.slice(basePrefix.length - 1);
      if (p === "/" || p === "") p = "/index.html";
      if (!extname(p)) p = `${p}.html`;
      const full = join(absRoot, p);
      try {
        const data = await readFile(full);
        res.writeHead(200, {"content-type": MIMES[extname(full)] ?? "application/octet-stream"});
        res.end(data);
      } catch {
        res.writeHead(404).end(`not found: ${p}`);
      }
    });
    srv.listen(port, "127.0.0.1", () => resolveSrv(srv));
  });
}

function attachListeners(page) {
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(`${err.name}: ${err.message}`));
  page.on("requestfailed", (req) => failedRequests.push(`${req.method()} ${req.url()} — ${req.failure()?.errorText}`));
  return {consoleErrors, pageErrors, failedRequests};
}

async function collectVisibleErrors(page) {
  return await page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll(".observablehq--error, .observablehq--inspect-error, pre.observablehq--inspect")) {
      const txt = el.textContent.trim();
      if (/error|TypeError|RuntimeError|ReferenceError|SyntaxError/i.test(txt)) out.push(txt.slice(0, 300));
    }
    return out;
  });
}

async function checkPage(browser, url, {viewport, label} = {}) {
  const page = await browser.newPage();
  if (viewport) await page.setViewport(viewport);
  else await page.setViewport({width: 1280, height: 900});
  const {consoleErrors, pageErrors, failedRequests} = attachListeners(page);
  console.log(`\n=== ${label ?? url} ===`);
  try {
    await page.goto(url, {waitUntil: "networkidle0", timeout: 30000});
    await new Promise((r) => setTimeout(r, 1500));
    const visible = await collectVisibleErrors(page);
    const issues = consoleErrors.length + pageErrors.length + visible.length;
    if (issues === 0 && failedRequests.length === 0) console.log("OK — no errors, no failed requests");
    else {
      if (pageErrors.length)     console.log("pageerror:", pageErrors);
      if (consoleErrors.length)  console.log("console.error:", consoleErrors);
      if (visible.length)        console.log("visible inspector errors:", visible);
      if (failedRequests.length) console.log("failed requests:", failedRequests);
    }
    return {page, issues: issues + failedRequests.length, consoleErrors, pageErrors};
  } catch (err) {
    console.log("NAV FAILED:", err.message);
    return {page, issues: 1};
  }
}

// SMOKE_PHASE selects which phases run. Default "all" (local dev). CI sets "dist".
//   "all"  — Phase 1 (dev server) + Phase 2 (static dist/)
//   "dev"  — Phase 1 only (no dist build required)
//   "dist" — Phase 2 only (no dev server required; safe in CI after `npm run build`)
const phase = (process.env.SMOKE_PHASE ?? "all").toLowerCase();
const runDev = phase === "all" || phase === "dev";
const runDist = phase === "all" || phase === "dist";

const browser = await puppeteer.launch({headless: true, args: ["--no-sandbox"]});
let total = 0;

// ---------- Phase 1: dev server, single page ----------
if (runDev) {
  const devPort = process.env.DEV_PORT ?? "3000";
  const devOrigin = `http://127.0.0.1:${devPort}`;
  {
    const {page, issues} = await checkPage(browser, `${devOrigin}/`, {label: "dev /"});
    total += issues;
    await page.close();
  }

  // Phase 1b: filter interaction on /
  {
    console.log("\n=== / filter interaction ===");
    const page = await browser.newPage();
    await page.setViewport({width: 1280, height: 900});
    const {consoleErrors, pageErrors, failedRequests} = attachListeners(page);
    await page.goto(`${devOrigin}/`, {waitUntil: "networkidle0", timeout: 30000});
    await new Promise((r) => setTimeout(r, 1500));
    // change the first select (Country)
    const changed = await page.evaluate(() => {
      const select = document.querySelector('select');
      if (!select) return false;
      const opts = Array.from(select.options).map((o) => o.value);
      const target = opts.find((v) => v && v !== "(all)") ?? opts[0];
      select.value = target;
      select.dispatchEvent(new Event("input", {bubbles: true}));
      select.dispatchEvent(new Event("change", {bubbles: true}));
      return target;
    });
    console.log(`changed country to: ${changed}`);
    await new Promise((r) => setTimeout(r, 2500));
    const visible = await collectVisibleErrors(page);
    const issues = consoleErrors.length + pageErrors.length + visible.length;
    if (issues === 0 && failedRequests.length === 0) console.log("OK — filter re-render clean");
    else {
      if (pageErrors.length)     console.log("pageerror:", pageErrors);
      if (consoleErrors.length)  console.log("console.error:", consoleErrors);
      if (visible.length)        console.log("visible inspector errors:", visible);
      if (failedRequests.length) console.log("failed requests:", failedRequests);
    }
    total += issues + failedRequests.length;
    await page.close();
  }

  // Phase 1c: narrow viewport
  {
    const {page, issues} = await checkPage(browser, `${devOrigin}/`, {viewport: {width: 375, height: 667}, label: "/ @ 375px"});
    total += issues;
    await page.close();
  }
}

// ---------- Phase 2: static dist/ with /jobmarket_analyzer/ base ----------
if (runDist) {
  const distSrv = await staticServer("dist", 4173, "/jobmarket_analyzer/");
  console.log("\n--- static dist/ server up on :4173 ---");
  {
    const url = "http://127.0.0.1:4173/jobmarket_analyzer/";
    const {page, issues} = await checkPage(browser, url, {label: "dist /"});
    total += issues;
    await page.close();
  }
  distSrv.close();
}

await browser.close();
console.log(`\n=== TOTAL ISSUES: ${total} ===`);
process.exit(total > 0 ? 1 : 0);
