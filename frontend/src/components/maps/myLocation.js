// "Show my location" on every map: a button that finds the viewer through the browser,
// then draws a blue dot with an accuracy circle and follows them as they move.
//
// Nothing is asked for until the button is pressed, so opening a page never triggers
// the browser's permission prompt. The position stays in the browser: it is only drawn,
// never sent to the server (the driver's trip sharing is separate, in DriverTrip).
// Browsers allow location only on HTTPS or localhost.
import maplibregl from "maplibre-gl";

export const LOCATION_OPTIONS = { enableHighAccuracy: true, timeout: 10000, maximumAge: 10000 };

export const canLocate = () => typeof navigator !== "undefined" && "geolocation" in navigator && window.isSecureContext;

/** Adds the MapLibre locate button (top right, under the zoom buttons) to a map. */
export function addMyLocationControl(map, position = "top-right") {
  if (!canLocate()) return null;
  const control = new maplibregl.GeolocateControl({
    positionOptions: LOCATION_OPTIONS,
    trackUserLocation: true,  // keep the dot moving while the page is open
    showAccuracyCircle: true,
    showUserLocation: true,
    fitBoundsOptions: { maxZoom: 15 },
  });
  map.addControl(control, position);
  return control;
}

/** A short, human message for a failed location request. */
export function locationErrorMessage(error) {
  if (!error) return "";
  if (error.code === 1) return "Location is blocked for this site. Allow it in your browser's site settings to show where you are.";
  if (error.code === 3) return "Finding your location took too long. Try again outside or near a window.";
  return "Your location could not be found right now.";
}
