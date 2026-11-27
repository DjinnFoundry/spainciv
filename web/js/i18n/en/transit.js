// English strings of the train lens (web/js/ext/transit; see web/js/i18n.js). Only Spain has the lens, so there is no
// en-ES counterpart. Its description, note and rules are data texts of transit.json.
export default {
  "transit.lens.name": "Hours to Madrid by train",
  "transit.loading": "Loading the train timetables…",
  "transit.loadError": "The train timetables could not be loaded.",
  "transit.hex.from": "from {name}",
  "transit.station.trains": { one: "{count} train on {date}", other: "{count} trains on {date}" },
  "transit.station.split": "({ld} high-speed and long-distance, {md} medium-distance, {cer} Cercanías).",
  "transit.station.best": "To Madrid in {time}: leaves {dep}, arrives {arr} at {to}, {changes} ({legs})",
  "transit.station.direct": "direct",
  "transit.station.changes": { one: "{n} change", other: "{n} changes" },
  "transit.station.none": "No train from here reaches Madrid that day.",
  "transit.station.madrid": "In Madrid.",
  "transit.link.served": { one: "{count} passenger train on {date}", other: "{count} passenger trains on {date}" },
  "transit.link.ghost": "Adif track with no passenger trains on {date} (may carry freight)",
};
