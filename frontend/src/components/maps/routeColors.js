// Route colours. Eight hues that stay apart for colour-blind readers too, given out
// so that routes sharing roads get different hues: with 50+ routes some hues
// repeat, but on routes in different parts of the city.
import { CAMPUS } from "./campus";

export const ROUTE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"];

const CELL_DEG = 0.004;          // ~400 m grid for "these routes use the same road"
const SAMPLE_M = 150;            // look at a route every 150 m along its line
const CAMPUS_IGNORE_M = 3000;    // every route ends on the same campus approach

const remembered = new Map();    // route id -> colour, kept while the app is open

function metres(a, b) {
  const kx = 111320 * Math.cos((a[1] * Math.PI) / 180);
  return Math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * 110574);
}

function cellsOf(route) {
  const line = route.geometry?.coordinates?.length > 1
    ? route.geometry.coordinates
    : (route.stops || []).map((stop) => [Number(stop.longitude), Number(stop.latitude)]);
  const cells = new Set();
  const add = (point) => {
    if (metres(point, CAMPUS.center) > CAMPUS_IGNORE_M) cells.add(`${Math.floor(point[0] / CELL_DEG)},${Math.floor(point[1] / CELL_DEG)}`);
  };
  line.forEach((point, index) => {
    add(point);
    const next = line[index + 1];
    if (!next) return;
    const steps = Math.floor(metres(point, next) / SAMPLE_M);
    for (let step = 1; step <= steps; step += 1) {
      const t = step / (steps + 1);
      add([point[0] + t * (next[0] - point[0]), point[1] + t * (next[1] - point[1])]);
    }
  });
  return cells;
}

/** Map of route id -> colour. A route keeps its colour for the rest of the visit,
 *  so filtering the list never repaints the routes still shown. */
export function routeColors(routes) {
  const fresh = routes.filter((route) => !remembered.has(route.id));
  if (fresh.length) {
    const cells = new Map(routes.map((route) => [route.id, cellsOf(route)]));
    const shared = (a, b) => {
      let count = 0;
      const [small, large] = cells.get(a).size < cells.get(b).size ? [cells.get(a), cells.get(b)] : [cells.get(b), cells.get(a)];
      small.forEach((cell) => { if (large.has(cell)) count += 1; });
      return count;
    };
    const overlap = new Map(fresh.map((route) => [
      route.id,
      routes.filter((other) => other.id !== route.id).map((other) => [other.id, shared(route.id, other.id)]).filter(([, n]) => n > 0),
    ]));
    // Most entangled routes choose first; ties by id keep the result stable.
    const order = [...fresh].sort((a, b) => {
      const weight = (route) => overlap.get(route.id).reduce((sum, [, n]) => sum + n, 0);
      return weight(b) - weight(a) || Number(a.id) - Number(b.id);
    });
    const uses = new Map(ROUTE_COLORS.map((color) => [color, 0]));
    remembered.forEach((color) => uses.set(color, (uses.get(color) || 0) + 1));
    order.forEach((route) => {
      const clash = new Map(ROUTE_COLORS.map((color) => [color, 0]));
      overlap.get(route.id).forEach(([otherId, n]) => {
        const color = remembered.get(otherId);
        if (color) clash.set(color, clash.get(color) + n);
      });
      const best = [...ROUTE_COLORS].sort((a, b) => clash.get(a) - clash.get(b) || uses.get(a) - uses.get(b) || ROUTE_COLORS.indexOf(a) - ROUTE_COLORS.indexOf(b))[0];
      remembered.set(route.id, best);
      uses.set(best, uses.get(best) + 1);
    });
  }
  return new Map(routes.map((route) => [route.id, remembered.get(route.id)]));
}
