// City View "Districts": the metro's real industry specialisation (districts.json, BLS QCEW) as strategy-game
// districts, plus the Encampment tier from military.json (installations + armed-forces residents).
//
//   cityDistricts(ddata, mil, id) → [district]   the metro's districts, strongest first, each with what the dock and
//                                                the map plaques need ({id, name, short, color, icon, lq, emp, …})
//   badgeOf(ddata, id) → {label, text, color, icon, district} | null | undefined   the city-type badge
//   districtsHtml(m, ddata, mil) → HTML          the section body
//   badgeHtml(m, ddata) → HTML                   the header badge
import { esc, fixed, int, pct } from "../../format.js";
import { t } from "../../i18n.js";
import { compact, money } from "./fmt.js";
import { icon } from "../../ui/icon.js";
import { hasIcon } from "../../icons.js";

// Icons the district catalog names (d-*) are not drawn yet; until they are, a near icon from the set stands in,
// and canvas plaques without any icon get the letter in `mark`.
const FALLBACK = {
  campus: ["y-science", "🎓"], commercial_hub: ["i-finance", "💰"], industrial_zone: ["i-manufacturing", "🏭"],
  harbor: ["i-transportation", "⚓"], theater_square: ["i-arts", "🎭"], entertainment_complex: ["i-accommodation", "🎡"],
  aerodrome: ["i-transportation", "✈️"], government_plaza: ["i-public_admin", "🏛"], encampment: [null, "⛺"],
  aqueduct: ["i-utilities", "💧"],
};
const SHORT = {
  campus: () => t("cv.d.short.campus"), commercial_hub: () => t("cv.d.short.commercial_hub"),
  industrial_zone: () => t("cv.d.short.industrial_zone"), harbor: () => t("cv.d.short.harbor"),
  theater_square: () => t("cv.d.short.theater_square"), entertainment_complex: () => t("cv.d.short.entertainment_complex"),
  aerodrome: () => t("cv.d.short.aerodrome"), government_plaza: () => t("cv.d.short.government_plaza"),
  encampment: () => t("cv.d.short.encampment"), aqueduct: () => t("cv.d.short.aqueduct"),
};
const shortOf = (id) => SHORT[id]?.();
const TIER = { garrison: () => t("cv.d.tier.garrison"), fortress: () => t("cv.d.tier.fortress") };
const tierOf = (tier) => TIER[tier]?.();

const catCache = new WeakMap();
function catalog(ddata) {
  let m = catCache.get(ddata);
  if (!m) catCache.set(ddata, (m = new Map((ddata?.catalog || []).map((c) => [c.id, c]))));
  return m;
}

export function iconFor(id, cat) {
  if (cat?.icon && hasIcon(cat.icon)) return cat.icon;
  const f = FALLBACK[id]?.[0];
  return f && hasIcon(f) ? f : null;
}

const instCache = new WeakMap();
function installationsById(mil) {
  let m = instCache.get(mil);
  if (!m) instCache.set(mil, (m = new Map((mil?.installations || []).map((i) => [i.id, i]))));
  return m;
}

/**
 * The metro's districts: districts.json entries (strongest first), with military.json's Encampment merged in (its
 * tier label; added at the end when only military.json has one).
 */
