import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";
import path from "path";

const DAY = 24 * 60 * 60;

export default defineConfig({
  plugins: [
    react(),
    // A service worker (production builds only) keeps the app shell and the base map
    // in the browser, so repeat visits open without waiting on the network. API data
    // is never stored here (see services/queryClient.js), and neither is Google's
    // traffic map, whose terms forbid caching it.
    VitePWA({
      registerType: "prompt", // a new version waits for the user to reload (UpdatePrompt)
      injectRegister: false,
      manifest: false,
      workbox: {
        // Code plus the images the app shows; the unused brand files in public/ stay out.
        globPatterns: [
          "**/*.{js,css,html,woff2}",
          "{favicon-32,icon-192,apple-touch-icon,fleetcentric-mark,fleetcentric-wordmark-white}.png",
        ],
        maximumFileSizeToCacheInBytes: 3 * 1024 * 1024, // the MapLibre chunk is ~1 MB
        navigateFallback: "index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/static\//],
        cleanupOutdatedCaches: true,
        runtimeCaching: [
          {
            // Map tiles sit under a dated version path, so a stored tile never goes stale.
            urlPattern: /^https:\/\/tiles\.openfreemap\.org\/planet\/[^/]+\/\d+\/\d+\/\d+\.pbf$/,
            handler: "CacheFirst",
            options: {
              cacheName: "map-tiles",
              expiration: { maxEntries: 1000, maxAgeSeconds: 14 * DAY, purgeOnQuotaError: true },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // Style, fonts, sprites and the tile index: drawn from the stored copy, then refreshed.
            urlPattern: /^https:\/\/tiles\.openfreemap\.org\//,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "map-style",
              expiration: { maxEntries: 300, maxAgeSeconds: 30 * DAY, purgeOnQuotaError: true },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      react: path.resolve("./node_modules/react"),
      "react-dom": path.resolve("./node_modules/react-dom"),
    },
  },
});
