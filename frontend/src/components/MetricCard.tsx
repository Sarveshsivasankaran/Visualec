import { ReactNode } from "react";

export default function MetricCard({
  label,
  value,
  detail,
  icon,
  tone,
  badge,
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
  tone?: "good" | "warn" | "danger" | "neutral";
  badge?: ReactNode;
}) {
  return (
    <article className={`metric-card ${tone ? `tone-${tone}` : ""}`}>
      <div className="metric-icon">{icon}</div>
      <div>
        <div className="metric-header">
          <p>{label}</p>
          {badge}
        </div>
        <strong>{value}</strong>
        <span>{detail}</span>
      </div>
    </article>
  );
}

