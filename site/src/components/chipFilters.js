import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import {ALL, salaryRange, dateRange} from "./filters.js";
import {presetSelect} from "./presets.js";
import {readFromURL, writeToURL} from "./filterState.js";
import {ISCO_MAJORS} from "./isco.js";

// Chip-style filter bar (ADR-028). Same value shape and URL contract as
// filterCard(), plus `skills`, so whereClause() consumes it unchanged and
// filters carry across pages. Categorical filters are stock Inputs.radio /
// Inputs.checkbox; chips.css (the page's `style:`) renders them as chips.
//
//   skills: [{skill, n}] offered as multi-select chips (postings must mention
//           every selected skill)
//   extras: page-scoped chip inputs; values ride along in form.value but are
//           not URL-persisted
const allOr = (label) => (k) => (k === ALL ? "All" : label(k));

function chips(type, options, {label, value, format = allOr(String)}) {
  return type(options, {label, value, format});
}

export function chipFilterBar({countries, iscoPresent, dateBounds, presets, skills = [], salaryBounds = [0, 250000], extras = {}}) {
  const url = readFromURL();
  const [salMin, salMax] = salaryBounds;
  const [dMin, dMax] = dateBounds;
  const pick = (options, v) => (v && options.includes(v) ? v : ALL);

  const countryOpts = [ALL, ...countries];
  const iscoOpts = [ALL, ...iscoPresent];
  const arrOpts = [ALL, "remote", "hybrid", "onsite", "unknown"];
  const skillOpts = skills.map((s) => s.skill);
  const skillCount = new Map(skills.map((s) => [s.skill, s.n]));

  const form = Inputs.form(
    {
      preset: presetSelect(presets, url.preset),
      country: chips(Inputs.radio, countryOpts, {label: "Country", value: pick(countryOpts, url.country)}),
      iscoMajor: chips(Inputs.radio, iscoOpts, {
        label: "ISCO group",
        value: pick(iscoOpts, url.iscoMajor),
        format: allOr((k) => `${k} · ${ISCO_MAJORS[k] ?? "?"}`)
      }),
      arrangement: chips(Inputs.radio, arrOpts, {label: "Arrangement", value: pick(arrOpts, url.arrangement)}),
      skills: chips(Inputs.checkbox, skillOpts, {
        label: "Skills",
        value: (url.skills ?? []).filter((s) => skillOpts.includes(s)),
        format: (s) => html`${s}<small>${skillCount.get(s).toLocaleString()}</small>`
      }),
      salary: salaryRange(salMin, salMax, {lo: url.salaryLo, hi: url.salaryHi}),
      dates: dateRange(dateBounds, {from: url.dateFrom, to: url.dateTo}),
      ...extras
    },
    {
      template: (form) => html`<div class="card chip-bar">
        <div class="chips">
          ${form.country}
          ${form.arrangement}
          ${form.iscoMajor}
          ${skillOpts.length ? form.skills : ""}
          ${Object.keys(extras).map((k) => form[k])}
        </div>
        <div class="chip-bar-ranges">${form.preset}${form.salary}${form.dates}</div>
      </div>`
    }
  );

  const defaults = {
    salaryLoBound: salMin,
    salaryHiBound: salMax,
    dateFromBound: dMin,
    dateToBound: dMax,
    presetDefault: presets && presets.length ? presets[0] : "data_analyst_eu"
  };
  form.addEventListener("input", () => writeToURL(form.value, defaults));

  return form;
}
