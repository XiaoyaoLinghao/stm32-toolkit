import type {JSX} from "preact";
import type {LiveRow} from "../chart/series";

export type LiveTableProps={
  rows:readonly LiveRow[];
  selectedSeries:readonly string[];
  onSeriesToggle:(key:string)=>void|Promise<void>;
};

function watchLabel(row:LiveRow):string{
  return row.watch.kind==="variable"?row.watch.expression:row.watch.registerPath;
}

export function LiveTable({rows,selectedSeries,onSeriesToggle}:LiveTableProps):JSX.Element{
  return<section className="panel" aria-label="Live values">
    <h2>Live values</h2>
    <table><thead><tr><th>Selector</th><th>Value</th><th>Type</th><th>Trend</th><th>Chart</th></tr></thead>
      <tbody>{rows.map(row=>{
        const key=row.watch.kind==="variable"?`variable:${row.watch.expression}`:`register:${row.watch.registerPath}`;
        const selected=selectedSeries.includes(key);
        return<tr key={key}>
          <td><code>{watchLabel(row)}</code></td>
          <td>{row.errorCode!==null?<em>{row.errorCode}</em>:row.displayValue}</td>
          <td>{row.typeName??"-"}</td>
          <td>{row.trend}</td>
          <td><button type="button" aria-pressed={selected} onClick={()=>void onSeriesToggle(key)}>{selected?"On":"Off"}</button></td>
        </tr>;})}</tbody></table>
    {rows.length===0&&<p>No watches in the selected group.</p>}
  </section>;
}
