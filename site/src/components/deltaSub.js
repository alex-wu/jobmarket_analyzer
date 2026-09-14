// Delta sub-line for a KPI card: "<label>: <a> · ▲ <move>".
//
// `kind: "pp"` renders the move in percentage points (shares/rates, a and b in
// 0–1); `kind: "pct"` renders relative change (counts, medians). Sign is always
// shown. `label` names the baseline ("prior", "Jan–Mar", …); `missing` overrides
// the text when there is no baseline at all (default: "<label>: —").
export function deltaSub(a, b, {kind, fmt = String, label = "prior", missing} = {}) {
  if (a == null) return missing ?? `${label}: —`;
  if (b == null) return `${label}: ${fmt(a)}`;
  const arrow = b > a ? "▲" : b < a ? "▼" : "＝";
  const sign = b - a >= 0 ? "+" : "";
  const move = kind === "pp"
    ? `${sign}${((b - a) * 100).toFixed(1)} pp`
    : a === 0 ? "n/a" : `${sign}${Math.round(((b - a) / a) * 100)}%`;
  return `${label}: ${fmt(a)} · ${arrow} ${move}`;
}
