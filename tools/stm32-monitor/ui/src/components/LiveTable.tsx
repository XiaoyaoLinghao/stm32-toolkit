import type {JSX} from "preact";
import type {LiveRow} from "../chart/series";
import {copy,formatCopy,trendText} from "../presentation/zh";
import {watchFullLabel,watchKey,watchLabel,watchLabelFromKey} from "../state/watch";

export type LiveTableProps={
  rows:readonly LiveRow[];
  selectedSeries:readonly string[];
  onSeriesToggle:(key:string)=>void|Promise<void>;
  fresh?:boolean;
  collapsed?:boolean;
  waiting?:"connection"|"start"|undefined;
};

export function LiveTable({rows,selectedSeries,onSeriesToggle,fresh=true,collapsed=false,waiting}:LiveTableProps):JSX.Element{
  const full=selectedSeries.length>=8;
  return<section className={`panel values-panel ${collapsed?"collapsed":""}`} aria-label={copy.valuesTitle}>
    <div className="panel-heading"><h2>{copy.valuesTitle}</h2><span>{formatCopy.selectedCount(selectedSeries.length)}</span>
      {selectedSeries.length>0&&<details className="selected-curves" hidden={collapsed}>
      <summary>{copy.selectedCurves}</summary><div className="selected-curves-popover">
      {selectedSeries.length>0&&<ul>{selectedSeries.map(key=>{
        const label=key.startsWith("variable:")?`${copy.variables} ${watchLabelFromKey(key)}`:
          key.startsWith("register:")?`${copy.registers} ${watchLabelFromKey(key)}`:watchLabelFromKey(key);
        return<li key={key}><code>{label}</code><button type="button" aria-label={`${copy.removeCurve}：${label}`}
          onClick={()=>void onSeriesToggle(key)}>{copy.removeCurve}</button></li>;
      })}</ul>}
      {full&&<p className="curve-limit-note">{copy.curveLimitReached}</p>}
      </div></details>}
      {!fresh&&waiting===undefined&&rows.length>0&&<span className="stale-label">{copy.valuesStale}</span>}</div>
    <div className="table-scroll" hidden={collapsed}><table><thead><tr><th>{copy.watch}</th><th>{copy.value}</th><th>{copy.historyCaptured}</th><th>{copy.type}</th><th>{copy.trend}</th><th>{copy.curve}</th></tr></thead>
      <tbody>{rows.map(row=>{
        const key=watchKey(row.watch);
        const selected=selectedSeries.includes(key);
        return<tr key={key}>
          <td><code title={watchFullLabel(row.watch)} aria-label={watchFullLabel(row.watch)}>{watchLabel(row.watch)}</code></td>
          <td>{row.errorCode!==null?<span>{copy.readFailed} <details><summary>{copy.diagnostics}</summary><code>{row.errorCode}</code></details></span>:
            waiting!==undefined&&row.displayValue===""&&row.capturedAtUtc===""?waiting==="connection"?copy.valuesAwaitConnection:copy.valuesAwaitStart:row.displayValue}</td>
          <td><time>{row.capturedAtUtc||"-"}</time></td>
          <td>{row.typeName??"-"}</td>
          <td>{trendText(row.trend)}</td>
          <td><button type="button" aria-pressed={selected} disabled={!selected&&full}
            onClick={()=>void onSeriesToggle(key)}>{selected?copy.curveHide:copy.curveShow}</button></td>
        </tr>;})}</tbody></table></div>
    {rows.length===0&&!collapsed&&<p>{copy.valuesEmpty}</p>}
  </section>;
}
