// CSV/JSON reading and writing behind the stop and route import/export buttons.
// Everything except downloadFile is pure; run `node src/utils/transferFiles.check.mjs` after changing it.

export const DUPLICATE_RADIUS_M = 25; // same threshold the stop import uses on the server
const BOM = String.fromCharCode(0xfeff);

const csvCell = (value) => {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
};

// The BOM makes Excel read the file as UTF-8; parseCsv and the server import both strip it.
export const toCsv = (columns, rows) =>
  `${BOM}${[columns.join(","), ...rows.map((row) => columns.map((column) => csvCell(row[column])).join(","))].join("\r\n")}\r\n`;

/** Parses CSV text into one object per non-blank row, keyed by the lower-cased header. */
export function parseCsv(text) {
  const source = text.startsWith(BOM) ? text.slice(1) : text;
  const table = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (quoted) {
      if (char !== '"') cell += char;
      else if (source[i + 1] === '"') { cell += '"'; i += 1; }
      else quoted = false;
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && source[i + 1] === "\n") i += 1;
      row.push(cell);
      table.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }
  if (cell !== "" || row.length) { row.push(cell); table.push(row); }

  const [header = [], ...body] = table;
  const keys = header.map((key) => key.trim().toLowerCase());
  return body
    .filter((cells) => cells.some((value) => value.trim() !== ""))
    .map((cells) => Object.fromEntries(keys.map((key, index) => [key, (cells[index] ?? "").trim()])));
}

export function downloadFile(filename, content) {
  const type = filename.endsWith(".json") ? "application/json" : "text/csv;charset=utf-8";
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// ── Routes ───────────────────────────────────────────────────────────────────
// The stop columns use the stop import's names, so a route CSV also imports on the Stops page.
const ROUTE_COLUMNS = ["stop_order", "name", "latitude", "longitude", "address", "morning_eta", "evening_eta", "route_id", "route_name", "route_description", "route_status"];
const NO_ADDRESS = "N/A";

const normName = (name) => String(name ?? "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");

const metresBetween = (a, b) => {
  const toRad = Math.PI / 180;
  const x = (b.longitude - a.longitude) * toRad * Math.cos(((a.latitude + b.latitude) / 2) * toRad);
  const y = (b.latitude - a.latitude) * toRad;
  return Math.hypot(x, y) * 6371000;
};

const pointOf = (source) => {
  if (source.latitude === "" || source.latitude == null || source.longitude === "" || source.longitude == null) return null;
  const latitude = Number(source.latitude);
  const longitude = Number(source.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180 || (latitude === 0 && longitude === 0)) return null;
  return { latitude, longitude };
};

/** "7:05", "07:05" or "07:05:00" → "07:05"; blank → ""; anything else → null. */
export function parseTime(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const match = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(text);
  if (!match || Number(match[1]) > 23 || Number(match[2]) > 59) return null;
  return `${match[1].padStart(2, "0")}:${match[2]}`;
}

/** The whole route (details, ordered stops, ETAs) as CSV or JSON text. */
export function routeExport(route, stops, format) {
  const rows = stops.map((stop, index) => ({
    stop_order: index + 1,
    name: stop.name,
    latitude: stop.latitude,
    longitude: stop.longitude,
    address: !stop.address || stop.address === NO_ADDRESS ? "" : stop.address,
    morning_eta: parseTime(stop.morning_eta) || "",
    evening_eta: parseTime(stop.evening_eta) || "",
  }));
  const details = { id: route.id ?? null, name: route.name ?? "", description: route.description ?? "", status: route.status ?? "" };
  if (format === "json") return JSON.stringify({ route: details, stops: rows }, null, 2);
  return toCsv(ROUTE_COLUMNS, rows.map((row) => ({ ...row, route_id: details.id, route_name: details.name, route_description: details.description, route_status: details.status })));
}

/** Reads a route file into raw rows plus the `source` route it was exported from. Throws an Error with a readable message. */
export function parseRouteFile(filename, text) {
  if (!filename.toLowerCase().endsWith(".json")) {
    const rows = parseCsv(text);
    if (!rows.length) throw new Error("The CSV file has no stop rows.");
    return { rows, firstRow: 2, source: { id: rows[0].route_id || null, name: rows[0].route_name || "" } }; // line 1 is the header
  }
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error("The file is not valid JSON.");
  }
  const list = Array.isArray(data) ? data : data?.stops;
  if (!Array.isArray(list) || !list.length || !list.every((item) => item && typeof item === "object")) {
    throw new Error('JSON must be a list of stops, or {"stops": [...]}.');
  }
  const rows = list.map((item) => Object.fromEntries(Object.entries(item).map(([key, value]) => [key.trim().toLowerCase(), value])));
  const from = (!Array.isArray(data) && data.route) || {};
  return { rows, firstRow: 1, source: { id: from.id ?? null, name: from.name ?? "" } };
}

/**
 * Works out what importing `rows` into a route would do, without changing anything.
 * Each row is matched to an existing stop by name, else by being within 25 m; unmatched rows
 * with coordinates become stops to create. Returns the ordered `stops` to put on the route
 * (each with `existing` or `create`), the rows `skipped` and why, and ETA `warnings`.
 */
export function planRouteImport(rows, firstRow, existingStops) {
  let numbered = rows.map((row, index) => ({ row, rowNo: firstRow + index }));
  const hasOrder = numbered.every(({ row }) => row.stop_order !== "" && row.stop_order != null && Number.isFinite(Number(row.stop_order)));
  if (hasOrder) numbered = [...numbered].sort((a, b) => Number(a.row.stop_order) - Number(b.row.stop_order)); // sort is stable

  const stops = [];
  const skipped = [];
  const warnings = [];
  const seen = new Set();

  numbered.forEach(({ row, rowNo }) => {
    const name = String(row.name ?? row.stop_name ?? "").trim();
    const skip = (reason) => skipped.push({ row: rowNo, name, reason });
    if (!name) { skip("Stop name is missing."); return; }

    const point = pointOf(row);
    const existing = existingStops.find((stop) => normName(stop.name) === normName(name))
      || (point && existingStops.find((stop) => pointOf(stop) && metresBetween(point, pointOf(stop)) <= DUPLICATE_RADIUS_M))
      || null;

    if (existing && existing.is_active === false) { skip(`"${existing.name}" exists but is inactive. Reactivate it on the Stops page first.`); return; }
    if (existing && !pointOf(existing)) { skip(`"${existing.name}" exists but has no location. Set one on the Stops page first.`); return; }
    if (!existing && !point) { skip("Not an existing stop, and the row has no valid latitude/longitude to create one."); return; }
    if (!existing && name.length > 100) { skip("Name is longer than 100 characters."); return; }

    const key = existing ? `id:${existing.id}` : `new:${normName(name)}`;
    if (seen.has(key)) { skip("This stop appears more than once in the file."); return; }
    seen.add(key);

    const eta = (field, label) => {
      const time = parseTime(row[field]);
      if (time !== null) return time;
      warnings.push(`Row ${rowNo} (${name}): ${label} "${row[field]}" is not a time like 07:30, so it was left blank.`);
      return "";
    };

    stops.push({
      name: existing ? existing.name : name,
      existing,
      create: existing ? null : { name, ...point, address: String(row.address ?? "").trim() || NO_ADDRESS },
      morning_eta: eta("morning_eta", "morning ETA"),
      evening_eta: eta("evening_eta", "evening ETA"),
    });
  });

  return { stops, skipped, warnings };
}
