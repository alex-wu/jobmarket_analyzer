import {fileURLToPath} from "node:url";
import {dirname, resolve} from "node:path";
import {readFileSync} from "node:fs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const src = resolve(__dirname, "../../../data/gh_databuild_samples/manifest.json");

process.stdout.write(readFileSync(src));
