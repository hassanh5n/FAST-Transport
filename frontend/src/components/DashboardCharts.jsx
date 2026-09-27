import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { colors, fonts } from "../theme";

const tooltipStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  boxShadow: "0 4px 14px rgba(11,45,66,0.12)",
  fontFamily: fonts.body,
  fontSize: 12,
};

function ChartPanel({ title, summary, meta, children }) {
  return (
    <section style={styles.panel}>
      <div style={styles.header}>
        <div>
          <h3 style={styles.title}>{title}</h3>
          <p style={styles.summary}>{summary}</p>
        </div>
        {meta && <span style={styles.actionHint}>{meta}</span>}
      </div>
      <div style={styles.chart}>{children}</div>
    </section>
  );
}

function FleetStatusChart({ buses }) {
  const navigate = useNavigate();
  const data = [
    { name: "Live", value: buses.filter((bus) => bus.status === "live").length, color: colors.successDot },
    { name: "Stale", value: buses.filter((bus) => ["stale", "ping"].includes(bus.status)).length, color: colors.warningDot },
    { name: "Offline", value: buses.filter((bus) => ["offline", "invalid"].includes(bus.status)).length, color: colors.dangerDot },
    { name: "No tracker", value: buses.filter((bus) => bus.status === "no_tracker").length, color: colors.neutralText },
  ];
  const total = buses.length;
  const live = data[0].value;
  const offRoute = buses.filter((bus) => bus.is_off_route).length;

  return (
    <ChartPanel
      title="Fleet health"
      summary={`${live} of ${total} buses live${offRoute ? ` · ${offRoute} off route` : ""}.`}
      meta={`${total} active`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 18, left: -20, bottom: 4 }} onClick={() => navigate("/admin/buses")}>
          <CartesianGrid stroke={colors.borderLight} vertical={false} />
          <XAxis dataKey="name" tick={{ fill: colors.textSecondary, fontSize: 11 }} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tick={{ fill: colors.textMuted, fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.infoBg }} />
          <Bar dataKey="value" name="Buses" radius={[4, 4, 0, 0]} cursor="pointer">
            {data.map((item) => <Cell key={item.name} fill={item.color} />)}
            <LabelList dataKey="value" position="top" fill={colors.textSecondary} fontSize={11} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

function RouteUtilizationChart({ buses }) {
  const navigate = useNavigate();
  const routeMap = buses.reduce((result, bus) => {
    if (!bus.route) return result;
    const key = bus.route.id;
    const row = result[key] || { routeId: key, route: bus.route.name, capacity: 0, allocated: 0, buses: 0 };
    row.capacity += Number(bus.capacity || 0);
    row.allocated += Number(bus.allocated_seats || 0);
    row.buses += 1;
    result[key] = row;
    return result;
  }, {});
  const data = Object.values(routeMap)
    .map((row) => ({ ...row, available: Math.max(row.capacity - row.allocated, 0), utilization: row.capacity ? Math.round((row.allocated / row.capacity) * 100) : 0 }))
    .sort((a, b) => b.utilization - a.utilization)
    .slice(0, 6);

  return (
    <ChartPanel title="Route capacity" summary="Allocated versus available seats on active assigned routes." meta={`${data.length} routes`}>
      {data.length ? (
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout="vertical"
            margin={{ top: 4, right: 28, left: 28, bottom: 4 }}
            barCategoryGap="22%"
            onClick={(event) => {
              const routeId = event?.activePayload?.[0]?.payload?.routeId;
              if (routeId) navigate(`/admin/routes/${routeId}`);
            }}
          >
            <CartesianGrid stroke={colors.borderLight} horizontal={false} />
            <XAxis type="number" allowDecimals={false} tick={{ fill: colors.textMuted, fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis type="category" dataKey="route" width={82} tick={{ fill: colors.textSecondary, fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.infoBg }} formatter={(value, name) => [`${value} seats`, name === "allocated" ? "Allocated" : "Available"]} />
            <Bar dataKey="allocated" stackId="capacity" fill={colors.accent} name="allocated" cursor="pointer" />
            <Bar dataKey="available" stackId="capacity" fill={colors.neutralBg} name="available" radius={[0, 4, 4, 0]} cursor="pointer" />
          </BarChart>
        </ResponsiveContainer>
      ) : <p style={styles.empty}>Route capacity data is not available yet.</p>}
    </ChartPanel>
  );
}

function AttentionChart({ stats }) {
  const navigate = useNavigate();
  const data = [
    { name: "Complaints", value: stats?.pending_complaints || 0, path: "/admin/complaints", color: colors.warningDot },
    { name: "Route requests", value: stats?.open_route_change_requests || 0, path: "/admin/routechangerequests", color: colors.warningText },
    { name: "Unverified fees", value: stats?.unverified_fees || 0, path: "/admin/feeverifications", color: colors.dangerDot },
  ];
  const total = data.reduce((sum, item) => sum + item.value, 0);

  return (
    <ChartPanel title="Admin attention" summary={`${total} open items currently require follow-up.`} meta={`${total} open`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 8, right: 26, left: 28, bottom: 4 }}
          onClick={(event) => {
            const path = event?.activePayload?.[0]?.payload?.path;
            if (path) navigate(path);
          }}
        >
          <CartesianGrid stroke={colors.borderLight} horizontal={false} />
          <XAxis type="number" allowDecimals={false} tick={{ fill: colors.textMuted, fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="name" width={88} tick={{ fill: colors.textSecondary, fontSize: 11 }} tickLine={false} axisLine={false} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: colors.infoBg }} />
          <Bar dataKey="value" name="Open items" radius={[0, 4, 4, 0]} cursor="pointer">
            {data.map((item) => <Cell key={item.name} fill={item.color} />)}
            <LabelList dataKey="value" position="right" fill={colors.textSecondary} fontSize={11} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartPanel>
  );
}

export default function DashboardCharts({ stats, fleetData, showFleet = true }) {
  const buses = fleetData?.buses || [];
  return (
    <div style={styles.grid}>
      {showFleet && <FleetStatusChart buses={buses} />}
      {showFleet && <RouteUtilizationChart buses={buses} />}
      <AttentionChart stats={stats} />
    </div>
  );
}

const styles = {
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, marginBottom: 20 },
  panel: { minWidth: 0, background: "#fff", border: `1px solid ${colors.borderLight}`, borderRadius: 12, padding: "16px 18px 12px", boxShadow: "0 1px 3px rgba(11,45,66,0.06)" },
  header: { minHeight: 52, display: "flex", justifyContent: "space-between", gap: 10 },
  title: { margin: 0, fontSize: 14, fontWeight: 700, color: colors.textPrimary, fontFamily: fonts.heading },
  summary: { margin: "4px 0 0", fontSize: 11.5, lineHeight: 1.45, color: colors.textSecondary },
  actionHint: { color: colors.accent, fontSize: 10.5, whiteSpace: "nowrap", paddingTop: 2 },
  chart: { width: "100%", height: 190 },
  empty: { margin: "50px 0", textAlign: "center", color: colors.textMuted, fontSize: 12 },
};
