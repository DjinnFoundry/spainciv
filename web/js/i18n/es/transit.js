// Spanish strings of the train lens (web/js/ext/transit; see web/js/i18n.js). Its description, note and rules are data
// texts of transit.json.
export default {
  "transit.lens.name": "Horas a Madrid en tren",
  "transit.loading": "Cargando los horarios de tren…",
  "transit.loadError": "No se han podido cargar los horarios de tren.",
  "transit.hex.from": "desde {name}",
  "transit.station.trains": { one: "{count} tren el {date}", other: "{count} trenes el {date}" },
  "transit.station.split": "({kinds}).",
  "transit.station.kind.ld": "{n} de alta velocidad y larga distancia",
  "transit.station.kind.md": "{n} de media distancia",
  "transit.station.kind.cer": "{n} de Cercanías",
  "transit.station.best": "A Madrid en {time}: sale {dep}, llega {arr} a {to}, {changes} ({legs})",
  "transit.station.walk": "a pie a {to}",
  "transit.station.direct": "sin transbordos",
  "transit.station.changes": { one: "{n} transbordo", other: "{n} transbordos" },
  "transit.station.none": "Ese día ningún tren lleva de aquí a Madrid.",
  "transit.station.madrid": "En Madrid.",
  "transit.link.served": { one: "{count} tren de viajeros el {date}", other: "{count} trenes de viajeros el {date}" },
  "transit.link.ghost": "Vía de Adif sin trenes de viajeros el {date} (puede tener mercancías)",
};
