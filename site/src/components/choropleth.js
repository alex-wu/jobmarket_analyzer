import * as Plot from "npm:@observablehq/plot";

// Europe choropleth. `europe` is the FeatureCollection from data/europe.json
// (properties: {iso2, name}); `valueByIso2` maps lowercase ISO2 → metric value.
// Countries absent from the map render as stroke-only geographic context.
export function choropleth(europe, valueByIso2, {
  label,
  format = (v) => v.toLocaleString(),
  scheme = "blues",
  width,
  height = 420
} = {}) {
  const has = (d) => valueByIso2.get(d.properties.iso2) != null;
  return Plot.plot({
    width,
    height,
    // Fixed frame over mainland Europe; also clips overseas territories
    // (world-atlas France includes French Guiana in one MultiPolygon).
    projection: {
      type: "conic-conformal",
      rotate: [-10, 0],
      domain: {type: "MultiPoint", coordinates: [[-11, 35], [32, 71]]}
    },
    color: {scheme, legend: true, label, tickFormat: format},
    marks: [
      Plot.geo(europe.features, {stroke: "currentColor", strokeOpacity: 0.25, fill: "none"}),
      Plot.geo(europe.features.filter(has), {
        fill: (d) => valueByIso2.get(d.properties.iso2),
        stroke: "currentColor",
        strokeOpacity: 0.25,
        tip: true,
        title: (d) => `${d.properties.name}\n${format(valueByIso2.get(d.properties.iso2))}`
      })
    ]
  });
}
