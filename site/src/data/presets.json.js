import {fileURLToPath} from "node:url";
import {dirname, resolve} from "node:path";
import {readdirSync} from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const dir = resolve(__dirname, "../../../data/gh_databuild_samples");

const ids = readdirSync(dir)
  .filter((f) => f.startsWith("latest-") && f.endsWith(".parquet"))
  .map((f) => f.slice("latest-".length, -".parquet".length))
  .sort();

process.stdout.write(JSON.stringify(ids));
