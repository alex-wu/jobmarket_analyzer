import * as Inputs from "npm:@observablehq/inputs";

// Single preset switcher. Stubbed at v1: when only one preset is available
// the select is disabled and shows the lone option. Multi-preset accumulation
// (ADR-020) populates this dropdown automatically — the loader emits the list
// via `data/presets.json.js`.
export function presetSelect(options, def) {
  const list = options && options.length ? options : ["data_analyst_eu"];
  const value = def && list.includes(def) ? def : list[0];
  return Inputs.select(list, {
    label: "Preset",
    value,
    disabled: list.length <= 1,
    format: (k) => k.replaceAll("_", " ")
  });
}
