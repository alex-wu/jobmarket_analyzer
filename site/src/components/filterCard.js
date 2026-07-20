import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import {countrySelect, iscoMajorSelect, arrangementSelect, salaryRange, dateRange} from "./filters.js";
import {presetSelect} from "./presets.js";
import {readFromURL, writeToURL} from "./filterState.js";

// Sticky filter card used at the top of every data page. Combines the
// existing four filter primitives + the preset switcher into one
// Inputs.form so a single view() call yields {preset, country, iscoMajor,
// salary, dates}. whereClause() in filters.js consumes the same shape.
//
// Seeds initial values from URL search params (vanilla DOM) and writes back
// on every change via history.replaceState. Linking pages preserves filter
// state — see the head: script in observablehq.config.js which appends the
// current location.search to internal sidebar/footer links.
export function filterCard({countries, iscoPresent, dateBounds, presets, salaryBounds = [0, 250000], extras = {}}) {
  const url = readFromURL();
  const [salMin, salMax] = salaryBounds;
  const [dMin, dMax] = dateBounds;

  const form = Inputs.form(
    {
      preset: presetSelect(presets, url.preset),
      country: countrySelect(countries, url.country),
      iscoMajor: iscoMajorSelect(iscoPresent, url.iscoMajor),
      arrangement: arrangementSelect(url.arrangement),
      salary: salaryRange(salMin, salMax, {lo: url.salaryLo, hi: url.salaryHi}),
      dates: dateRange(dateBounds, {from: url.dateFrom, to: url.dateTo}),
      // Page-scoped inputs rendered inside the same card. Their values ride
      // along in form.value but are NOT URL-persisted (writeToURL ignores
      // unknown keys) and do not carry across pages.
      ...extras
    },
    {
      template: (form) => html`<div class="card" style="position:sticky;top:0;z-index:10;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0.75rem 1rem;align-items:end;margin-bottom:1rem">
        <div>${form.preset}</div>
        <div>${form.country}</div>
        <div>${form.iscoMajor}</div>
        <div>${form.arrangement}</div>
        <div>${form.salary}</div>
        <div>${form.dates}</div>
        ${Object.keys(extras).map((k) => html`<div>${form[k]}</div>`)}
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
