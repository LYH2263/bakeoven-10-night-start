import { useEffect, useState } from "react";
import { api } from "../api/client";
type P = { id: number; name: string }; type O = { id: number; label: string };
type B = { id: number; code: string; product_name?: string; oven_label?: string; start_min: number; start_day_offset?: number; night_start?: boolean; ferment_end?: number; bake_end?: number; status: string };

const DAY = 24 * 60;
function pad(n: number) { return String(n).padStart(2, "0"); }
function fmt(m: number) { const h = Math.floor(((m % DAY) + DAY) % DAY / 60), mm = ((m % DAY) + DAY) % DAY % 60; return `${pad(h)}:${pad(mm)}`; }
// Signed minutes: negative = previous-day wall clock, positive = today.
function fmtDay(m: number) { return m < 0 ? `前一日 ${fmt(m)}` : fmt(m); }

export default function BatchesPage() {
  const [products, setProducts] = useState<P[]>([]);
  const [ovens, setOvens] = useState<O[]>([]);
  const [rows, setRows] = useState<B[]>([]);
  const [pid, setPid] = useState<number | "">(""); const [oid, setOid] = useState<number | "">("");
  const [start, setStart] = useState(11 * 60); const [night, setNight] = useState(false);
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  const reload = () => api<B[]>("/batches").then(setRows);
  useEffect(() => {
    api<P[]>("/products").then(p => { setProducts(p); if (p[0]) setPid(p[0].id); });
    api<O[]>("/ovens").then(o => { setOvens(o); if (o[0]) setOid(o[0].id); });
    reload();
  }, []);
  // Toggling the previous-day marker flips to a sensible signed default.
  function toggleNight(v: boolean) {
    setNight(v);
    if (v && start >= 0) setStart(-60);
    if (!v && start < 0) setStart(9 * 60);
  }
  async function create() {
    setMsg(""); setErr("");
    try {
      const b = await api<B>("/batches", {
        method: "POST",
        body: JSON.stringify({
          product_id: pid, oven_id: oid,
          start_min: start,
          ...(night ? { start_day_offset: -1 } : {}),
        }),
      });
      setMsg(`已排产 ${b.code}${night ? "（前一日夜间开工）" : ""}`);
      reload();
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
  }
  const invalid = night ? start >= 0 : start < 0;
  return (<>
    <h2>批次</h2>
    <div className="toolbar">
      <select value={pid} onChange={e => setPid(Number(e.target.value))}>{products.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <select value={oid} onChange={e => setOid(Number(e.target.value))}>{ovens.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}</select>
      <label className="night-toggle">
        <input type="checkbox" checked={night} onChange={e => toggleNight(e.target.checked)} />
        前一日夜间开工
      </label>
      <label>开工分钟 <input type="number" value={start} onChange={e => setStart(Number(e.target.value))} style={{ width: 90 }} /></label>
      <span className="hint">{night ? `相对当日 0 点的负分钟，即 ${fmtDay(start)} 开酵` : `当日 0 点起算，即 ${fmt(start)} 开工`}</span>
      <button onClick={create} disabled={invalid}>创建生产批次</button>
    </div>
    {invalid && <div className="err">{night ? "夜间开工必须填负的开工分钟（相对当日 0 点）" : "当日开工分钟不可为负；如需夜间请勾选前一日标记"}</div>}
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    <table className="table"><thead><tr><th>批次</th><th>开工日</th><th>产品</th><th>炉位</th><th>发酵</th><th>烘烤结束</th><th>状态</th></tr></thead>
    <tbody>{rows.map(b => {
      const isNight = b.night_start === true || b.start_day_offset === -1;
      return <tr key={b.id} className={isNight ? "row-night" : ""}><td className="mono">{b.code}</td>
        <td>{isNight ? <span className="tag tag-night" title="头天夜间发酵，占炉跨过当日 0 点">前一日 · 夜间开工</span> : <span className="tag">当日</span>}</td>
        <td>{b.product_name}</td><td>{b.oven_label}</td>
        <td className="mono">{fmtDay(b.start_min)}–{fmt(b.ferment_end ?? b.start_min)}</td>
        <td className="mono">{fmt(b.bake_end ?? b.start_min)}</td><td>{b.status}</td></tr>;
    })}</tbody></table>
  </>);
}
