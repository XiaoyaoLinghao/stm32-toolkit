import type {JSX} from "preact";
import type {LiveRow} from "../chart/series";
import {copy,trendText} from "../presentation/zh";

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
  return<section className="panel values-panel" aria-label={copy.valuesTitle}>
    <div className="panel-heading"><h2>{copy.valuesTitle}</h2>{!fresh&&rows.length>0&&<span className="stale-label">{copy.valuesStale}</span>}</div>
    <div className="table-scroll"><table><thead><tr><th>{copy.watch}</th><th>{copy.value}</th><th>{copy.type}</th><th>{copy.trend}</th><th>{copy.curve}</th></tr></thead>
      <tbody>{rows.map(row=>{
        const key=row.watch.kind==="variable"?`variable:${row.watch.expression}`:`register:${row.watch.registerPath}`;
        const selected=selectedSeries.includes(key);
        return<tr key={key}>
          <td><code>{watchLabel(row)}</code></td>
          <td>{row.errorCode!==null?<span>{copy.readFailed} <details><summary>{copy.diagnostics}</summary><code>{row.errorCode}</code></details></span>:row.displayValue}</td>
          <td>{row.typeName??"-"}</td>
          <td>{trendText(row.trend)}</td>
          <td><button type="button" aria-pressed={selected} onClick={()=>void onSeriesToggle(key)}>{selected?copy.curveShow:copy.curveHide}</button></td>
        </tr>;})}</tbody></table></div>
    {rows.length===0&&<p>{copy.valuesEmpty}</p>}
  </section>;
}
