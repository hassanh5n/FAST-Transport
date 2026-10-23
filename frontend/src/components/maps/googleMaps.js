// Loads the Google Maps JavaScript API once per page, for the live traffic view.
//
// Google's terms only allow its traffic on a Google map, so traffic gets its own
// map instead of a layer on the MapLibre maps. The key is a browser key: restrict
// it to the site's domains in Google Cloud and cap its daily map loads there.

export const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "";

const CALLBACK = "__fleetcentricGoogleMapsReady";
const authFailureListeners = new Set();
let loading = null;

/** Run `listener` if Google rejects the key (wrong key, API not enabled, daily limit). */
export function onGoogleMapsAuthFailure(listener) {
  authFailureListeners.add(listener);
  return () => authFailureListeners.delete(listener);
}

/** Resolves with `google.maps` once the API is ready. */
export function loadGoogleMaps() {
  if (!GOOGLE_MAPS_API_KEY) return Promise.reject(new Error("VITE_GOOGLE_MAPS_API_KEY is not set."));
  if (window.google?.maps?.importLibrary) return Promise.resolve(window.google.maps);
  if (loading) return loading;

  loading = new Promise((resolve, reject) => {
    // Google calls this global when the key is refused, after the script has loaded.
    window.gm_authFailure = () => authFailureListeners.forEach((listener) => listener());
    window[CALLBACK] = () => {
      delete window[CALLBACK];
      resolve(window.google.maps);
    };
    const script = document.createElement("script");
    script.src = "https://maps.googleapis.com/maps/api/js?" + new URLSearchParams({
      key: GOOGLE_MAPS_API_KEY, v: "weekly", loading: "async", callback: CALLBACK,
    });
    script.async = true;
    script.onerror = () => {
      script.remove();
      loading = null; // a later visit may try again
      reject(new Error("Google Maps could not be loaded."));
    };
    document.head.appendChild(script);
  });
  return loading;
}
