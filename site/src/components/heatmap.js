import * as Plot from "npm:@observablehq/plot";

export function heatmap(rows, {
  x,
  y,
  value,
  valueLabel,
  valueFormat = (v) => Math.round(v).toLocaleString(),
  width,
  height,
  marginLeft = 220,
  scheme = "blues" // shared sequential scheme with the geography choropleth
} = {}) {
  return Plot.plot({
    ...(width ? {width} : {}),
    ...(height ? {height} : {}),
    marginLeft,
    marginRight: 60,
    color: {scheme, legend: true, label: valueLabel},
    x: {label: null},
    y: {label: null},
    marks: [
      Plot.cell(rows, {x, y, fill: value, inset: 0.5, tip: true}),
      Plot.text(rows, {x, y, text: (d) => valueFormat(d[value])})
    ]
  });
}
