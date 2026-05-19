import * as Inputs from "npm:@observablehq/inputs";
import {html} from "npm:htl";
import {countrySelect, iscoMajorSelect, salaryRange, dateRange} from "./filters.js";
import {presetSelect} from "./presets.js";

// Sticky filter card used at the top of every data page. Combines the
// existing four filter primitives + the preset switcher into one
// Inputs.form so a single view() call yields {preset, country, iscoMajor,
// salary, dates}. whereClause() in filters.js consumes the same shape.
export function filterCard({countries, iscoPresent, dateBounds, presets}) {
  return Inputs.form(
    {
      preset: presetSelect(presets),
      country: countrySelect(countries),
      iscoMajor: iscoMajorSelect(iscoPresent),
      salary: salaryRange(0, 250000),
      dates: dateRange(dateBounds)
    },
    {
      template: (form) => html`<div class="card" style="position:sticky;top:0;z-index:10;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0.75rem 1rem;align-items:end;margin-bottom:1rem">
        <div>${form.preset}</div>
        <div>${form.country}</div>
        <div>${form.iscoMajor}</div>
        <div>${form.salary}</div>
        <div>${form.dates}</div>
      </div>`
    }
  );
}
