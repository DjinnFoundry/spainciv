// The Spanish table: one file per part of the interface (see web/js/i18n.js).
import core from "./es/core.js";
import app from "./es/app.js";
import cityView from "./es/cityView.js";
import advisors from "./es/advisors.js";
import game from "./es/game.js";
import fiestas from "./es/fiestas.js";
import timeline from "./es/timeline.js";

export default { ...core, ...app, ...cityView, ...advisors, ...game, ...fiestas, ...timeline };
