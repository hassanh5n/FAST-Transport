// Saves a road-following line for every route that has none yet.
// Map pages only ever read saved lines (a route without one is drawn stop to stop),
// because asking the routing service for 50 routes on every page load took minutes.
// Lines are built here one route at a time, about one per second as the free service asks.
import { useEffect, useRef, useState } from "react";
import { Banner } from "./ui";
import { btn, colors } from "../theme";
import { buildRouteGeometry, getRoutesMap } from "../services/transportService";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
let running = false; // one build at a time across the app

export default function RoadLineBuilder({ autoStart = false, onDone }) {
  const [missing, setMissing] = useState([]);
  const [progress, setProgress] = useState(null); // { done, total, failed }
  const cancelled = useRef(false);

  const start = async (routes) => {
    if (running || !routes.length) return;
    running = true;
    cancelled.current = false;
    let failed = 0;
    setProgress({ done: 0, total: routes.length, failed });
    try {
      for (let i = 0; i < routes.length && !cancelled.current; i += 1) {
        try {
          const res = await buildRouteGeometry(routes[i].id);
          if (!res.data.has_road_line) failed += 1;
        } catch {
          failed += 1;
        }
        setProgress({ done: i + 1, total: routes.length, failed });
        await sleep(1000);
      }
    } finally {
      running = false;
    }
    if (!cancelled.current) {
      setMissing([]);
      onDone?.();
    }
  };

  useEffect(() => {
    cancelled.current = false;
    getRoutesMap({ noCache: true })
      .then((res) => {
        const todo = (res.data?.routes || []).filter((route) => !route.has_road_line && (route.stops?.length ?? 0) >= 2);
        setMissing(todo);
        if (autoStart) start(todo);
      })
      .catch(() => {});
    return () => { cancelled.current = true; }; // leaving the page stops it; the button resumes later
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (progress) {
    const inProgress = progress.done < progress.total;
    return (
      <Banner variant={progress.failed && !inProgress ? "warning" : "info"}>
        {inProgress
          ? `Building road lines on the map… ${progress.done} / ${progress.total}. You can keep working; leaving this page pauses it.`
          : progress.failed
            ? `Road lines built, except ${progress.failed} the routing service could not draw right now. Those stay as straight lines; try again later.`
            : `Road lines built for ${progress.total} routes.`}
        <div style={{ height: 6, borderRadius: 99, background: colors.borderLight, overflow: "hidden", marginTop: 8 }}>
          <div style={{ height: "100%", width: `${(progress.done / progress.total) * 100}%`, background: colors.accent, transition: "width 0.3s" }} />
        </div>
      </Banner>
    );
  }
  if (!missing.length) return null;
  return (
    <Banner variant="info">
      {missing.length} route{missing.length === 1 ? " is" : "s are"} drawn as straight lines because {missing.length === 1 ? "its road line hasn't" : "their road lines haven't"} been built yet.{" "}
      <button type="button" onClick={() => start(missing)} style={{ ...btn.ghost, padding: "5px 10px", fontSize: 12, marginLeft: 6 }}>
        Build road lines
      </button>
    </Banner>
  );
}
