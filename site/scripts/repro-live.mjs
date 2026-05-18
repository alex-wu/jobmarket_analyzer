// One-shot diagnostic to reproduce the TProtocolException reported on the live site.
// Loads alex-wu.github.io/jobmarket_analyzer/ with extended wait + verbose listeners.
import puppeteer from "puppeteer";

const URL = process.argv[2] || "https://alex-wu.github.io/jobmarket_analyzer/";
console.log("target:", URL);

const browser = await puppeteer.launch({headless: true, args: ["--no-sandbox"]});
const page = await browser.newPage();

const consoleAll = [];
const errors = [];
page.on("console", (m) => consoleAll.push(`[${m.type()}] ${m.text()}`));
page.on("pageerror", (e) => errors.push(`pageerror: ${e.name}: ${e.message}`));
page.on("requestfailed", (r) => errors.push(`reqfailed: ${r.method()} ${r.url()} -- ${r.failure()?.errorText}`));

await page.goto(URL, {waitUntil: "networkidle0", timeout: 60000});
console.log("--- networkidle0 ---");
await new Promise((r) => setTimeout(r, 6000));
console.log("--- +6s wait ---");

const visible = await page.evaluate(() => {
  const out = [];
  document.querySelectorAll(".observablehq--error, .observablehq--inspect-error, pre.observablehq--inspect").forEach((el) => {
    const t = el.textContent.trim();
    if (/error|Exception|Invalid/i.test(t)) out.push(t.slice(0, 500));
  });
  return out;
});

console.log("\n=== CONSOLE ===");
for (const c of consoleAll) console.log(c);
console.log("\n=== ERRORS ===");
for (const e of errors) console.log(e);
console.log("\n=== VISIBLE ERROR NODES ===");
for (const v of visible) console.log(v);

await browser.close();
