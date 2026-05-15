// ISCO-08 major groups (top-level, 1-digit). Stable, public domain — see
// https://www.ilo.org/public/english/bureau/stat/isco/isco08/
export const ISCO_MAJORS = {
  "1": "Managers",
  "2": "Professionals",
  "3": "Technicians & associate professionals",
  "4": "Clerical support workers",
  "5": "Services & sales workers",
  "6": "Skilled agricultural, forestry, fishery",
  "7": "Craft & related trades",
  "8": "Plant & machine operators",
  "9": "Elementary occupations",
  "0": "Armed forces"
};

export function iscoMajorLabel(code) {
  if (code == null) return "Unclassified";
  return ISCO_MAJORS[String(code)] ?? `ISCO ${code}`;
}
