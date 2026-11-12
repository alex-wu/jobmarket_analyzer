import {FileAttachment} from "observablehq:stdlib";
import {SQLiteDatabaseClient} from "npm:@observablehq/sqlite";
import {medianOf} from "./median.js";

// In-browser SQL backend (ADR-027): SQLite via sql.js — one small wasm, no
// workers, no extensions. The database file is built by data/postings.db.js.
//
// SQLite has no date or boolean types, so the loader stores timestamps and
// period buckets as UTC text and booleans as 0/1. `query` converts the columns
// named below back to the JS types the charts and tables expect; pass
// {dates: [...]} / {bools: [...]} to override per query.
const DATE_COLUMNS = ["posted_at", "wk", "bucket", "lo", "hi"];
const BOOL_COLUMNS = ["salary_imputed"];
const PERIOD_COLUMNS = {week: "posted_week", month: "posted_month", quarter: "posted_quarter"};

// 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS[.ffffff]' (UTC) -> Date. Built by hand
// because the space-separated form is not portable through `new Date(string)`.
export function toDate(s) {
  if (s == null) return null;
  if (s instanceof Date) return s;
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?)?/.exec(String(s));
  if (!m) return null;
  const ms = m[7] ? +m[7].padEnd(3, "0") : 0;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] ?? 0), +(m[5] ?? 0), +(m[6] ?? 0), ms));
}

// Pre-computed period-bucket column for a granularity (replaces date_trunc).
export function periodColumn(granularity) {
  const col = PERIOD_COLUMNS[granularity];
  if (!col) throw new Error(`unknown granularity: ${granularity}`);
  return col;
}

function convert(rows, {dates = DATE_COLUMNS, bools = BOOL_COLUMNS} = {}) {
  const cols = rows.columns ?? (rows.length ? Object.keys(rows[0]) : []);
  const dateCols = cols.filter((c) => dates.includes(c));
  const boolCols = cols.filter((c) => bools.includes(c));
  if (dateCols.length || boolCols.length) {
    for (const r of rows) {
      for (const c of dateCols) r[c] = toDate(r[c]);
      for (const c of boolCols) r[c] = r[c] == null ? null : Boolean(r[c]);
    }
  }
  return rows;
}

let clientPromise;

// Open the postings database once per page. Returns {query, queryRow}: query
// resolves to an array of plain row objects, queryRow to the first row or null.
export function openDb() {
  clientPromise ??= SQLiteDatabaseClient.open(FileAttachment("../data/postings.db")).then((client) => {
    client._db.create_aggregate("median", {
      init: () => [],
      step: (state, value) => (state.push(value), state),
      finalize: (state) => medianOf(state)
    });
    return {
      query: async (sql, opts) => convert(await client.query(sql), opts),
      queryRow: async (sql, opts) => convert(await client.query(sql), opts)[0] ?? null
    };
  });
  return clientPromise;
}

// The filter-card bootstrap every filtered page needs: distinct countries,
// ISCO major groups present, and the posted_at span (as Dates).
export async function loadBootstrap(db) {
  const countries = (await db.query(`SELECT DISTINCT country FROM postings WHERE country IS NOT NULL ORDER BY 1`)).map((r) => r.country);
  const iscoPresent = (await db.query(`SELECT DISTINCT isco_major FROM postings WHERE isco_major IS NOT NULL ORDER BY 1`)).map((r) => r.isco_major);
  const allDates = await db.queryRow(`SELECT MIN(posted_at) AS lo, MAX(posted_at) AS hi FROM postings WHERE posted_at IS NOT NULL`);
  return {countries, iscoPresent, allDates};
}
