import { ReactNode } from "react";

export default function MetricCard({label,value,detail,icon}:{label:string;value:string;detail:string;icon:ReactNode}) {
  return <article className="metric-card"><div className="metric-icon">{icon}</div><div><p>{label}</p><strong>{value}</strong><span>{detail}</span></div></article>;
}
