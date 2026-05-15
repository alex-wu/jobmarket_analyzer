import {html} from "npm:htl";

export function kpiCard(label, value, sub) {
  return html`<div class="card">
    <h2>${label}</h2>
    <span class="big">${value}</span>
    ${sub ? html`<small>${sub}</small>` : ""}
  </div>`;
}
