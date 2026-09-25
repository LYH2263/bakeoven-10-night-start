import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
type Block = { batch_id: number; code: string; oven_id: number; oven_label: string; phase: string; start_min: number; end_min: number; night_start?: boolean };
// The board covers the whole current day; only the after-midnight slice of any
// previous-night batch is returned (already clipped by the API), so every block
// lies within [0, 24h).
const DAY_START = 0, DAY_END = 24 * 60, SPAN = DAY_END - DAY_START;
function pct(m: number) { return ((m - DAY_START) / SPAN) * 100; }
export default function GanttPage() {
  const [blocks, setBlocks] = useState<Block[]>([]);
  useEffect(() => { api<Block[]>("/gantt").then(setBlocks); }, []);
  const rows = useMemo(() => {
    const map = new Map<number, { label: string; blocks: Block[] }>();
    for (const b of blocks) {
      if (!map.has(b.oven_id)) map.set(b.oven_id, { label: b.oven_label, blocks: [] });
      map.get(b.oven_id)!.blocks.push(b);
    }
    return [...map.entries()];
  }, [blocks]);
  return (<>
    <h2>甘特（生产占炉）</h2>
    <div className="night-legend">
      <span className="tag tag-night">前一日 · 夜间开工</span>
      <span>仅画当日 0 点后仍占炉的部分；冲突按完整区间（含跨 0 点段）判定</span>
    </div>
    <div className="axis"><div /><div className="axis-scale"><span>00:00</span><span>06:00</span><span>12:00</span><span>18:00</span><span>24:00</span></div></div>
    <div className="gantt">
      {rows.map(([oid, row]) => (
        <div className="gantt-row" key={oid}>
          <div>{row.label}</div>
          <div className="gantt-track">
            {row.blocks.map((b, i) => (
              <div key={i} className={`gantt-block ${b.phase}${b.night_start ? " night" : ""}`}
                style={{ left: `${pct(b.start_min)}%`, width: `${((b.end_min - b.start_min) / SPAN) * 100}%` }}
                title={`${b.code} ${b.phase === "ferment" ? "发酵" : "烘烤"}${b.night_start ? "（前一日夜间开工）" : ""}`}>
                {b.night_start && <span className="night-mark">夜</span>}
                {b.code}/{b.phase === "ferment" ? "酵" : "烤"}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  </>);
}
