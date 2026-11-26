// Hover tooltips for the map-art layers (HTML strings; every data value is escaped). Each says where the number comes
// from and the caveat that matters for it (FAF values are model estimates; bases have no published headcount; the
// trade arc is a drawing aid; curated landmarks are an editorial pick).
import { esc, compact, int, pct, fixed, withPct, shownTons, shownWeight } from "../../format.js";
import { FORT_KINDS, fortKind } from "../../render/art/sites.js";
import { MODE_STYLE } from "../../render/art/improvements.js";
import { t, usOr } from "../../i18n.js";

const muted = (s) => `<span class="muted">${s}</span>`;
const num = (n, d = 1) => (n == null || !Number.isFinite(n) ? "–" : compact(n));
const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "±");

function usd(n) {
  if (n == null || !Number.isFinite(n)) return "–";
  const a = Math.abs(n);
  if (a >= 1e12) return `$${(n / 1e12).toFixed(2)} trillion`;
  if (a >= 1e9) return `$${(n / 1e9).toFixed(a >= 1e10 ? 1 : 2)} billion`;
  if (a >= 1e6) return `$${(n / 1e6).toFixed(1)} million`;
  return `$${int(n)}`;
}

const HUB_NAME = { L: "tip.hub.L", M: "tip.hub.M", S: "tip.hub.S", N: "tip.hub.N" };
const PORT_TYPE = { coastal: "tip.port.coastal", great_lakes: "tip.port.great_lakes.us", inland: "tip.port.inland" };
const WONDER_KIND = { natural: "wonder.kind.natural", university: "wonder.kind.university", landmark: "wonder.kind.landmark" };
const NATIONAL_PARK = new Set(["National Park", "Parque Nacional"]); // metrics.unit_type in the US and Spanish data

