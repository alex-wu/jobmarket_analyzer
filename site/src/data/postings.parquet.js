import {fileURLToPath} from "node:url";
import {dirname, resolve, join} from "node:path";
import {readFileSync, mkdtempSync, rmSync} from "node:fs";
import {tmpdir} from "node:os";
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

const tmp = mkdtempSync(join(tmpdir(), "postings-loader-"));
const out = join(tmp, "out.parquet").replaceAll("\\", "/");

const instance = await DuckDBInstance.create(":memory:");
const conn = await instance.connect();

// Cast posted_at TIMESTAMPTZ -> TIMESTAMP so duckdb-wasm avoids the
// date_trunc(TIMESTAMPTZ) overload gap (see pitfall_duckdb_date_trunc_tz).
// SNAPPY (not ZSTD) for the broadest duckdb-wasm reader compat across
// browsers; the size delta on ~24-40 KB is negligible.
await conn.run(`
  COPY (
    SELECT
      title,
      company,
      country,
      posted_at::TIMESTAMP AS posted_at,
      posting_url,
      salary_annual_eur_p50,
      salary_imputed,
      salary_period,
      isco_code,
      isco_match_method,
      isco_match_score,
      CASE WHEN isco_code IS NULL THEN NULL ELSE SUBSTR(isco_code, 1, 1) END AS isco_major,
      source
    FROM read_parquet('${sqlSrc}')
    WHERE salary_annual_eur_p50 IS NULL OR salary_annual_eur_p50 > 0
  )
  TO '${out}' (FORMAT PARQUET, COMPRESSION SNAPPY);
`);

conn.closeSync();
instance.closeSync();

process.stdout.write(readFileSync(out));
rmSync(tmp, {recursive: true, force: true});
