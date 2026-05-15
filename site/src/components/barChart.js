import * as Plot from "npm:@observablehq/plot";

export function barChart(rows, {
  x,
  y,
  xLabel,
  width,
  height,
  marginLeft = 220,
  sort = {y: "x", reverse: true},
  annotate = (d) => `n=${d.n ?? d[x]}`,
  fill,
  xTickFormat
} = {}) {
  return Plot.plot({
    ...(width ? {width} : {}),
    ...(height ? {height} : {}),
    marginLeft,
    x: {label: xLabel, grid: true, ...(xTickFormat ? {tickFormat: xTickFormat} : {})},
    y: {label: null},
    marks: [
      Plot.barX(rows, {x, y, ...(fill !== undefined ? {fill} : {}), sort, tip: true}),
      Plot.text(rows, {x, y, text: annotate, dx: 6, textAnchor: "start"}),
      Plot.ruleX([0])
    ]
  });
}