export const tips = {
  port(p, m) {
    const yr = p.year ?? "";
    const lines = [
      `<b>${esc(p.name)}</b> ${muted(`${esc(t(PORT_TYPE[p.type] || "tip.port"))}, ${esc(p.state || "")}`)}`,
      t("tip.port.rank", { rank: esc(p.rank), tons: num(shownTons(p.tons)), year: esc(yr) }),
    ];
    if (p.foreign != null || p.domestic != null) lines.push(t("tip.port.foreign", { foreign: num(shownTons(p.foreign)), domestic: num(shownTons(p.domestic)) }));
    if (p.imports != null || p.exports != null) lines.push(t("tip.port.imports", { imports: num(shownTons(p.imports)), exports: num(shownTons(p.exports)) }));
    lines.push(muted(t("tip.port.note")));
    return lines.join("<br>");
  },
  airport(a) {
    const lines = [`<b>${esc(a.id)} · ${esc(a.name)}</b> ${muted(esc([a.city, a.state].filter(Boolean).join(", ")))}`];
    lines.push(a.hub ? esc(HUB_NAME[a.hub] ? t(HUB_NAME[a.hub]) : a.hub) : t("tip.air.cargoOnly"));
    if (a.enplanements != null) {
      let ch = "";
      if (a.enplanements_prev > 0) {
        const r = a.enplanements / a.enplanements_prev - 1;
        ch = t("tip.air.change", { change: withPct(sign(r) + fixed(Math.abs(r * 100), 1)), year: a.year - 1 });
      }
      lines.push(t("tip.air.pax", { n: num(a.enplanements), year: esc(a.year), change: ch }));
    }
    if (a.cargo_lbs != null) lines.push(t("tip.air.cargo", { v: num(shownWeight(a.cargo_lbs)) }));
    lines.push(muted(t("tip.air.note")));
    return lines.join("<br>");
  },
  fort(f, m) {
    const comp = m.data.military?.components?.find((c) => c.id === f.component);
    const name = comp?.name || FORT_KINDS[fortKind(f.component)]?.name || t("tip.fort.site");
    const tier = { major: t("tip.fort.major"), base: t("tip.fort.base"), site: t("tip.fort.siteTier") }[f.tier] || "";
    const status = { act: "", semi: t("tip.fort.semi"), care: t("tip.fort.care") }[f.status] ?? "";
    const lines = [
      `<b>${esc(f.name)}</b> ${muted(esc(f.state || ""))}`,
      `${esc(name)}${f.joint ? t("tip.fort.joint") : ""} · ${esc(tier)}${esc(status)}`,
    ];
    if (f.area_km2 != null) lines.push(t("tip.fort.boundary", { area: int(f.area_km2) }));
    lines.push(muted(usOr("tip.fort.note")));
    return lines.join("<br>");
  },
  range(r, m) {
    const comp = m.data.military?.components?.find((c) => c.id === r.component);
    return [
      `<b>${esc(r.name)}</b> ${muted(esc(r.state || ""))}`,
      t("tip.range.line", { comp: esc(comp?.name || ""), area: int(r.area_km2) }),
      muted(usOr("tip.range.note", { n: m.ranges?.length || 0 })),
    ].join("<br>");
  },
  wonder(x, m) {
    const k = t(WONDER_KIND[x.kind] || "wonder.kind.other");
    const rule = m.data.wonders?.rules?.find((r) => r.id === x.rule);
    const mt = x.metrics || {};
    const lines = [`<b>${esc(x.name)}</b> ${muted(esc([x.state].filter(Boolean).join("")))}`];
    if (x.kind === "university") {
      lines.push(mt.rd_usd != null ? `${esc(k)} · #${esc(x.rank)} by research spending` : t("wonder.rankStudents", { kind: esc(k), rank: esc(x.rank) }));
      if (mt.rd_usd != null) lines.push(`R&amp;D ${usd(mt.rd_usd)} (FY${esc(mt.year)})${mt.federal_usd != null ? `, ${pct(mt.federal_usd / mt.rd_usd, 0)} federal` : ""}`);
      if (mt.students != null) lines.push(`${t("wonder.students", { n: int(mt.students), year: esc(mt.students_year) })}${mt.municipality ? ` ${muted(esc(mt.municipality))}` : ""}`);
      if (mt.enrollment != null) lines.push(`${int(mt.enrollment)} students (12-month headcount, ${esc(mt.enrollment_year)})`);
    } else if (x.curated) {
      lines.push(`${esc(k)} · hand-picked (curated, not ranked by data)`);
      if (mt.visits != null) lines.push(`${num(mt.visits)} recreation visits (${esc(mt.year)})`);
      if (mt.designated) lines.push(`National Historic Landmark since ${esc(mt.designated)}`);
    } else {
      const among = mt.unit_type ? t(NATIONAL_PARK.has(mt.unit_type) ? "wonder.amongParks" : "wonder.amongOther") : "";
      lines.push(t("wonder.rank", { kind: esc(k), rank: esc(x.rank), among }));
      if (mt.visits != null) lines.push(`${t("wonder.visits", { n: num(mt.visits), year: esc(mt.year) })}${mt.visits_of ? ` ${muted(`(${esc(mt.visits_of)})`)}` : ""}`);
      if (mt.area_km2 != null) lines.push(`${int(mt.area_km2)} km²`);
      if (mt.unesco_id != null) lines.push(t("wonder.unesco", { id: esc(mt.unesco_id), n: mt.components ?? 1 }));
    }
    if (rule?.text) lines.push(muted(esc(rule.text)));
    return lines.join("<br>");
  },
  route(rt, m) {
    const r = rt.route;
    const t = m.data.trade || {};
    const a = rt.a?.short || rt.a?.name || r.a, b = rt.b?.short || rt.b?.name || r.b;
    const modes = Object.entries(r.modes || {}).filter(([, v]) => v >= 0.05).sort((p, q) => q[1] - p[1])
      .map(([k, v]) => `${esc(MODE_STYLE[k]?.label || k)} ${Math.round(v * 100)}%`).join(" · ");
    const com = t.commodities?.[r.top_commodity];
    const lines = [
      `<b>${esc(a)} ⇄ ${esc(b)}</b> ${muted(`trade route #${esc(r.rank)}`)}`,
      `<b>${usd(r.value_musd * 1e6)}</b> of freight a year, ${num(r.tons_k * 1e3)} short tons (FAF ${esc(t.year ?? "")} estimate)`,
    ];
    if (modes) lines.push(modes);
    if (com) lines.push(`Top commodity: ${esc(com)}`);
    lines.push(muted("Both directions summed. Drawn as an arc between each zone's largest city: FAF records where freight starts and ends, not its route."));
    return lines.join("<br>");
  },
};