export function cityDistricts(ddata, mil, id) {
  const cat = catalog(ddata);
  const row = ddata?.cities?.[id] || null;
  const mc = mil?.cities?.[id] || null;
  const out = [];
  for (const d of row?.districts || []) {
    const c = cat.get(d.id) || {};
    const spec = d.via === "specialty" && d.sub;
    out.push({
      ...d, name: c.name || d.id, color: c.color || "#5a6a7a", icon: iconFor(d.id, c), emoji: FALLBACK[d.id]?.[1] || "◆",
      cat: c, subName: d.sub ? c.sub?.[d.sub] || ddata.industries?.[d.sub]?.title || d.sub : null,
      // The map plaque: a speciality-qualified district is labelled by that speciality (its own LQ is the reason).
      short: spec ? c.sub?.[d.sub] || shortOf(d.id) : shortOf(d.id) || c.name || d.id,
      mapLq: spec ? d.sub_lq : d.lq,
      military: d.id === "encampment" ? mc : null,
    });
  }
  if (mc && !out.some((d) => d.id === "encampment")) {
    const c = cat.get("encampment") || {};
    out.push({
      id: "encampment", name: c.name || "Encampment", color: c.color || "#8a4a3a", icon: iconFor("encampment", c), emoji: "⛺",
      cat: c, lq: null, emp: null, short: tierOf(mc.tier) || shortOf("encampment"), mapLq: null, military: mc, militaryOnly: true,
    });
  }
  for (const d of out) {
    if (d.military) d.tierLabel = tierOf(d.military.tier) || d.military.tier;
  }
  return out;
}

/** The city-type badge; undefined while districts.json is loading, null when there is none. */
export function badgeOf(ddata, id) {
  if (!ddata) return ddata; // undefined (loading) or null (missing)
  const row = ddata.cities?.[id];
  if (!row) return null;
  if (!row.badge) return { label: t("cv.d.diversified"), text: t("cv.d.diversifiedText"), color: "#6a7484", icon: null, district: null };
  const c = catalog(ddata).get(row.badge.district) || {};
  return { ...row.badge, color: c.color || "#6a7484", icon: iconFor(row.badge.district, c), emoji: FALLBACK[row.badge.district]?.[1] };
}

// districts.json `method` names the source for the UI; the original (BLS QCEW) data has none and gets these.
const QCEW_METHOD = {
  code_system: "NAICS", source_label: "BLS QCEW",
  note: "QCEW counts jobs where the employer is, not where workers live; it leaves out the self-employed, most farm workers, railroads and uniformed military.",
};
const method = (ddata) => ({ ...QCEW_METHOD, ...(ddata?.method || {}) });
const isQcew = (ddata) => !ddata?.method;

export function badgeHtml(m, ddata) {
  const b = badgeOf(ddata, m.city.id);
  if (!b) return "";
  return `<span class="cv-type${b.district ? "" : " plain"}" style="--tc:${esc(b.color)}" title="${t("cv.d.typeTip", { text: esc(b.text || b.label), source: esc(method(ddata).source_label), year: esc(String(ddata.year || "")) })}">
    <span class="cv-type-ic">${icon(b.icon, b.emoji || "◆", { size: 13 })}</span>${esc(b.label)}</span>`;
}

const ge = (lb) => (lb ? "≥" : "");
const signed = (x) => (x == null ? "–" : `${x >= 0 ? "+" : "−"}${pct(Math.abs(x), 1)}`);

function lqTag(lq, lb, tip) {
  if (lq == null) return "";
  const cls = lq >= 1.25 ? "hi" : lq <= 0.75 ? "lo" : "mid";
  return `<span class="cv-lq ${cls}" title="${esc(tip || t("cv.d.lqTip", { lq: fixed(lq, 2) }))}">×${ge(lb)}${fixed(lq, 1)}</span>`;
}

