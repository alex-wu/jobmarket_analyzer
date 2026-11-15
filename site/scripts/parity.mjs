// Parity check for the browser SQL backend (ADR-027).
//
// Runs the dashboard's representative queries twice — the original DuckDB SQL
// over the release parquet, and the ported SQLite SQL over the database the
// loader builds — and fails if any result differs. Run after touching
// src/data/postings.db.js, components/db.js, or any page query:
//
//   npm run parity
import {execFileSync} from "node:child_process";
import {mkdtempSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname, join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {DatabaseSync} from "node:sqlite";
import {DuckDBInstance} from "@duckdb/node-api";
import {medianOf} from "../src/components/median.js";

const here = dirname(fileURLToPath(import.meta.url));
const loader = resolve(here, "../src/data/postings.db.js");
const source = resolve(here, "../../data/gh_databuild_samples/latest-data_analyst_eu.parquet").replaceAll("\\", "/");

// --- SQLite side: build the database exactly as the site build does ---------
const tmp = mkdtempSync(join(tmpdir(), "parity-"));
const dbPath = join(tmp, "postings.db");
writeFileSync(dbPath, execFileSync(process.execPath, [loader], {maxBuffer: 1 << 28, stdio: ["ignore", "pipe", "ignore"]}));
const sqlite = new DatabaseSync(dbPath);
sqlite.aggregate("median", {
  start: () => [],
  step: (state, value) => (state.push(value), state),
  result: (state) => medianOf(state)
});

// --- DuckDB side: the table the old in-browser client saw --------------------
const instance = await DuckDBInstance.create(":memory:");
const duck = await instance.connect();
await duck.run(`SET TimeZone = 'UTC'`); // duckdb-wasm ran without ICU, i.e. UTC
await duck.run(`
  CREATE TABLE postings AS
  SELECT title, company, country, posted_at, posting_url, salary_annual_eur_p50,
         salary_imputed, salary_period, isco_code, isco_match_method, isco_match_score,
         CASE WHEN isco_code IS NULL THEN NULL ELSE SUBSTR(isco_code, 1, 1) END AS isco_major,
         source, work_arrangement, skills
  FROM read_parquet('${source}')
  WHERE salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 > 0
`);

// Filter variants: [label, DuckDB WHERE, SQLite WHERE] — same shapes as
// components/filters.js whereClause() emitted before / emits now.
const FILTERS = [
  ["no filter", "", ""],
  ["country", "WHERE country = 'GB'", "WHERE country = 'GB'"],
  [
    "country+isco+arrangement+salary+dates",
    `WHERE country = 'ES' AND isco_major = '2' AND work_arrangement IS NULL
       AND (salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 >= 20000)
       AND (salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 <= 90000)
       AND posted_at >= TIMESTAMP '2026-03-01 00:00:00' AND posted_at <= TIMESTAMP '2026-08-15 00:00:00'`,
    `WHERE country = 'ES' AND isco_major = '2' AND work_arrangement IS NULL
       AND (salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 >= 20000)
       AND (salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 <= 90000)
       AND posted_at >= '2026-03-01 00:00:00.000000' AND posted_at <= '2026-08-15 00:00:00.000000'`
  ],
  [
    "dates only",
    `WHERE posted_at >= TIMESTAMP '2026-06-01 00:00:00' AND posted_at <= TIMESTAMP '2026-09-14 00:00:00'`,
    `WHERE posted_at >= '2026-06-01 00:00:00.000000' AND posted_at <= '2026-09-14 00:00:00.000000'`
  ]
];
const and = (w) => (w ? `${w} AND` : "WHERE");
const JOIN = "posting_skills JOIN postings ON postings.id = posting_skills.posting_id";

// Each case: name + (where) => [DuckDB SQL, SQLite SQL]. Every query carries a
// total ORDER BY so row order is comparable.
const perFilter = [
  ["coverage counts", (d, s) => [
    `SELECT COUNT(*)::INT AS n, COUNT(salary_annual_eur_p50)::INT AS n_salary, COUNT(isco_code)::INT AS n_isco,
            SUM(CASE WHEN salary_imputed THEN 1 ELSE 0 END)::INT AS n_imputed, COUNT(work_arrangement)::INT AS classified
     FROM postings ${d}`,
    `SELECT COUNT(*) AS n, COUNT(salary_annual_eur_p50) AS n_salary, COUNT(isco_code) AS n_isco,
            SUM(CASE WHEN salary_imputed THEN 1 ELSE 0 END) AS n_imputed, COUNT(work_arrangement) AS classified
     FROM postings ${s}`
  ]],
  ...["week", "month", "quarter"].map((g) => [`${g} buckets (pulse/trends)`, (d, s) => [
    `SELECT date_trunc('${g}', posted_at::TIMESTAMP)::DATE::VARCHAR AS bucket, COUNT(*)::INT AS n,
            COUNT(salary_annual_eur_p50)::INT AS n_salary, MEDIAN(salary_annual_eur_p50) AS med_salary,
            COUNT(work_arrangement)::INT AS n_arr,
            COUNT(*) FILTER (WHERE work_arrangement = 'remote')::INT AS n_remote,
            COUNT(*) FILTER (WHERE work_arrangement = 'hybrid')::INT AS n_hybrid,
            COUNT(*) FILTER (WHERE work_arrangement = 'onsite')::INT AS n_onsite
     FROM postings ${and(d)} posted_at IS NOT NULL GROUP BY 1 ORDER BY 1`,
    `SELECT posted_${g} AS bucket, COUNT(*) AS n,
            COUNT(salary_annual_eur_p50) AS n_salary, median(salary_annual_eur_p50) AS med_salary,
            COUNT(work_arrangement) AS n_arr,
            COUNT(*) FILTER (WHERE work_arrangement = 'remote') AS n_remote,
            COUNT(*) FILTER (WHERE work_arrangement = 'hybrid') AS n_hybrid,
            COUNT(*) FILTER (WHERE work_arrangement = 'onsite') AS n_onsite
     FROM postings ${and(s)} posted_at IS NOT NULL GROUP BY 1 ORDER BY 1`
  ]]),
  ["overview pulse (complete weeks)", (d, s) => [
    `SELECT date_trunc('week', posted_at::TIMESTAMP)::DATE::VARCHAR AS wk, COUNT(*)::INT AS n, MEDIAN(salary_annual_eur_p50) AS med_salary
     FROM postings ${and(d)} posted_at IS NOT NULL
       AND posted_at::TIMESTAMP < (SELECT date_trunc('week', MAX(posted_at)::TIMESTAMP) FROM postings)
     GROUP BY 1 ORDER BY 1 DESC LIMIT 2`,
    `SELECT posted_week AS wk, COUNT(*) AS n, median(salary_annual_eur_p50) AS med_salary
     FROM postings ${and(s)} posted_at IS NOT NULL
       AND posted_week < (SELECT MAX(posted_week) FROM postings)
     GROUP BY 1 ORDER BY 1 DESC LIMIT 2`
  ]],
  ["weekly volume by country", (d, s) => [
    `SELECT date_trunc('week', posted_at::TIMESTAMP)::DATE::VARCHAR AS wk, country, COUNT(*)::INT AS n
     FROM postings ${and(d)} posted_at IS NOT NULL AND country IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2`,
    `SELECT posted_week AS wk, country, COUNT(*) AS n
     FROM postings ${and(s)} posted_at IS NOT NULL AND country IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2`
  ]],
  ["monthly median salary by country (HAVING)", (d, s) => [
    `SELECT date_trunc('month', posted_at::TIMESTAMP)::DATE::VARCHAR AS bucket, country,
            COUNT(salary_annual_eur_p50)::INT AS n_sal, MEDIAN(salary_annual_eur_p50) AS med
     FROM postings ${and(d)} posted_at IS NOT NULL AND country IS NOT NULL
     GROUP BY 1, 2 HAVING COUNT(salary_annual_eur_p50) >= 3 ORDER BY 1, 2`,
    `SELECT posted_month AS bucket, country, COUNT(salary_annual_eur_p50) AS n_sal, median(salary_annual_eur_p50) AS med
     FROM postings ${and(s)} posted_at IS NOT NULL AND country IS NOT NULL
     GROUP BY 1, 2 HAVING COUNT(salary_annual_eur_p50) >= 3 ORDER BY 1, 2`
  ]],
  ["salary histogram rows", (d, s) => [
    `SELECT salary_annual_eur_p50 AS salary FROM postings ${and(d)} salary_annual_eur_p50 IS NOT NULL ORDER BY 1`,
    `SELECT salary_annual_eur_p50 AS salary FROM postings ${and(s)} salary_annual_eur_p50 IS NOT NULL ORDER BY 1`
  ]],
  ["geography by country", (d, s) => [
    `SELECT country, COUNT(*)::INT AS n, quantile_cont(salary_annual_eur_p50, 0.5) AS p50
     FROM postings ${and(d)} country IS NOT NULL GROUP BY 1 ORDER BY 1`,
    `SELECT country, COUNT(*) AS n, median(salary_annual_eur_p50) AS p50
     FROM postings ${and(s)} country IS NOT NULL GROUP BY 1 ORDER BY 1`
  ]],
  ["arrangement share by country (window)", (d, s) => [
    `SELECT country, COALESCE(work_arrangement, 'unknown') AS arrangement, COUNT(*)::INT AS n,
            COUNT(*)::DOUBLE / SUM(COUNT(*)) OVER (PARTITION BY country) AS share
     FROM postings ${and(d)} country IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2`,
    `SELECT country, COALESCE(work_arrangement, 'unknown') AS arrangement, COUNT(*) AS n,
            CAST(COUNT(*) AS REAL) / SUM(COUNT(*)) OVER (PARTITION BY country) AS share
     FROM postings ${and(s)} country IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2`
  ]],
  ["title counts", (d, s) => [
    `SELECT title, COUNT(*)::INT AS n FROM postings ${and(d)} title IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1`,
    `SELECT title, COUNT(*) AS n FROM postings ${and(s)} title IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1`
  ]],
  ["skill counts (unnest vs posting_skills)", (d, s) => [
    `SELECT skill, COUNT(*)::INT AS n FROM (SELECT unnest(skills) AS skill FROM postings ${d}) GROUP BY 1 ORDER BY 2 DESC, 1`,
    `SELECT skill, COUNT(*) AS n FROM ${JOIN} ${s} GROUP BY 1 ORDER BY 2 DESC, 1`
  ]],
  ["skill counts per month", (d, s) => [
    `SELECT bucket, skill, COUNT(*)::INT AS n
     FROM (SELECT date_trunc('month', posted_at::TIMESTAMP)::DATE::VARCHAR AS bucket, unnest(skills) AS skill
           FROM postings ${and(d)} posted_at IS NOT NULL)
     GROUP BY 1, 2 ORDER BY 1, 2`,
    `SELECT posted_month AS bucket, skill, COUNT(*) AS n
     FROM ${JOIN} ${and(s)} posted_at IS NOT NULL GROUP BY 1, 2 ORDER BY 1, 2`
  ]],
  ["country x ISCO median heatmap", (d, s) => [
    `SELECT country, isco_major, quantile_cont(salary_annual_eur_p50, 0.5) AS p50, COUNT(salary_annual_eur_p50)::INT AS n
     FROM postings ${and(d)} salary_annual_eur_p50 IS NOT NULL AND isco_major IS NOT NULL
     GROUP BY 1, 2 HAVING COUNT(*) >= 3 ORDER BY 1, 2`,
    `SELECT country, isco_major, median(salary_annual_eur_p50) AS p50, COUNT(salary_annual_eur_p50) AS n
     FROM postings ${and(s)} salary_annual_eur_p50 IS NOT NULL AND isco_major IS NOT NULL
     GROUP BY 1, 2 HAVING COUNT(*) >= 3 ORDER BY 1, 2`
  ]],
  ["ISCO mix + match method + source", (d, s) => [
    `SELECT COALESCE(isco_major, '∅') AS isco_major, COALESCE(isco_match_method, 'none') AS method, source, COUNT(*)::INT AS n
     FROM postings ${d} GROUP BY 1, 2, 3 ORDER BY 1, 2, 3`,
    `SELECT COALESCE(isco_major, '∅') AS isco_major, COALESCE(isco_match_method, 'none') AS method, source, COUNT(*) AS n
     FROM postings ${s} GROUP BY 1, 2, 3 ORDER BY 1, 2, 3`
  ]],
  ["postings table (all rows, all columns)", (d, s) => [
    `SELECT title, company, country, strftime(posted_at::TIMESTAMP, '%Y-%m-%d %H:%M:%S.%f') AS posted_at,
            salary_annual_eur_p50, salary_imputed::INT AS salary_imputed, salary_period,
            isco_code, isco_major, isco_match_method, isco_match_score, source, work_arrangement, posting_url
     FROM postings ${d} ORDER BY posted_at DESC NULLS LAST, posting_url, title, company`,
    `SELECT title, company, country, posted_at,
            salary_annual_eur_p50, salary_imputed, salary_period,
            isco_code, isco_major, isco_match_method, isco_match_score, source, work_arrangement, posting_url
     FROM postings ${s} ORDER BY posted_at DESC NULLS LAST, posting_url, title, company`
  ]]
];

// Compare-page cases (no filter card): two periods per granularity.
const compareCases = [];
for (const g of ["week", "month", "quarter"]) {
  const ids = sqlite.prepare(`SELECT DISTINCT posted_${g} AS b FROM postings WHERE posted_at IS NOT NULL ORDER BY 1`).all().map((r) => r.b);
  const [a, b] = [ids.at(-2) ?? ids.at(-1), ids.at(-1)];
  const dExpr = `date_trunc('${g}', posted_at::TIMESTAMP)::DATE`;
  const dIn = `${dExpr} IN (DATE '${a}', DATE '${b}')`;
  const dCase = `CASE WHEN ${dExpr} = DATE '${a}' THEN 'A' ELSE 'B' END`;
  const sIn = `posted_${g} IN ('${a}', '${b}')`;
  const sCase = `CASE WHEN posted_${g} = '${a}' THEN 'A' ELSE 'B' END`;
  compareCases.push(
    [`compare ${g} bucket list`, [
      `SELECT ${dExpr}::VARCHAR AS bucket, COUNT(*)::INT AS n FROM postings WHERE posted_at IS NOT NULL GROUP BY 1 ORDER BY 1`,
      `SELECT posted_${g} AS bucket, COUNT(*) AS n FROM postings WHERE posted_at IS NOT NULL GROUP BY 1 ORDER BY 1`
    ]],
    [`compare ${g} KPIs ${a} vs ${b}`, [
      `SELECT ${dCase} AS period, COUNT(*)::INT AS n, COUNT(salary_annual_eur_p50)::INT AS n_salary,
              MEDIAN(salary_annual_eur_p50) AS med_salary, COUNT(work_arrangement)::INT AS n_arr,
              COUNT(*) FILTER (WHERE work_arrangement = 'remote')::INT AS n_remote
       FROM postings WHERE posted_at IS NOT NULL AND ${dIn} GROUP BY 1 ORDER BY 1`,
      `SELECT ${sCase} AS period, COUNT(*) AS n, COUNT(salary_annual_eur_p50) AS n_salary,
              median(salary_annual_eur_p50) AS med_salary, COUNT(work_arrangement) AS n_arr,
              COUNT(*) FILTER (WHERE work_arrangement = 'remote') AS n_remote
       FROM postings WHERE posted_at IS NOT NULL AND ${sIn} GROUP BY 1 ORDER BY 1`
    ]],
    [`compare ${g} skills`, [
      `SELECT period, skill, COUNT(*)::INT AS n
       FROM (SELECT ${dCase} AS period, unnest(skills) AS skill FROM postings WHERE posted_at IS NOT NULL AND ${dIn})
       GROUP BY 1, 2 ORDER BY 1, 2`,
      `SELECT ${sCase} AS period, skill, COUNT(*) AS n FROM ${JOIN}
       WHERE posted_at IS NOT NULL AND ${sIn} GROUP BY 1, 2 ORDER BY 1, 2`
    ]],
    [`compare ${g} ISCO + arrangement mix`, [
      `SELECT ${dCase} AS period, CASE WHEN isco_code IS NULL THEN NULL ELSE SUBSTR(isco_code, 1, 1) END AS isco_major,
              COALESCE(work_arrangement, 'unknown') AS arrangement, COUNT(*)::INT AS n
       FROM postings WHERE posted_at IS NOT NULL AND ${dIn} GROUP BY 1, 2, 3 ORDER BY 1, 2 NULLS FIRST, 3`,
      `SELECT ${sCase} AS period, CASE WHEN isco_code IS NULL THEN NULL ELSE SUBSTR(isco_code, 1, 1) END AS isco_major,
              COALESCE(work_arrangement, 'unknown') AS arrangement, COUNT(*) AS n
       FROM postings WHERE posted_at IS NOT NULL AND ${sIn} GROUP BY 1, 2, 3 ORDER BY 1, 2 NULLS FIRST, 3`
    ]],
    [`compare ${g} median salary by country`, [
      `SELECT ${dCase} AS period, country, COUNT(salary_annual_eur_p50)::INT AS n_sal, MEDIAN(salary_annual_eur_p50) AS med
       FROM postings WHERE posted_at IS NOT NULL AND country IS NOT NULL AND ${dIn}
       GROUP BY 1, 2 HAVING COUNT(salary_annual_eur_p50) >= 3 ORDER BY 1, 2`,
      `SELECT ${sCase} AS period, country, COUNT(salary_annual_eur_p50) AS n_sal, median(salary_annual_eur_p50) AS med
       FROM postings WHERE posted_at IS NOT NULL AND country IS NOT NULL AND ${sIn}
       GROUP BY 1, 2 HAVING COUNT(salary_annual_eur_p50) >= 3 ORDER BY 1, 2`
    ]]
  );
}

const singles = [
  ["bootstrap: countries", [
    `SELECT DISTINCT country FROM postings WHERE country IS NOT NULL ORDER BY 1`,
    `SELECT DISTINCT country FROM postings WHERE country IS NOT NULL ORDER BY 1`
  ]],
  ["bootstrap: ISCO majors", [
    `SELECT DISTINCT isco_major FROM postings WHERE isco_major IS NOT NULL ORDER BY 1`,
    `SELECT DISTINCT isco_major FROM postings WHERE isco_major IS NOT NULL ORDER BY 1`
  ]],
  ["bootstrap: date span", [
    `SELECT strftime(MIN(posted_at)::TIMESTAMP, '%Y-%m-%d %H:%M:%S.%f') AS lo, strftime(MAX(posted_at)::TIMESTAMP, '%Y-%m-%d %H:%M:%S.%f') AS hi FROM postings WHERE posted_at IS NOT NULL`,
    `SELECT MIN(posted_at) AS lo, MAX(posted_at) AS hi FROM postings WHERE posted_at IS NOT NULL`
  ]],
  ...["week", "month"].map((g) => [`trends cutoff bucket (${g})`, [
    `SELECT date_trunc('${g}', MAX(posted_at)::TIMESTAMP)::DATE::VARCHAR AS bucket FROM postings`,
    `SELECT MAX(posted_${g}) AS bucket FROM postings`
  ]])
];

// --- compare -----------------------------------------------------------------
const TOL = 1e-9;
function same(a, b) {
  if (a == null || b == null) return a == null && b == null;
  if (typeof a === "bigint") a = Number(a);
  if (typeof b === "bigint") b = Number(b);
  if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) <= TOL * Math.max(1, Math.abs(a), Math.abs(b));
  return String(a) === String(b);
}

