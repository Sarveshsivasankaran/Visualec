import { useEffect, useState } from "react";
import { Download, Leaf, TrendingDown, Zap } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { apiBase, request } from "../api";
import MetricCard from "../components/MetricCard";
import { Energy } from "../types";

export default function Analytics({energy:live}:{energy?:Energy}) {
  const [period,setPeriod]=useState("daily");const [energy,setEnergy]=useState<Energy|undefined>(live);
  useEffect(()=>{request<Energy>(`/api/analytics/summary?period=${period}`).then(setEnergy).catch(()=>undefined)},[period,live?.relay_activations]);
  const data=energy?.zone_usage.map((item,i)=>({...item,minutes:Math.round(item.runtime_seconds/60),fill:["#22d3ee","#34d399","#f59e0b"][i%3]}))??[];
  return <div className="page"><header className="topbar"><div><p className="eyebrow">PERFORMANCE / INSIGHTS</p><h1>Energy analytics</h1></div><div className="top-actions"><div className="period-tabs">{["daily","weekly","monthly"].map(p=><button className={period===p?"active":""} onClick={()=>setPeriod(p)} key={p}>{p}</button>)}</div><a className="button ghost" href={`${apiBase}/api/analytics/export`}><Download size={17}/>Export CSV</a></div></header>
    <section className="metrics-grid"><MetricCard label="Adaptive energy" value={`${energy?.actual_energy_kwh.toFixed(3)??0} kWh`} detail="Measured from state transitions" icon={<Zap/>}/><MetricCard label="All-on baseline" value={`${energy?.baseline_energy_kwh.toFixed(3)??0} kWh`} detail="Reference consumption" icon={<TrendingDown/>}/><MetricCard label="Energy avoided" value={`${energy?.energy_saved_kwh.toFixed(3)??0} kWh`} detail="Adaptive grid contribution" icon={<Leaf/>}/></section>
    <section className="analytics-grid"><article className="panel chart-panel"><div className="panel-heading"><div><strong>Zone runtime</strong><small>Minutes powered during selected period</small></div></div><div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><BarChart data={data}><CartesianGrid vertical={false} stroke="#213044"/><XAxis dataKey="name" stroke="#7c8ba1" tickLine={false}/><YAxis stroke="#7c8ba1" tickLine={false}/><Tooltip cursor={{fill:"#ffffff08"}} contentStyle={{background:"#101c2b",border:"1px solid #2b3b4f",borderRadius:12}}/><Bar dataKey="minutes" radius={[7,7,0,0]}>{data.map((item,index)=><Cell fill={item.fill} key={index}/>)}</Bar></BarChart></ResponsiveContainer></div></article><article className="panel savings-panel"><div className="saving-ring" style={{"--value":`${Math.min(100,((energy?.energy_saved_kwh??0)/(energy?.baseline_energy_kwh||1))*100)}%`} as React.CSSProperties}><div><strong>{Math.round(((energy?.energy_saved_kwh??0)/(energy?.baseline_energy_kwh||1))*100)}%</strong><span>saved</span></div></div><h2>Adaptive efficiency</h2><p>Loads run only when their mapped zone passes the occupancy persistence rules.</p><dl><div><dt>Cost avoided</dt><dd>₹{energy?.cost_saved.toFixed(2)??"0.00"}</dd></div><div><dt>Relay starts</dt><dd>{energy?.relay_activations??0}</dd></div></dl></article></section>
  </div>;
}
