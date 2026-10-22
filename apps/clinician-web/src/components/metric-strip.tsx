import type { DashboardMetric } from "@/lib/demo-data";

interface MetricStripProps {
  metrics: readonly DashboardMetric[];
}

export function MetricStrip({ metrics }: MetricStripProps) {
  return (
    <dl className="metric-strip">
      {metrics.map((metric) => (
        <div className={`metric metric-${metric.tone}`} key={metric.label}>
          <dt>{metric.label}</dt>
          <dd>{metric.value}</dd>
          <dd className="metric-detail">{metric.detail}</dd>
        </div>
      ))}
    </dl>
  );
}
