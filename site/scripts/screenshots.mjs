// README hero screenshots. Serves the built dist/ on 127.0.0.1:4174 (same static
// server as smoke.mjs phase 2) and captures a 1440x900 viewport of selected pages
// into ../docs/img/ — sidebar, TOC and all, exactly as the deployed app renders.
// Each page is scrolled to a heading first so the crop lands on charts, not prose.
// Run `npm run build` first.
//
//   npm run screenshots                            # overview + trends
//   node scripts/screenshots.mjs "/geography#Where"  # any page, optional #heading text
import puppeteer from "puppeteer";
import http from "node:http";
import {mkdir, readFile} from "node:fs/promises";
import {extname, join, resolve} from "node:path";

const PORT = 4174;
const BASE = "/jobmarket_analyzer/";
const OUT_DIR = resolve("..", "docs", "img");
const VIEWPORT = {width: 1440, height: 900, deviceScaleFactor: 2};
const DEFAULT_SHOTS = ["/#Market pulse", "/trends#Volume & pay"];

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

const shots = process.argv.length > 2 ? process.argv.slice(2) : DEFAULT_SHOTS;
await mkdir(OUT_DIR, {recursive: true});
const srv = await staticServer("dist", PORT, BASE);
const browser = await puppeteer.launch({headless: true, args: ["--no-sandbox"]});

for (const shot of shots) {
  const [path, heading] = shot.split("#");
  const name = path === "/" ? "overview" : path.slice(1).replaceAll("/", "-");
  const url = `http://127.0.0.1:${PORT}${BASE}${path === "/" ? "" : path.slice(1)}`;
  const page = await browser.newPage();
  await page.setViewport(VIEWPORT);
  await page.emulateMediaFeatures([{name: "prefers-color-scheme", value: "light"}]);
  await page.goto(url, {waitUntil: "networkidle0", timeout: 60000});
  await new Promise((r) => setTimeout(r, 2500)); // let DuckDB-WASM queries settle
  if (heading) {
    const found = await page.evaluate((text) => {
      const h = Array.from(document.querySelectorAll("#observablehq-main h1, #observablehq-main h2, #observablehq-main h3"))
        .find((el) => el.textContent.trim().startsWith(text));
      if (!h) return false;
      window.scrollTo(0, h.getBoundingClientRect().top + window.scrollY - 24); // ignore scroll-margin-top
      return true;
    }, heading);
    if (!found) throw new Error(`heading "${heading}" not found on ${url}`);
    await new Promise((r) => setTimeout(r, 500));
  }
  const out = join(OUT_DIR, `${name}.png`);
  await page.screenshot({path: out});
  console.log(`${shot} -> ${out} (${VIEWPORT.width}x${VIEWPORT.height} @${VIEWPORT.deviceScaleFactor}x)`);
  await page.close();
}

await browser.close();
srv.close();
