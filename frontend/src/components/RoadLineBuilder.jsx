// Shows routes still waiting for their road-following line.
// The server builds the lines itself in the background (backend road_lines.py),
// about one route a second, whenever stops change or the map is loaded. This only
// reports progress and refreshes the map once they land.
import { useEffect, useRef, useState } from "react";
import { Banner } from "./ui";
import { getRoutesMap } from "../services/transportService";

const POLL_MS = 10000;

const countMissing = (res) =>
  (res.data?.routes || []).filter((route) => !route.has_road_line && (route.stops?.length ?? 0) >= 2).length;

export default function RoadLineBuilder({ onDone }) {
  const [missing, setMissing] = useState(0);
  const last = useRef(null);
  const onDoneRef = useRef(onDone);
  useEffect(() => { onDoneRef.current = onDone; }, [onDone]);

  useEffect(() => {
    let timer;
    let stopped = false;
    const check = () =>
      getRoutesMap({ noCache: true })
        .then((res) => {
          if (stopped) return;
          const count = countMissing(res);
          if (last.current !== null && count < last.current) onDoneRef.current?.();
          last.current = count;
          setMissing(count);
          if (count) timer = setTimeout(check, POLL_MS);
        })
        .catch(() => { if (!stopped) timer = setTimeout(check, POLL_MS * 3); });
    check();
    return () => { stopped = true; clearTimeout(timer); };
  }, []);

  if (!missing) return null;
  return (
    <Banner variant="info">
      Building road lines for {missing} route{missing === 1 ? "" : "s"} in the background. Until then {missing === 1 ? "it is" : "they are"} drawn
      as straight lines; the map updates by itself.
    </Banner>
  );
}
