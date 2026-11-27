// Shared by the extensions' docks (fiestas, timeline) and the lens legend's fly_to list: ring some hexes and bring them
// into view.

/** Highlight `cells` and fit them in the view, zooming in to `scale` css px per km at most (never out of a closer
 *  view). Returns the highlight, so the caller can tell later whether it is still the map's. */
export function flyToCells(app, cells, scale) {
  const mark = { cells: new Set(cells) };
  app.setHighlight(mark);
  const b = app.highlightBounds(mark);
  if (b) app.fitBounds(b.x0, b.y0, b.x1, b.y1, { maxScale: Math.max(app.cam.scale, scale) });
  return mark;
}
