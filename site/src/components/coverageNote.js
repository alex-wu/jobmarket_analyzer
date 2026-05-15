import {html} from "npm:htl";

// Renders the coverage banner from the manifest + live counts.
//
//   manifest: parsed manifest.json (has postings.row_count, country_counts, isco_match_method_counts)
//   live: optional {n, nSalary, nIsco} object from a live filter query
export function coverageNote(manifest, live) {
  const total = manifest?.postings?.row_count ?? 0;
  const countries = manifest?.postings?.country_counts ?? {};
  const iscoCounts = manifest?.postings?.isco_match_method_counts ?? {};
  const iscoHit = Object.entries(iscoCounts)
    .filter(([k]) => k !== "none")
    .reduce((a, [, v]) => a + v, 0);

  const pct = (num, den) => (den > 0 ? `${Math.round((num / den) * 100)}%` : "—");
  const countryList = Object.entries(countries)
    .map(([k, v]) => `${k} ${v}`)
    .join(" · ");

  const liveLine = live
    ? html` <small
        >Current filter: <strong>${live.n}</strong> postings
        (${pct(live.nSalary ?? 0, live.n)} with salary,
        ${pct(live.nIsco ?? 0, live.n)} ISCO-tagged).</small
      >`
    : "";

  return html`<div>
    <strong>Coverage:</strong> ${total} postings in this snapshot (${countryList}).
    ${pct(total, total)} have a posting URL; ${pct(iscoHit, total)} have an ISCO
    code (rapidfuzz tagger, cutoff 85); ~99% disclose a p50 salary after
    EUR-normalisation + imputation.<br />
    <small
      >Not yet captured upstream:
      <code>experience_level</code>, <code>work_arrangement</code>,
      <code>skills</code> — see <a href="#sources">sources &amp; methodology</a> below
      or the
      <a
        href="https://github.com/alex-wu/jobmarket_analyzer/blob/main/docs/dashboard_data_gaps.md"
        >data-gaps roadmap</a
      >.</small
    >
    ${liveLine}
  </div>`;
}
