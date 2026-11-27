// The data files in the chosen language. A country published in several languages writes each file's texts in its
// first language and, next to it, an overlay per other language with only the texts that differ, at the same path
// (pipeline/core/lang.py): data/lenses.json + data/lenses.en.json = the lenses in English. The numbers are shared.
import { country } from "./country.js";

/** Lay `patch` over `data` in place: a string replaces the text at its path; an object key indexes a list or an
 *  object. Returns `data`. */
export function overlay(data, patch) {
  for (const [k, v] of Object.entries(patch || {})) {
    if (v && typeof v === "object" && data[k] && typeof data[k] === "object") overlay(data[k], v);
    else data[k] = v;
  }
  return data;
}

async function fetchJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

/** data/<name>.json, with the overlay of the chosen language when it is not the data's own. */
export async function loadData(name) {
  const c = country();
  // A site that lists its data files (page settings `data`) has no other: an optional US-only file is not asked for.
  if (c.data && !c.data.includes(name)) throw new Error(`data/${name}.json: not in this map`);
  const lang = c.data_lang && c.lang !== c.data_lang ? c.lang : null;
  const data = await fetchJSON(`data/${name}.json`); // first: a file a country lacks (404) has no overlay either
  return lang ? overlay(data, await fetchJSON(`data/${name}.${lang}.json`)) : data;
}
