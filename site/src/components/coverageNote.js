import {html} from "npm:htl";

// Renders the coverage banner from the manifest + live counts.
//
//   manifest: parsed manifest.json — postings.row_count is the *fresh* weekly
//             fetch; postings.accumulated_row_count (ADR-020) is the full
//             snapshot the dashboard queries. country_counts and
//             isco_match_method_counts describe the fresh fetch only.
//   live: optional {n, nSalary, nIsco} object from a live filter query
export function coverageNote(manifest, live) {
  const p = manifest?.postings ?? {};
  const fresh = p.row_count ?? 0;
  const total = p.accumulated_row_count ?? fresh;
  const windowDays = p.accumulate_window_days;
  const countries = p.country_counts ?? {};
  const iscoCounts = p.isco_match_method_counts ?? {};
  const iscoHit = Object.entries(iscoCounts)
    .filter(([k]) => k !== "none")
    .reduce((a, [, v]) => a + v, 0);

  const pct = (num, den) => (den > 0 ? `${Math.round((num / den) * 100)}%` : "—");
  const countryList = Object.entries(countries)
    .map(([k, v]) => `${k} ${v.toLocaleString()}`)
    .join(" · ");

  const liveLine = live
    ? html` <small
        >Current filter: <strong>${live.n.toLocaleString()}</strong> postings
        (${pct(live.nSalary ?? 0, live.n)} with salary,
        ${pct(live.nIsco ?? 0, live.n)} ISCO-tagged).</small
      >`
    : "";

  return html`<div>
    <strong>Coverage:</strong> ${total.toLocaleString()} postings in this snapshot${
      windowDays ? html` (${windowDays}-day accumulation window)` : ""
    }. This week's fetch added ${fresh.toLocaleString()} (${countryList});
    ${pct(iscoHit, fresh)} of those carry an ISCO code (rapidfuzz tagger, cutoff 85).<br />
    <small
      >Salary, work-arrangement and skill coverage vary by country — see
      <a href="./quality">Quality &amp; Coverage</a>.</small
    >
    ${liveLine}
  </div>`;
}
