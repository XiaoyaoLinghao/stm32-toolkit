import type {JSX} from "preact";
import type {LiveRow} from "../chart/series";
import {copy,formatCopy,trendText} from "../presentation/zh";

export type LiveTableProps={
  rows:readonly LiveRow[];
  selectedSeries:readonly string[];
  onSeriesToggle:(key:string)=>void|Promise<void>;
  fresh?:boolean;
};

function watchLabel(row:LiveRow):string{
  return row.watch.kind==="variable"?row.watch.expression:row.watch.registerPath;
}

export function LiveTable({rows,selectedSeries,onSeriesToggle,fresh=true}:LiveTableProps):JSX.Element{
  const full=selectedSeries.length>=8;
  return<section className="panel values-panel" aria-label={copy.valuesTitle}>
    <div className="panel-heading"><h2>{copy.valuesTitle}</h2>{!fresh&&rows.length>0&&<span className="stale-label">{copy.valuesStale}</span>}</div>
    <section className="selected-curves" aria-label={copy.selectedCurves}>
      <p>{formatCopy.selectedCount(selectedSeries.length)}</p>
      {selectedSeries.length>0&&<ul>{selectedSeries.map(key=>{
        const label=key.startsWith("variable:")?`${copy.variables} ${key.slice(9)}`
          :key.startsWith("register:")?`${copy.registers} ${key.slice(9)}`:key;
        return<li key={key}><code>{label}</code><button type="button" aria-label={`${copy.removeCurve}：${label}`}
          onClick={()=>void onSeriesToggle(key)}>{copy.removeCurve}</button></li>;
      })}</ul>}
      {full&&<p className="curve-limit-note">{copy.curveLimitReached}</p>}
    </section>
    <div className="table-scroll"><table><thead><tr><th>{copy.watch}</th><th>{copy.value}</th><th>{copy.type}</th><th>{copy.trend}</th><th>{copy.curve}</th></tr></thead>
      <tbody>{rows.map(row=>{
        const key=row.watch.kind==="variable"?`variable:${row.watch.expression}`:`register:${row.watch.registerPath}`;
        const selected=selectedSeries.includes(key);
        return<tr key={key}>
          <td><code>{watchLabel(row)}</code></td>
          <td>{row.errorCode!==null?<span>{copy.readFailed} <details><summary>{copy.diagnostics}</summary><code>{row.errorCode}</code></details></span>:row.displayValue}</td>
          <td>{row.typeName??"-"}</td>
          <td>{trendText(row.trend)}</td>
          <td><button type="button" aria-pressed={selected} disabled={!selected&&full}
            onClick={()=>void onSeriesToggle(key)}>{selected?copy.curveHide:copy.curveShow}</button></td>
        </tr>;})}</tbody></table></div>
    {rows.length===0&&<p>{copy.valuesEmpty}</p>}
  </section>;
}
