import * as Plot from "npm:@observablehq/plot";
import * as d3 from "npm:d3";

// Raincloud chart: per group, a density curve on top, every observation as a
// dot stacked below it, and a box plot underneath — on one shared x axis.
// Built from stock Plot marks (areaY, lineY, dot, rect, rule, text)
// with facets for the groups; the only hand-rolled parts are the kernel
// density estimate and the unit-histogram dot layout.
//
// rows:    [{value, group, kind, url, ...}] — one per observation
// summary: summarize(rows), which also fixes the row order

// Pixel heights of the bands in each group row (dots: single row / split rows).
const BAND = {density: 64, dotsSingle: 320, dotsSplit: 170, box: 30, gap: 22};
const BIN_PX = 16; // target width of one histogram bin
const PITCH_MAX = 8; // px between dot centres when there is room
const PITCH_MIN = 2; // below this the rows grow taller instead

// Per-group five-number summary (Tukey fences at 1.5 × IQR), largest median first.
export function summarize(rows, {minCount = 1} = {}) {
  return d3
    .groups(rows, (d) => d.group)
    .map(([group, g]) => {
      const v = Float64Array.from(g, (d) => d.value).sort();
      const q1 = d3.quantileSorted(v, 0.25);
      const med = d3.quantileSorted(v, 0.5);
      const q3 = d3.quantileSorted(v, 0.75);
      const iqr = q3 - q1;
      return {
        group,
        n: v.length,
        q1,
        med,
        q3,
        lo: v.find((x) => x >= q1 - 1.5 * iqr),
        hi: v.findLast((x) => x <= q3 + 1.5 * iqr),
        values: v
      };
    })
    .filter((s) => s.n >= minCount)
    .sort((a, b) => d3.descending(a.med, b.med));
}

// Gaussian kernel density estimate on a fixed grid, Silverman's bandwidth.
// Returned heights are scaled so each group's peak is 1 (shape, not volume).
function density(values, grid) {
  const n = values.length;
  const sd = d3.deviation(values) ?? 0;
  const iqr = d3.quantileSorted(values, 0.75) - d3.quantileSorted(values, 0.25);
  const spread = Math.min(sd || Infinity, iqr / 1.34 || Infinity);
  const h = Number.isFinite(spread) ? 0.9 * spread * n ** -0.2 : (grid.at(-1) - grid[0]) / 50 || 1;
  const ys = grid.map((x) => {
    let sum = 0;
    for (const v of values) sum += Math.exp(-0.5 * ((x - v) / h) ** 2);
    return sum;
  });
  const peak = d3.max(ys) || 1;
  return ys.map((y) => y / peak);
}

// Unit histogram layout: each bin is a block several dots wide, filled row by
// row from the baseline down, so heaping at round salaries widens a block
// instead of producing a needle. Each group gets the largest dot pitch at
// which its fullest block still fits the dots band. Returns the dots with
// pixel offsets (y, below the baseline) and radii, plus the height actually used.
function layoutDots(rows, [lo, hi], innerWidth, band) {
  const bins = Math.max(1, Math.round(innerWidth / BIN_PX));
  const binPx = innerWidth / bins;
  const step = (hi - lo) / bins || 1;
  const unit = step / binPx; // data units per pixel
  const dots = [];
  let height = 0;
  for (const [, byBin] of d3.group(rows, (d) => d.group, (d) => Math.min(bins - 1, Math.floor((d.value - lo) / step)))) {
    const fullest = d3.max(byBin.values(), (b) => b.length);
    let pitch = PITCH_MAX;
    let cols = 1;
    for (; pitch >= PITCH_MIN; pitch -= 0.25) {
      cols = Math.max(1, Math.floor(binPx / pitch));
      if (Math.ceil(fullest / cols) * pitch <= band) break;
    }
    pitch = Math.max(pitch, PITCH_MIN);
    height = Math.max(height, Math.ceil(fullest / cols) * pitch);
    for (const [bin, block] of byBin) {
      const left = lo + bin * step + ((binPx - cols * pitch) / 2) * unit;
      block.forEach((d, i) =>
        dots.push({...d, x: left + ((i % cols) + 0.5) * pitch * unit, y: -(Math.floor(i / cols) + 0.75) * pitch, r: pitch * 0.42})
      );
    }
  }
  return {dots, height};
}