let failures = 0;
let checked = 0;
async function check(name, [duckSql, sqliteSql]) {
  const reader = await duck.runAndReadAll(duckSql);
  const cols = reader.columnNames();
  const d = reader.getRows();
  const s = sqlite.prepare(sqliteSql).all().map((r) => cols.map((c) => r[c]));
  checked++;
  let problem = null;
  if (d.length !== s.length) problem = `row count ${d.length} (duckdb) vs ${s.length} (sqlite)`;
  else {
    outer: for (let i = 0; i < d.length; i++) {
      for (let j = 0; j < cols.length; j++) {
        if (!same(d[i][j], s[i][j])) {
          problem = `row ${i} col ${cols[j]}: ${String(d[i][j])} (duckdb) vs ${String(s[i][j])} (sqlite)`;
          break outer;
        }
      }
    }
  }
  if (problem) failures++;
  console.log(`${problem ? "FAIL" : "ok  "}  ${name}  [${d.length} rows]${problem ? `  — ${problem}` : ""}`);
}

for (const [name, sql] of singles) await check(name, sql);
for (const [label, d, s] of FILTERS) {
  for (const [name, make] of perFilter) await check(`${name}  {${label}}`, make(d, s));
}
for (const [name, sql] of compareCases) await check(name, sql);

sqlite.close();
duck.closeSync();
instance.closeSync();
rmSync(tmp, {recursive: true, force: true});

console.log(`\n=== parity: ${checked - failures}/${checked} queries identical ===`);
process.exit(failures > 0 ? 1 : 0);
