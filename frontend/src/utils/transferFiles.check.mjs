// Self-check for transferFiles.js. Run: node src/utils/transferFiles.check.mjs
import assert from "node:assert/strict";
import { parseCsv, parseRouteFile, parseTime, planRouteImport, routeExport, toCsv } from "./transferFiles.js";

// CSV survives commas, quotes and line breaks inside cells, plus the BOM and CRLF line ends.
const tricky = [{ name: 'Gate "A", North', note: "line one\nline two" }, { name: "Plain", note: "" }];
assert.deepEqual(parseCsv(toCsv(["name", "note"], tricky)), [{ name: 'Gate "A", North', note: "line one\nline two" }, { name: "Plain", note: "" }]);
assert.deepEqual(parseCsv(" Name ,LATITUDE\nA,1\n\n,\nB,2"), [{ name: "A", latitude: "1" }, { name: "B", latitude: "2" }]);

assert.equal(parseTime("7:05"), "07:05");
assert.equal(parseTime("07:05:00"), "07:05");
assert.equal(parseTime(""), "");
assert.equal(parseTime(null), "");
assert.equal(parseTime("25:00"), null);
assert.equal(parseTime("soon"), null);

const route = { id: 7, name: "Gulshan Route", description: "Via, University Rd", status: "published" };
const routeStops = [
  { id: 1, name: "Gulshan Chowrangi", latitude: 24.9215, longitude: 67.0847, address: "N/A", morning_eta: "07:10:00", evening_eta: null },
  { id: 2, name: "NIPA", latitude: 24.9176, longitude: 67.0971, address: "NIPA, Karachi", morning_eta: "07:25:00", evening_eta: "17:40:00" },
];
const existing = [...routeStops, { id: 3, name: "Old Depot", latitude: 24.9, longitude: 67.1, is_active: false }];

// A route exported in either format plans back to the same stops, order and ETAs.
for (const format of ["csv", "json"]) {
  const { rows, firstRow, source } = parseRouteFile(`route.${format}`, routeExport(route, routeStops, format));
  assert.deepEqual([String(source.id), source.name], ["7", "Gulshan Route"]);
  const plan = planRouteImport(rows, firstRow, existing);
  assert.deepEqual(plan.skipped, []);
  assert.deepEqual(plan.warnings, []);
  assert.deepEqual(plan.stops.map((stop) => [stop.existing.id, stop.morning_eta, stop.evening_eta]), [[1, "07:10", ""], [2, "07:25", "17:40"]]);
}
assert.equal(JSON.parse(routeExport(route, routeStops, "json")).route.description, "Via, University Rd");

// Ordering, matching, creation and every skip reason.
const plan = planRouteImport([
  { stop_order: "3", name: "Brand New", latitude: "24.95", longitude: "67.05", morning_eta: "8am" },
  { stop_order: "1", name: "  nipa ", latitude: "", longitude: "" },
  { stop_order: "2", name: "Renamed Chowrangi", latitude: "24.92151", longitude: "67.08471" }, // within 25 m of stop 1
  { stop_order: "4", name: "NIPA" },
  { stop_order: "5", name: "Old Depot" },
  { stop_order: "6", name: "Nowhere" },
  { stop_order: "7", name: "" },
], 2, existing);
assert.deepEqual(plan.stops.map((stop) => stop.existing?.id ?? stop.create.name), [2, 1, "Brand New"]);
assert.deepEqual(plan.stops[2].create, { name: "Brand New", latitude: 24.95, longitude: 67.05, address: "N/A" });
assert.equal(plan.warnings.length, 1);
assert.deepEqual(plan.skipped.map((item) => item.row), [5, 6, 7, 8]);

// Without a complete stop_order column, file order is kept.
assert.deepEqual(planRouteImport([{ name: "NIPA" }, { name: "Gulshan Chowrangi" }], 1, existing).stops.map((stop) => stop.existing.id), [2, 1]);

assert.deepEqual(parseRouteFile("route.json", '[{"name": "NIPA"}]').source, { id: null, name: "" });
assert.throws(() => parseRouteFile("route.json", "{not json"), /not valid JSON/);
assert.throws(() => parseRouteFile("route.json", '{"route": {}}'), /list of stops/);
assert.throws(() => parseRouteFile("route.csv", "name,latitude\n"), /no stop rows/);

console.log("transferFiles: all checks passed");
