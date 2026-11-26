// Map-art extension: tile improvements (Interstates and major highways, railroads, ports, airports),
// military forts and restricted ground, wonders and protected land, and freight trade routes, each as a static layer
// drawn into the cached map (nothing animates; an idle map draws no frames), with a switch in the "Map" menu.
//
// Data: infrastructure.json, military.json, wonders.json and trade.json (loaded eagerly by main.js right after the
// first frame; app.loadData returns the same promise). A missing file (null) leaves its layers off and their switches
// harmless. Defaults: roads, rail, ports & airports, military and wonders on (roads, rail and hubs only from the region
// view in: see each layer's minRpx), trade routes off.
import { createModel } from "./model.js";
import { makeLayers } from "./layers.js";
import { tips } from "./tips.js";
import { t } from "../../i18n.js";

// label and title are i18n keys (layers.<id> and layers.<id>.title).
const TOGGLES = [
  { id: "roads", label: "layers.roads", icon: "t-road", def: true, title: "layers.roads.title", layers: ["roads"] },
  { id: "rail", label: "layers.rail", icon: "t-rail", def: true, title: "layers.rail.title", layers: ["rail"] },
  { id: "hubs", label: "layers.hubs", icon: "d-harbor", def: true, title: "layers.hubs.title", layers: ["hubs"] },
  { id: "military", label: "layers.military", icon: "m-army", def: true, title: "layers.military.title", layers: ["forts", "restricted", "plates"] },
  { id: "wonders", label: "layers.wonders", icon: "w-landmark", def: true, title: "layers.wonders.title", layers: ["wonders", "protected", "plates"] },
  { id: "trade", label: "layers.trade", icon: "t-trade", def: false, title: "layers.trade.title", layers: ["trade"] },
];

export function install(app) {
  const model = createModel(app.w);
  const on = Object.fromEntries(TOGGLES.map((t) => [t.id, t.def]));
  const layers = makeLayers(model, on, { tips, app });
  for (const l of layers) app.registerStaticLayer(l);

  for (const tg of TOGGLES) {
    app.ui.addMapToggle({
      id: tg.id, label: t(tg.label), icon: tg.icon, title: t(tg.title), default: tg.def,
      get: () => on[tg.id],
      set: (v) => {
        on[tg.id] = !!v;
        app.requestDraw();
      },
    });
  }

  const apply = (name, data) => {
    model.setData(name, data);
    app.requestDraw();
  };
  for (const name of ["infrastructure", "military", "wonders", "trade"]) {
    if (app.data[name] !== undefined) apply(name, app.data[name]);
    else app.loadData(name).then((d) => apply(name, d), (err) => console.warn(`map layers: ${name} failed to load`, err));
  }

  // For debugging and the gallery: the model and switches.
  app.mapArt = { model, on, layers };
}
