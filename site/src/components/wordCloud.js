import * as Plot from "npm:@observablehq/plot";
import cloud from "npm:d3-cloud";

// Word cloud over {text, value} rows via the d3-cloud layout, rendered with a
// Plot.text mark so fonts/colors stay consistent with the rest of the site.
// The layout is async (d3-cloud measures text on a canvas), so this returns a
// Promise<Element> — fine inside resize(), which awaits its render function.
export function wordCloud(rows, {
  text = "skill",
  value = "n",
  width = 640,
  height = 400,
  maxWords = 60,
  minFont = 12,
  maxFont = 44
} = {}) {
  const data = rows.slice(0, maxWords);
  if (data.length === 0) return Promise.resolve(document.createElement("div"));
  const max = Math.max(...data.map((d) => d[value]));
  const words = data.map((d) => ({
    text: d[text],
    n: d[value],
    size: minFont + (maxFont - minFont) * Math.sqrt(d[value] / max)
  }));
  return new Promise((resolve) => {
    cloud()
      .size([width, height])
      .words(words)
      .padding(2)
      .rotate(0)
      .font("sans-serif")
      .fontSize((d) => d.size)
      .random(() => 0.5) // deterministic layout across re-renders
      .on("end", (placed) => resolve(
        Plot.plot({
          width,
          height,
          margin: 0,
          x: {axis: null, domain: [-width / 2, width / 2]},
          y: {axis: null, domain: [-height / 2, height / 2]},
          marks: [
            Plot.text(placed, {
              x: "x",
              y: "y",
              text: "text",
              fontSize: "size",
              title: (d) => `${d.text}\n${d.n} postings`
            })
          ]
        })
      ))
      .start();
  });
}
