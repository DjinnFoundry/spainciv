// "Horas a Madrid en tren" / "Hours to Madrid by train", on a map whose data has transit.json (Spain).
//
//   lens "rail_madrid" in the lens picker, after "commuters": the shortest timetabled journey to Madrid from each land
//     hex on the day of the timetable, the station it counts from in the tooltip
//   while the lens is open: the day's passenger track (thicker for more trains), Adif track with no passenger train
//     (dashed grey), and the stations as dots sized by their trains; the rail layer of the map hides (hides_layers)
//   URL hash: #lens=rail_madrid
// transit.json loads the first time the lens opens; the rules that need no canvas are in model.js.
import { country } from "../../app/country.js";
import { t } from "../../i18n.js";
import { buildPieces, visibleTiles, strokeAll } from "../../render/art/improvements.js";
import * as M from "./model.js";

const LENS = "rail_madrid";
const AFTER = "commuters";
const BANDS = [0, 1, 2];
// Below this hex radius (css px) the lines lose their casings and the dots their outlines: the whole of Spain stays
// under 3 ms a layer (DECISIONS A18) and the casing would be thinner than a pixel anyway.
const DETAIL_RPX = 14;

export function install(app) {
  const after = app.lensById.get(AFTER);
  if (!country().data?.includes("transit") || !after) return;
  const n = app.w.grid.size;

  const lens = {
    id: LENS, group: after.group, name: t("transit.lens.name"), icon: "t-rail", emoji: "🚆",
    format: "duration", scale: "linear", domain: [0, 1], higher_is: "bad", unit: "", source: "horarios_tren",
    description: t("transit.loading"), ramp: ["#8a8a8a", "#8a8a8a"], values: new Array(n).fill(null),
    hides_layers: ["rail"],
  };
  app.addLens(lens, { after: AFTER });

  let net = null, date = "", loading = null;
  let dots = null; // the station dots of one zoom: {Rpx, other, madrid} (Path2D)

  function prepare(d) {
    const { served, ghost } = M.lineClasses(d);
    return {
      served: buildPieces(app.w, served, BANDS),
      ghost: buildPieces(app.w, ghost, [M.GHOST]),
      links: M.linkIndex(d),
      stations: [...d.stations].sort((a, b) => M.totalTrains(b) - M.totalTrains(a)), // small dots drawn on top
    };
  }

  function load() {
    loading ??= app.loadData("transit").catch(() => null).then((d) => {
      if (!d?.lens?.values) {
        lens.description = t("transit.loadError");
        if (app.state.lens === lens) app.refreshLens();
        return;
      }
      date = M.dayLabel(d.date);
      const { values, names, labels } = M.lensLayer(d);
      const l = d.lens;
      Object.assign(lens, { domain: l.domain, ramp: l.ramp, scale: l.scale, higher_is: l.higher_is, unit: l.unit,
                            description: l.description, note: l.note, null_label: l.null_label, values, names, labels });
      net = prepare(d);
      if (app.state.lens === lens) app.refreshLens();
      app.invalidate();
    });
    return loading;
  }

  app.on("lens", (l) => { if (l === lens) load(); });
  if (app.hash.value("lens") === LENS) app.setLens(lens);

  const on = () => app.state.lens === lens && !!net;
  const sig = () => (net ? "1" : "0");

  app.registerStaticLayer({
    id: "transit-lines", z: 56, visible: on, sig,
    draw(ctx, vp, w, o) {
      const s = vp.s, pad = 4 / s;
      const ghost = visibleTiles(net.ghost, vp, pad), served = visibleTiles(net.served, vp, pad);
      const detail = o.Rpx >= DETAIL_RPX;
      ctx.lineJoin = "round";
      if (ghost.length) {
        ctx.lineCap = "butt";
        if (detail) {
          ctx.strokeStyle = "rgba(30,28,26,.55)";
          ctx.lineWidth = 2.4 / s;
          strokeAll(ctx, ghost, M.GHOST);
        }
        ctx.strokeStyle = "#d9d6d0";
        ctx.lineWidth = 1.2 / s;
        ctx.setLineDash([3 / s, 2.5 / s]);
        strokeAll(ctx, ghost, M.GHOST);
        ctx.setLineDash([]);
      }
      if (served.length) {
        ctx.lineCap = "round";
        ctx.strokeStyle = "rgba(255,250,238,.8)";
        for (const b of detail ? BANDS : []) {
          ctx.lineWidth = (M.lineWidth(b, o.Rpx) + 1.6) / s;
          strokeAll(ctx, served, b);
        }
        ctx.strokeStyle = "#1d1a18";
        for (const b of BANDS) {
          ctx.lineWidth = M.lineWidth(b, o.Rpx) / s;
          strokeAll(ctx, served, b);
        }
      }
    },
    hit(x, y, Rpx) {
      const it = M.hitLink(net.links, app.w.grid, x, y, Rpx);
      return it ? { kind: it.kind, n: it.n } : null;
    },
    tooltip: (it) => M.linkTip(it, date),
  });

  app.registerStaticLayer({
    id: "transit-stations", z: 65, visible: on, sig,
    draw(ctx, vp, w, o) {
      // One path per colour, filled and outlined once (1,400 separate arcs cost more than the 3 ms a layer may take),
      // built once per zoom: a drag repaints strips at the same zoom (A18). Far out, dark dots without outlines.
      const s = vp.s, detail = o.Rpx >= DETAIL_RPX;
      if (dots?.Rpx !== o.Rpx) {
        dots = { Rpx: o.Rpx, other: new Path2D(), madrid: new Path2D() };
        for (const st of net.stations) {
          const r = M.stationRadius(M.totalTrains(st), o.Rpx) / s;
          const p = st.madrid ? dots.madrid : dots.other;
          p.moveTo(st.x + r, st.y);
          p.arc(st.x, st.y, r, 0, 2 * Math.PI);
        }
      }
      ctx.lineWidth = 1 / s;
      ctx.strokeStyle = "#1d1a18";
      for (const [k, fill] of [["other", detail ? "#fffaf0" : "#1d1a18"], ["madrid", "#c8372d"]]) {
        ctx.fillStyle = fill;
        if (detail) ctx.stroke(dots[k]);
        ctx.fill(dots[k]);
      }
    },
    hit: (x, y, Rpx) => M.hitStation(net.stations, x, y, Rpx, app.w.grid.R),
    tooltip: (st) => M.stationTip(st, date),
  });
}
