// Build-time data loader: Europe country boundaries as GeoJSON.
// Prunes world-atlas countries-50m to European countries and rewrites each
// feature's properties to {iso2, name} so the dashboard can join on the
// lowercase ISO2 codes used by the postings `country` column. Non-preset
// countries are kept so the map shows gray geographic context.
import {createRequire} from "node:module";
import {readFileSync} from "node:fs";
import * as topojson from "topojson-client";

const require = createRequire(import.meta.url);
const world = JSON.parse(readFileSync(require.resolve("world-atlas/countries-50m.json"), "utf8"));

// ISO 3166-1 numeric → ISO2 lowercase. Russia/Turkey omitted: mostly outside
// the fixed map frame and their geometries dominate the payload.
const ISO2_BY_NUMERIC = {
  "008": "al", "020": "ad", "040": "at", "056": "be", "070": "ba",
  "100": "bg", "112": "by", "191": "hr", "196": "cy", "203": "cz",
  "208": "dk", "233": "ee", "246": "fi", "250": "fr", "276": "de",
  "300": "gr", "348": "hu", "352": "is", "372": "ie", "380": "it",
  "428": "lv", "438": "li", "440": "lt", "442": "lu", "470": "mt",
  "492": "mc", "498": "md", "499": "me", "528": "nl", "578": "no",
  "616": "pl", "620": "pt", "642": "ro", "688": "rs", "703": "sk",
  "705": "si", "724": "es", "752": "se", "756": "ch", "804": "ua",
  "807": "mk", "826": "gb"
};

const all = topojson.feature(world, world.objects.countries).features;
const features = all
  .map((f) => ({f, iso2: ISO2_BY_NUMERIC[String(f.id).padStart(3, "0")]}))
  .filter((d) => d.iso2)
  .map(({f, iso2}) => ({
    type: "Feature",
    geometry: f.geometry,
    properties: {iso2, name: f.properties.name}
  }));

process.stdout.write(JSON.stringify({type: "FeatureCollection", features}));
