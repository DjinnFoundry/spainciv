// English on the map of Spain: the strings whose usaciv English speaks of the United States (counties, the ACS,
// dollars), written for Spain; every other key falls back on the English table (see web/js/i18n.js).
import core from "./en-ES/core.js";
import app from "./en-ES/app.js";
import cityView from "./en-ES/cityView.js";
import advisors from "./en-ES/advisors.js";

export default { ...core, ...app, ...cityView, ...advisors };
