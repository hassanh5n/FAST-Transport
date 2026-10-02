// Shared TanStack Query cache for API GETs (see api.js).
import { QueryClient } from "@tanstack/react-query";

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

// Wipe on logout / new login so one user never sees another's data.
export const clearQueryCache = () => queryClient.clear();
