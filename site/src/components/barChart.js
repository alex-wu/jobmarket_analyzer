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
  xTickFormat,
  // Tick labels wider than the left margin are clipped with an ellipsis
  // (axis marks accept text-mark options; lineWidth is in ems at 10px font).
  yTickEms = (marginLeft - 30) / 10
} = {}) {
  return Plot.plot({
    ...(width ? {width} : {}),
    ...(height ? {height} : {}),
    marginLeft,
    x: {label: xLabel, grid: true, ...(xTickFormat ? {tickFormat: xTickFormat} : {})},
    y: {label: null},
    marks: [
      Plot.axisY({label: null, lineWidth: yTickEms, textOverflow: "ellipsis"}),
      Plot.barX(rows, {x, y, ...(fill !== undefined ? {fill} : {}), sort, tip: true}),
      Plot.text(rows, {x, y, text: annotate, dx: 6, textAnchor: "start"}),
      Plot.ruleX([0])
    ]
  });
}
