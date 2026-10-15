import type {JSX} from "preact";
import {useEffect,useState} from "preact/hooks";
import type {ApiFailure,HistoryPage,HistoryQuery,SampleValue,WatchItem} from "../api/contract";
import {copy} from "../presentation/zh";
import {FailureMessage} from "./FailureMessage";

export type FlattenedHistoryRow={runId:string;sequence:bigint;startOrdinal:bigint;batchValueCount:bigint;capturedAtUtc:string;valueOrdinal:bigint;value:SampleValue;};

export type HistoryPanelProps={
  query:HistoryQuery|null;
  page:HistoryPage|null;
  failure:ApiFailure|null;
  onLoad:(query:HistoryQuery)=>void|Promise<void>;
  onPage:(cursor:string|undefined)=>void|Promise<void>;
};

export const historyInput=(ns:bigint):string=>{
  const ms=ns/1_000_000n;
  if(ms>8_640_000_000_000_000n||ms< -8_640_000_000_000_000n)return "";
  return new Date(Number(ms)).toISOString().slice(0,23);
};
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
  const [start,setStart]=useState(()=>query===null?"":historyInput(query.startNs));
  const [end,setEnd]=useState(()=>query===null?"":historyInput(query.endNs));
  const [validation,setValidation]=useState(false);
  const [visited,setVisited]=useState<readonly (string|undefined)[]>([]);
  const key=query===null?"":historyQueryKey(query);
  const rows=page===null?[]:flattenHistory(page);
  const next=page?.nextCursor??null;
  useEffect(()=>{setVisited([]);if(query!==null){setStart(historyInput(query.startNs));setEnd(historyInput(query.endNs));setValidation(false);}},[key]);
  const load=():void=>{
    const startNs=inputNs(start),endNs=inputNs(end);
    if(startNs===null||endNs===null||endNs<=startNs){setValidation(true);return;}
    setValidation(false);
    const nextQuery:HistoryQuery={...(query??{}),startNs,endNs,limit:Math.min(query?.limit??10_000,10_000)};
    delete nextQuery.cursor;
    void onLoad(nextQuery);
  };
  const goNext=():void=>{if(next===null)return;setVisited(v=>[...v,query?.cursor]);void onPage(next);};
  const goPrevious=():void=>{if(visited.length===0)return;const prior=visited[visited.length-1];setVisited(v=>v.slice(0,-1));void onPage(prior);};
  return<section className="panel history-panel" aria-label={copy.historyTitle}>
    <h2>{copy.historyTitle}</h2>
    <p className="hint">{copy.historyHint}</p>
    <div className="form-row"><label>{copy.historyStart} <input type="datetime-local" step="0.001" value={start}
      onInput={event=>setStart(event.currentTarget.value)}/></label>
    <label>{copy.historyEnd} <input type="datetime-local" step="0.001" value={end}
      onInput={event=>setEnd(event.currentTarget.value)}/></label>
    <button type="button" className="primary" onClick={load}>{copy.historyLoad}</button></div>
    {validation&&<p role="alert">{copy.invalidRange}</p>}
    {failure!==null&&<FailureMessage failure={failure}/>}
    {query===null&&<p className="empty-state">{copy.historyChoose}</p>}
    <div className="table-scroll"><table><thead><tr><th>{copy.historyCaptured}</th><th>{copy.watch}</th><th>{copy.value}</th></tr></thead>
      <tbody>{rows.map(row=>{
        const value=row.value;
        return<tr key={historyRowKey(row)}>
          <td>{row.capturedAtUtc}</td>
          <td><code>{watchLabel(value.watch)}</code></td>
          <td>{value.status==="OK"?JSON.stringify(value.typedValue,(_k,v)=>typeof v==="bigint"?v.toString():v):<span>{copy.readFailed} <details><summary>{copy.diagnostics}</summary><code>{value.code}</code></details></span>}</td>
        </tr>;
      })}</tbody></table></div>
    {query!==null&&rows.length===0&&<p>{copy.historyEmpty}</p>}
    <div className="pagination"><button type="button" disabled={visited.length===0} onClick={goPrevious}>{copy.previousPage}</button>
    <button type="button" disabled={next===null} onClick={goNext}>{copy.nextPage}</button></div>
  </section>;
}
