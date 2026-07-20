import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";

// Sortable/scrollable table inside a card with a "Download CSV" button.
// Path of least resistance — Inputs.table for display, vanilla Blob for export.
// Display formatters do not affect the CSV; CSV always uses raw row values
// for every key present on the first row.
//
//   rows: array of row objects (e.g. Array.from(await db.query(...)))
//   opts:
//     filename  CSV filename when downloaded (default "data.csv")
//     title     card heading (default "Filtered data")
//     subtitle  small string under heading
//     columns   keys to show in the table (passed through to Inputs.table)
//     header    label map (passed through to Inputs.table)
//     format    cell formatter map (display only)
//     width     column-width map (passed through to Inputs.table)
export function dataTable(rows, opts = {}) {
  const {
    filename = "data.csv",
    title = "Filtered data",
    subtitle = null,
    columns,
    header,
    format,
    width
  } = opts;

  const tableOpts = {};
  if (columns) tableOpts.columns = columns;
  if (header) tableOpts.header = header;
  if (format) tableOpts.format = format;
  if (width) tableOpts.width = width;

  const btn = html`<button title="Download CSV of all filtered rows" aria-label="Download CSV" style="border:1px solid var(--theme-foreground-faintest, #ccc);background:transparent;color:inherit;font:inherit;font-size:0.85rem;cursor:pointer;padding:0.25rem 0.6rem;border-radius:4px">⬇ CSV (${rows.length.toLocaleString()})</button>`;
  btn.disabled = rows.length === 0;
  btn.onclick = () => {
    const csv = toCSV(rows);
    const blob = new Blob([csv], {type: "text/csv;charset=utf-8"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 100);
  };

  return html`<div class="card">
    <div style="display:flex;justify-content:space-between;align-items:baseline;gap:0.5rem;margin-bottom:0.25rem">
      <h2 style="margin:0">${title}</h2>
      ${btn}
    </div>
    ${subtitle ? html`<small style="display:block;margin-bottom:0.5rem">${subtitle}</small>` : ""}
    ${rows.length === 0
      ? html`<div>No rows in current selection.</div>`
      : Inputs.table(rows, tableOpts)}
  </div>`;
}

function toCSV(rows) {
  if (rows.length === 0) return "";
  const keys = Object.keys(rows[0]);
  const head = keys.map(csvCell).join(",");
  const body = rows.map((r) => keys.map((k) => csvCell(r[k])).join(",")).join("\n");
  return `${head}\n${body}\n`;
}

function csvCell(v) {
  if (v == null) return "";
  if (v instanceof Date) return v.toISOString();
  if (typeof v === "boolean") return v ? "true" : "false";
  const s = String(v);
  return /[",\n\r]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}