function districtCard(d, row, ddata, mil) {
  const nat = ddata?.national || {};
  const c = d.cat || {};
  const lb = !!d.lower_bound;
  const supTip = lb ? ` BLS withheld part of this in ${d.suppressed} member count${d.suppressed === 1 ? "y" : "ies"}, so it is a lower bound.` : "";
  const facts = [];
  if (d.emp != null) {
    facts.push(`<div><span>${t("cv.d.jobs")}</span><b>${ge(lb)}${compact(d.emp)}</b><small>${d.share != null ? t("cv.d.ofMetro", { share: pct(d.share, 1) }) : ""}</small></div>`);
  }
  if (d.avg_pay != null) {
    facts.push(`<div><span>${t("cv.d.avgPay")}</span><b>${money(d.avg_pay)}</b><small>${row?.avg_pay != null ? t("cv.d.metroPay", { v: money(row.avg_pay) }) : ""}</small></div>`);
  }
  if (d.strength != null) {
    facts.push(`<div title="${t("cv.d.aboveTip")}"><span>${t("cv.d.above")}</span><b>${ge(lb)}${compact(Math.max(0, d.strength))}</b><small>${t("cv.d.jobsUnit")}</small></div>`);
  }
  let spec = "";
  if (d.sub && d.subName) {
    // the speciality's own withheld flag (districts.json sub_lower_bound; older files: the top-industries row)
    const slb = d.sub_lower_bound ?? !!(row?.top || []).find((t) => t.naics === d.sub)?.lower_bound;
    spec = `<p class="cv-dc-sub">${d.via === "specialty" ? t("cv.d.via") : t("cv.d.strongest")}: <b>${esc(d.subName)}</b> ${lqTag(d.sub_lq, slb, slb ? `Location quotient: at least ${d.sub_lq.toFixed(2)}× the national share (BLS withheld part of it, so it is a lower bound)` : undefined)}${
      d.sub_emp != null ? ` <small>${ge(slb)}${t("cv.d.jobsN", { n: compact(d.sub_emp) })}</small>` : ""}${
      d.via === "specialty" && d.lq != null ? `<br><small>${t("cv.d.viaNote", { lq: fixed(d.lq, 2) })}</small>` : ""}</p>`;
  }
  let milHtml = "";
  if (d.military) {
    const mc = d.military;
    const inst = installationsById(mil);
    const names = (mc.installations || []).map((i) => inst.get(i)?.name).filter(Boolean);
    milHtml = `<div class="cv-dc-mil">
      <p><b>${esc(d.tierLabel)}</b>${mc.naval ? " (naval)" : ""}: ${int(mc.armed_forces)} residents in the armed forces, ${pct(mc.share, mc.share < 0.01 ? 2 : 1)} of people 16 and over.</p>
      ${names.length ? `<p class="cv-dc-inst">${names.slice(0, 5).map((n) => `<span>${esc(n)}</span>`).join("")}${
        mc.installation_count > Math.min(5, names.length) ? `<small>+${mc.installation_count - Math.min(5, names.length)} more</small>` : ""}</p>` : ""}
    </div>`;
  }
  const caveat = c.caveat ? `<p class="cv-dc-cav">${esc(c.caveat)}</p>` : "";
  const title = d.militaryOnly ? `${esc(d.name)} · ${esc(d.tierLabel)}` : d.military ? `${esc(d.name)} · ${esc(d.tierLabel)}` : esc(d.name);
  return `<div class="cv-dc" style="--dc:${esc(d.color)}" title="${esc(c.description || "")}${esc(supTip)}">
    <div class="cv-dc-h"><span class="cv-dc-hex">${icon(d.icon, d.emoji, { size: 18 })}</span>
      <div class="cv-dc-t"><b>${title}</b><small>${esc(c.description || "")}</small></div>
      ${d.lq != null ? lqTag(d.lq, lb, t("cv.d.lqDistrict", { lq: fixed(d.lq, 2), note: supTip })) : ""}</div>
    ${facts.length ? `<div class="cv-dc-f">${facts.join("")}</div>` : ""}
    ${spec}${milHtml}${caveat}
  </div>`;
}