export function distributionChart(rows, summary, {
  width,
  domain,
  xLabel,
  format = (v) => String(v),
  channels = {},
  tipFormat = {},
  colorDomain,
  colorLabel
} = {}) {
  const marginLeft = 16;
  const marginRight = 16;
  const [lo, hi] = domain;
  const groups = summary.map((s) => s.group);
  const visible = rows.filter((d) => d.value >= lo && d.value <= hi && groups.includes(d.group));
  const band = groups.length === 1 ? BAND.dotsSingle : BAND.dotsSplit;
  const {dots, height: dotsPx} = layoutDots(visible, domain, Math.max(BIN_PX, width - marginLeft - marginRight), band);

  // y is in pixels: 0 is the baseline between the density curve and the dots.
  const boxMid = -(dotsPx + BAND.box / 2);
  const boxHalf = BAND.box * 0.3;
  const bottom = -(dotsPx + BAND.box + BAND.gap);
  const rowHeight = BAND.density - bottom;

  const grid = d3.range(101).map((i) => lo + ((hi - lo) * i) / 100);
  const curves = summary.flatMap((s) => {
    const ys = density(s.values, grid);
    return grid.map((x, i) => ({group: s.group, x, y: ys[i] * BAND.density * 0.9}));
  });

  const dot = (options) => ({x: "x", y: "y", r: "r", fy: "group", fill: {value: "kind", label: colorLabel}, ...options});

  const plot = Plot.plot({
    width,
    height: 28 + 40 + rowHeight * groups.length,
    marginTop: 28,
    marginBottom: 40,
    marginLeft,
    marginRight,
    x: {domain, label: xLabel, tickFormat: format, grid: true},
    y: {domain: [bottom, BAND.density], axis: null},
    r: {type: "identity"},
    fy: {domain: groups, axis: null, padding: 0},
    color: {legend: true, domain: colorDomain},
    marks: [
      Plot.areaY(curves, {x: "x", y: "y", fy: "group", curve: "basis", fillOpacity: 0.12}),
      Plot.lineY(curves, {x: "x", y: "y", fy: "group", curve: "basis", strokeOpacity: 0.6}),
      Plot.ruleY([0], {strokeOpacity: 0.25}),
      Plot.dot(dots, dot({channels, tip: {format: {...tipFormat, x: false, y: false, r: false, fy: false}}})),
      Plot.dot(dots, Plot.pointer(dot({r: (d) => d.r + 3, stroke: "currentColor"}))),
      Plot.ruleY(summary, {x1: "lo", x2: "hi", y: () => boxMid, fy: "group", clip: true}),
      Plot.rect(summary, {
        x1: "q1",
        x2: "q3",
        y1: () => boxMid - boxHalf,
        y2: () => boxMid + boxHalf,
        fy: "group",
        fillOpacity: 0.12,
        stroke: "currentColor",
        clip: true
      }),
      Plot.ruleX(summary, {
        x: "med",
        y1: () => boxMid - boxHalf,
        y2: () => boxMid + boxHalf,
        fy: "group",
        strokeWidth: 2.5,
        clip: true
      }),
      Plot.text(summary, {
        fy: "group",
        frameAnchor: "top-right",
        lineAnchor: "top",
        dy: 2,
        fontWeight: 700,
        fontSize: 12,
        text: "group"
      }),
      Plot.text(summary, {
        fy: "group",
        frameAnchor: "top-right",
        lineAnchor: "top",
        dy: 18,
        fillOpacity: 0.7,
        text: (s) => `n = ${s.n.toLocaleString()} · median ${format(s.med)}`
      })
    ]
  });

  // Click opens the hovered observation (the pointer transform publishes it as
  // plot.value). A real anchor per dot would need a direct hit on a ~2px dot.
  plot.addEventListener("click", () => {
    const url = plot.value?.url;
    if (url) window.open(url, "_blank", "noopener");
  });

  return plot;
}
