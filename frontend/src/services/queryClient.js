// Shared TanStack Query cache for API GETs (see api.js).
import { QueryClient } from "@tanstack/react-query";
import { persistQueryClient } from "@tanstack/react-query-persist-client";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import { del, get, set } from "idb-keyval";

const DAY = 24 * 60 * 60 * 1000;
const PERSIST_KEY = "fleetcentric-query-cache";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2 * 60 * 1000, // reuse data for 2 min without a new request
      gcTime: 10 * 60 * 1000,
      retry: false,             // axios interceptor already handles 401 refresh
      refetchOnWindowFocus: false,
    },
  },
});

// Responses kept across visits, so a page can draw its last copy at once while the
// fresh one loads (see api.getSWR): the route network, the signed-in user's
// dashboard summary and the admin fleet snapshot, which is shown as "last seen",
// never as live. Sign-out and sign-in wipe them (clearQueryCache).
export const FLEET_SNAPSHOT_KEY = ["fleet-snapshot"];
const PERSISTED_URLS = [/\/api\/routes\/map\/$/, /\/api\/dashboard\/$/];

export const isPersistedUrl = (url) => PERSISTED_URLS.some((rx) => rx.test(url));
export const PERSISTED_GC_TIME = DAY; // a query is only saved while it is still in memory
queryClient.setQueryDefaults(FLEET_SNAPSHOT_KEY, { gcTime: DAY });

const isPersisted = (query) =>
  query.state.status === "success" &&
  (query.queryKey[0] === FLEET_SNAPSHOT_KEY[0] || (query.queryKey[0] === "api" && isPersistedUrl(query.queryKey[1])));

let restored = Promise.resolve();
if (typeof indexedDB !== "undefined") {
  const [, restore] = persistQueryClient({
    queryClient,
    persister: createAsyncStoragePersister({
      storage: { getItem: get, setItem: set, removeItem: del },
      key: PERSIST_KEY,
      throttleTime: 2000,
    }),
    maxAge: DAY,
    buster: "1", // bump when a saved response's shape changes
    dehydrateOptions: { shouldDehydrateQuery: isPersisted },
  });
  restored = restore.catch(() => {}); // a private window may refuse IndexedDB: just start empty
}
/** Resolves once saved responses from earlier visits are back in memory. */
export const cacheRestored = restored;

// Wipe on logout / new login so one user never sees another's data. The saved copy
// is deleted directly too: sign-out reloads the page before a throttled save runs.
export const clearQueryCache = () => {
  queryClient.clear();
  if (typeof indexedDB !== "undefined") del(PERSIST_KEY).catch(() => {});
};
