// Build-time loader: release parquet -> SQLite database for the browser (ADR-027).
//
// DuckDB (Node, build-time only) does the projection and every dialect-sensitive
// derivation — period buckets, UTC text timestamps, skills un-nesting — so the
// browser's SQLite (sql.js) only ever runs portable SQL over plain columns.
import {fileURLToPath} from "node:url";
import {dirname, resolve, join} from "node:path";
import {readFileSync, mkdtempSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
import {DatabaseSync} from "node:sqlite";
import {DuckDBInstance} from "@duckdb/node-api";

const __dirname = dirname(fileURLToPath(import.meta.url));
// Adapter to the post-ADR-019 release asset name. Multi-preset enumeration
// (and the preset switcher) is queued — see reference_phase_status. Until
// then, this loader hardcodes the v1 preset. Run-time: change the constant.
const PRESET_ID = "data_analyst_eu";
const SOURCE = resolve(
  __dirname,
  `../../../data/gh_databuild_samples/latest-${PRESET_ID}.parquet`,
);
const sqlSrc = SOURCE.replaceAll("\\", "/");

const instance = await DuckDBInstance.create(":memory:");
const conn = await instance.connect();

// posted_at is TIMESTAMPTZ; pin the session zone so ::TIMESTAMP is UTC on every
// build machine (the buckets must not depend on the builder's local time zone).
await conn.run(`SET TimeZone = 'UTC'`);

await conn.run(`
  CREATE TEMP TABLE src AS
  SELECT row_number() OVER () AS id, *
  FROM read_parquet('${sqlSrc}')
  WHERE salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 > 0
`);

// Fixed-width 'YYYY-MM-DD HH:MM:SS.ffffff' text sorts and compares exactly like
// the timestamp it encodes; period buckets are 'YYYY-MM-DD' (ISO week = Monday).
const postings = await conn.runAndReadAll(`
  SELECT
    id::INTEGER AS id,
    title,
    company,
    country,
    strftime(posted_at::TIMESTAMP, '%Y-%m-%d %H:%M:%S.%f') AS posted_at,
    strftime(date_trunc('week', posted_at::TIMESTAMP), '%Y-%m-%d') AS posted_week,
    strftime(date_trunc('month', posted_at::TIMESTAMP), '%Y-%m-%d') AS posted_month,
    strftime(date_trunc('quarter', posted_at::TIMESTAMP), '%Y-%m-%d') AS posted_quarter,
    posting_url,
    salary_annual_eur_p50::DOUBLE AS salary_annual_eur_p50,
    salary_imputed::INTEGER AS salary_imputed,
    salary_period,
    isco_code,
    isco_match_method,
    isco_match_score::DOUBLE AS isco_match_score,
    CASE WHEN isco_code IS NULL THEN NULL ELSE SUBSTR(isco_code, 1, 1) END AS isco_major,
    source,
    work_arrangement
  FROM src
  ORDER BY id
`);

const skills = await conn.runAndReadAll(`
  SELECT posting_id::INTEGER AS posting_id, skill
  FROM (SELECT id AS posting_id, unnest(skills) AS skill FROM src)
  ORDER BY posting_id
`);

const postingCols = postings.columnNames();
const postingRows = postings.getRows();
const skillRows = skills.getRows();

conn.closeSync();
instance.closeSync();

const tmp = mkdtempSync(join(tmpdir(), "postings-loader-"));
const out = join(tmp, "out.db");
const db = new DatabaseSync(out);

db.exec(`
  CREATE TABLE postings (
    id INTEGER PRIMARY KEY,
    title TEXT,
    company TEXT,
    country TEXT,
    posted_at TEXT,
    posted_week TEXT,
    posted_month TEXT,
    posted_quarter TEXT,
    posting_url TEXT,
    salary_annual_eur_p50 REAL,
    salary_imputed INTEGER,
    salary_period TEXT,
    isco_code TEXT,
    isco_match_method TEXT,
    isco_match_score REAL,
    isco_major TEXT,
    source TEXT,
    work_arrangement TEXT
  );
  CREATE TABLE posting_skills (
    posting_id INTEGER NOT NULL REFERENCES postings(id),
    skill TEXT
  );
`);

const insertPosting = db.prepare(
  `INSERT INTO postings (${postingCols.join(", ")}) VALUES (${postingCols.map(() => "?").join(", ")})`,
);
const insertSkill = db.prepare(`INSERT INTO posting_skills (posting_id, skill) VALUES (?, ?)`);

db.exec("BEGIN");
for (const row of postingRows) insertPosting.run(...row);
for (const row of skillRows) insertSkill.run(...row);
db.exec("COMMIT");

// No secondary indexes: at this row count full scans are sub-millisecond and
// indexes would only inflate the download.
db.exec("VACUUM");
db.close();

process.stdout.write(readFileSync(out));
rmSync(tmp, {recursive: true, force: true});
