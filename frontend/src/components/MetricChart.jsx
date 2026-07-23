import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { anomalyRegions, shortTime } from "../theme";

export default function MetricChart({ title, points, dataKey, color, unit }) {
  const regions = anomalyRegions(points);
  const gradId = `grad-${dataKey}`;

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>
          <span className="legend-swatch" style={{ background: color }} />
          {title}
        </h3>
        {regions.length > 0 && (
          <span className="chip both">{regions.length} anomaly region{regions.length === 1 ? "" : "s"}</span>
        )}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={points} margin={{ top: 4, right: 10, left: -14, bottom: 0 }}>
          <defs>
            <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#26313f" vertical={false} />
          <XAxis
            dataKey="window_start"
            tickFormatter={shortTime}
            stroke="#8b98a9"
            fontSize={11}
            minTickGap={48}
          />
          <YAxis stroke="#8b98a9" fontSize={11} width={48} />
          <Tooltip
            contentStyle={{ background: "#131a24", border: "1px solid #26313f", borderRadius: 8 }}
            labelFormatter={(v) => shortTime(v)}
            formatter={(val) => [`${Number(val).toFixed(2)}${unit || ""}`, title]}
          />
          {regions.map(([x1, x2], i) => (
            <ReferenceArea key={i} x1={x1} x2={x2} fill="#f87171" fillOpacity={0.16} stroke="#f87171" strokeOpacity={0.35} />
          ))}
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={color}
            strokeWidth={1.8}
            fill={`url(#${gradId})`}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
