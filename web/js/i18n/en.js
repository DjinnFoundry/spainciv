// The English table: one file per part of the interface (see web/js/i18n.js).
import core from "./en/core.js";
import app from "./en/app.js";
import cityView from "./en/cityView.js";
import advisors from "./en/advisors.js";
import game from "./en/game.js";
import fiestas from "./en/fiestas.js";
import timeline from "./en/timeline.js";

export default { ...core, ...app, ...cityView, ...advisors, ...game, ...fiestas, ...timeline };