function topTable(row, ddata) {
  const top = row?.top || [];
  if (!top.length) return "";
  const max = Math.max(...top.map((t) => t.lq || 0), 1);
  return `<h4 class="cv-h4">${t("cv.d.top")}</h4>
  <div class="cv-top" role="table" aria-label="${t("cv.d.topLabel")}">
    <div class="cv-top-r cv-top-hd" role="row"><span role="columnheader">${t("cv.d.col.industry")}</span><span role="columnheader">${t("cv.d.col.jobs")}</span><span role="columnheader">×N</span><span role="columnheader">${t("cv.d.col.pay")}</span><span role="columnheader">${t("cv.d.col.year")}</span></div>
    ${top.map((t) => {
      const cs = method(ddata).code_system;
      const title = ddata.industries?.[t.naics]?.title || `${cs} ${t.naics}`;
      const lb = !!t.lower_bound;
      return `<div class="cv-top-r" role="row" title="${esc(title)} (${esc(cs)} ${esc(t.naics)})${lb ? `. Lower bound: BLS withheld it in ${t.suppressed} member count${t.suppressed === 1 ? "y" : "ies"}.` : ""}">
        <span role="cell" class="cv-top-n">${esc(title)}<i style="width:${((Math.log(1 + (t.lq || 0)) / Math.log(1 + max)) * 100).toFixed(1)}%"></i></span>
        <span role="cell">${ge(lb)}${compact(t.emp)}</span>
        <span role="cell"><b>${t.lq != null ? `${ge(lb)}${fixed(t.lq, 1)}` : "–"}</b></span>
        <span role="cell">${money(t.avg_pay)}</span>
        <span role="cell" class="${t.oty_pct == null ? "" : t.oty_pct >= 0 ? "good" : "bad"}">${signed(t.oty_pct)}</span></div>`;
    }).join("")}
  </div>`;
}

/** The Districts section body. ddata: districts.json (undefined while loading, null when missing). */
export function districtsHtml(m, ddata, mil) {
  if (ddata === undefined) return `<p class="muted cv-note">${t("cv.d.loading")}</p>`;
  if (!ddata) return `<p class="muted cv-note">${t("cv.d.missing")}</p>`;
  const id = m.city.id;
  const row = ddata.cities?.[id] || null;
  const list = cityDistricts(ddata, mil, id);
  const b = badgeOf(ddata, id);
  let lead;
  if (!row) {
    lead = isQcew(ddata)
      ? `<p class="cv-lead">BLS publishes no county employment for ${esc(m.city.name)}'s member counties, so it has no industry districts.</p>`
      : `<p class="cv-lead">${t("cv.d.noRow", { source: esc(method(ddata).source_label), name: esc(m.city.name) })}</p>`;
  } else {
    const cnt = row.counties ? ` from ${row.counties[0]} of ${row.counties[1]} member count${row.counties[1] === 1 ? "y" : "ies"}` : "";
    const pay = row.avg_pay != null ? t("cv.d.pay", { pay: money(row.avg_pay), national: money(ddata.national?.avg_pay) }) : "";
    lead = `<p class="cv-lead">${b?.district ? `<b class="cv-type-l" style="--tc:${esc(b.color)}">${esc(b.label)}</b> · ${esc(b.text || "")}. ` : ""}${
      int(row.emp)} ${isQcew(ddata) ? `jobs counted${esc(cnt)}` : t("cv.d.employedResidents")}${pay}.</p>`;
  }
  const cards = list.length
    ? `<div class="cv-dcs">${list.map((d) => districtCard(d, row, ddata, mil)).join("")}</div>`
    : row ? `<p class="muted cv-note">${t("cv.d.none")}</p>` : "";
  const milRule = mil?.rule && list.some((d) => d.military) ? `<p><b>Encampment tier</b> (military.json): ${esc(mil.rule)}</p>` : "";
  return `${lead}
    ${cards}
    ${topTable(row, ddata)}
    <div class="cv-schematic">
      <p>${t("cv.d.schematic")}</p>
    </div>
    <details class="cv-more cv-rule"><summary>${t("cv.d.how")}</summary>
      <p>${esc(ddata.rule?.text || "")}</p>${milRule}
      <p>${esc(method(ddata).note)}</p>
    </details>
    <p class="cv-note">${esc(ddata.vintage || "BLS QCEW")}${isQcew(ddata) ? ", all ownerships (federal and state only for the Government plaza and Encampment). ×N = location quotient; ≥ = a lower bound (BLS withheld a county's figure)." : t("cv.d.note")}${
      mil && list.some((d) => d.military) ? ` Encampment tier: ${esc(typeof mil.vintage === "object" ? [mil.vintage.installations, mil.vintage.acs].filter(Boolean).join("; ") : mil.vintage || "")}.` : ""}</p>`;
}
