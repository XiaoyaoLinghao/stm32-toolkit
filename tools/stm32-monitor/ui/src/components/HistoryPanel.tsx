import type {JSX} from "preact";
import {useEffect,useState} from "preact/hooks";
import type {ApiFailure,HistoryPage,HistoryQuery,SampleValue,WatchItem} from "../api/contract";

export type FlattenedHistoryRow={runId:string;sequence:bigint;startOrdinal:bigint;batchValueCount:bigint;capturedAtUtc:string;valueOrdinal:bigint;value:SampleValue;};

export type HistoryPanelProps={
  query:HistoryQuery;
  page:HistoryPage|null;
  failure:ApiFailure|null;
  onLoad:(query:HistoryQuery)=>void|Promise<void>;
  onPage:(cursor:string|undefined)=>void|Promise<void>;
};

export const historyInput=(ns:bigint):string=>new Date(Number(ns/1_000_000n)).toISOString().slice(0,23);
export const inputNs=(value:string):bigint|null=>{
  const ms=Date.parse(`${value}Z`);
  return Number.isFinite(ms)?BigInt(ms)*1_000_000n:null;
};

export function flattenHistory(page:HistoryPage):readonly FlattenedHistoryRow[]{
  return page.batches.flatMap(batch=>batch.values.map((value,index)=>({
    runId:batch.runId,sequence:batch.sequence,startOrdinal:batch.startOrdinal,batchValueCount:batch.batchValueCount,
    capturedAtUtc:batch.capturedAtUtc,valueOrdinal:batch.startOrdinal+BigInt(index),value,
  })));
}
export const historyQueryKey=(query:HistoryQuery):string=>[
  query.startNs.toString(),query.endNs.toString(),query.runId??"",query.groupId??"",
  query.selectorKind??"",query.selector??"",
].join("|");
export const historyRowKey=(row:FlattenedHistoryRow):string=>`${row.runId}:${row.sequence}:${row.valueOrdinal}`;

function watchLabel(watch:WatchItem):string{
  return watch.kind==="variable"?watch.expression:watch.registerPath;
}

export function HistoryPanel({query,page,failure,onLoad,onPage}:HistoryPanelProps):JSX.Element{
  const [start,setStart]=useState(()=>historyInput(query.startNs));
  const [end,setEnd]=useState(()=>historyInput(query.endNs));
  const [visited,setVisited]=useState<readonly (string|undefined)[]>([]);
  const key=historyQueryKey(query);
  const rows=page===null?[]:flattenHistory(page);
  const next=page?.nextCursor??null;
  useEffect(()=>{setVisited([]);setStart(historyInput(query.startNs));setEnd(historyInput(query.endNs));},[key]);
  const load=():void=>{
    const startNs=inputNs(start),endNs=inputNs(end);
    if(startNs===null||endNs===null||endNs<=startNs)return;
    const nextQuery:HistoryQuery={...query,startNs,endNs,limit:Math.min(query.limit??10_000,10_000)};
    delete nextQuery.cursor;
    void onLoad(nextQuery);
  };
  const goNext=():void=>{if(next===null)return;setVisited(v=>[...v,query.cursor]);void onPage(next);};
  const goPrevious=():void=>{if(visited.length===0)return;const prior=visited[visited.length-1];setVisited(v=>v.slice(0,-1));void onPage(prior);};
  return<section className="panel" aria-label="History">
    <h2>History</h2>
    <label>History start <input type="datetime-local" step="0.001" value={start}
      onInput={event=>setStart(event.currentTarget.value)}/></label>
    <label>History end <input type="datetime-local" step="0.001" value={end}
      onInput={event=>setEnd(event.currentTarget.value)}/></label>
    <button type="button" onClick={load}>Load history</button>
    <button type="button" disabled={visited.length===0} onClick={goPrevious}>Previous history page</button>
    <button type="button" disabled={next===null} onClick={goNext}>Next history page</button>
    {failure!==null&&<p role="alert">{failure.code}: {failure.message}</p>}
    <table><thead><tr><th>Captured</th><th>Selector</th><th>Value</th></tr></thead>
      <tbody>{rows.map(row=>{
        const value=row.value;
        return<tr key={historyRowKey(row)}>
          <td>{row.capturedAtUtc}</td>
          <td><code>{watchLabel(value.watch)}</code></td>
          <td>{value.status==="OK"?JSON.stringify(value.typedValue,(_k,v)=>typeof v==="bigint"?v.toString():v):value.code}</td>
        </tr>;
      })}</tbody></table>
    {rows.length===0&&<p>No history rows for this query.</p>}
  </section>;
}
