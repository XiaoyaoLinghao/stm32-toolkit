import type {JSX} from "preact";
import {useEffect,useRef,useState} from "preact/hooks";
import type {ApiFailure,HistoryPage,HistoryQuery,SampleValue,WatchItem} from "../api/contract";
import {copy} from "../presentation/zh";
import type {HistoryInFlight} from "../state/model";
import {FailureMessage} from "./FailureMessage";

export type FlattenedHistoryRow={runId:string;sequence:bigint;startOrdinal:bigint;batchValueCount:bigint;capturedAtUtc:string;valueOrdinal:bigint;value:SampleValue;};

export type HistoryPanelProps={
  query:HistoryQuery|null;
  page:HistoryPage|null;
  inFlight?:HistoryInFlight|null;
  failure:ApiFailure|null;
  cursorStack?:readonly (string|undefined)[];
  busy?:boolean;
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
const maxHistoryNs=9_223_372_036_854_775_807n;
const utc=(ns:bigint):string=>new Date(Number(ns/1_000_000n)).toISOString();
const range=(query:HistoryQuery):string=>`${utc(query.startNs)} 至 ${utc(query.endNs)}`;

function watchLabel(watch:WatchItem):string{
  return watch.kind==="variable"?watch.expression:watch.registerPath;
}

export function HistoryPanel({query,page,inFlight=null,failure,cursorStack=[],busy=false,onLoad,onPage}:HistoryPanelProps):JSX.Element{
  const [start,setStart]=useState(()=>query===null?"":historyInput(query.startNs));
  const [end,setEnd]=useState(()=>query===null?"":historyInput(query.endNs));
  const [validation,setValidation]=useState(false);
  const synced=useRef({start:query===null?"":historyInput(query.startNs),end:query===null?"":historyInput(query.endNs)});
  const draft=useRef({...synced.current});
  const actionBusy=useRef(false);
  const acceptedStart=query===null?"":historyInput(query.startNs);
  const acceptedEnd=query===null?"":historyInput(query.endNs);
  const rows=page===null?[]:flattenHistory(page);
  const next=page?.nextCursor??null;
  useEffect(()=>{
    const clean=draft.current.start===synced.current.start&&draft.current.end===synced.current.end;
    synced.current={start:acceptedStart,end:acceptedEnd};
    if(clean){draft.current={start:acceptedStart,end:acceptedEnd};setStart(acceptedStart);setEnd(acceptedEnd);setValidation(false);}
  },[acceptedStart,acceptedEnd]);
  const run=(operation:()=>void|Promise<void>):void=>{
    if(busy||inFlight!==null||actionBusy.current)return;
    actionBusy.current=true;
    try{void Promise.resolve(operation()).then(()=>{actionBusy.current=false;},()=>{actionBusy.current=false;});}
    catch(error){actionBusy.current=false;throw error;}
  };
  const load=():void=>{
    if(busy||inFlight!==null||actionBusy.current)return;
    const startNs=inputNs(draft.current.start),endNs=inputNs(draft.current.end);
    if(startNs===null||endNs===null||startNs<0n||endNs>maxHistoryNs||endNs<=startNs){setValidation(true);return;}
    setValidation(false);
    const nextQuery:HistoryQuery={...(query??{}),startNs,endNs,limit:Math.min(query?.limit??10_000,10_000)};
    delete nextQuery.cursor;
    run(()=>onLoad(nextQuery));
  };
  const goNext=():void=>{if(next===null)return;run(()=>onPage(next));};
  const goPrevious=():void=>{if(cursorStack.length===0)return;run(()=>onPage(cursorStack[cursorStack.length-1]));};
  return<section className="panel history-panel" aria-label={copy.historyTitle}>
    <h2>{copy.historyTitle}</h2>
    <p className="hint">{copy.historyHint}</p>
    <div className="form-row"><label>{copy.historyStart} <input type="datetime-local" step="0.001" value={start}
      onInput={event=>{draft.current.start=event.currentTarget.value;setStart(draft.current.start);}}/></label>
    <label>{copy.historyEnd} <input type="datetime-local" step="0.001" value={end}
      onInput={event=>{draft.current.end=event.currentTarget.value;setEnd(draft.current.end);}}/></label>
    <button type="button" className="primary" disabled={busy||inFlight!==null} onClick={load}>{copy.historyLoad}</button></div>
    {validation&&<p role="alert">{copy.invalidRange}</p>}
    {failure!==null&&<FailureMessage failure={failure}/>}
    {inFlight!==null&&<p role="status" className="history-range">{copy.historyPendingRange}：{range(inFlight.query)}</p>}
    {query!==null&&<p className="history-range">{copy.historyCurrentRange}：{range(query)}（{copy.historyHalfOpen}）</p>}
    {inFlight!==null&&query!==null&&<p className="hint">{copy.historyPreviousResult}</p>}
    {query===null&&inFlight===null&&<p className="empty-state">{copy.historyChoose}</p>}
    <div className="table-scroll"><table><thead><tr><th>{copy.historyCaptured}</th><th>{copy.watch}</th><th>{copy.value}</th><th>{copy.historySource}</th></tr></thead>
      <tbody>{rows.map(row=>{
        const value=row.value;
        return<tr key={historyRowKey(row)}>
          <td>{row.capturedAtUtc}</td>
          <td><code>{watchLabel(value.watch)}</code></td>
          <td>{value.status==="OK"?JSON.stringify(value.typedValue,(_k,v)=>typeof v==="bigint"?v.toString():v):<span>{copy.readFailed} <details><summary>{copy.diagnostics}</summary><code>{value.code}</code></details></span>}</td>
          <td><span>{copy.historyRun}：<code>{row.runId}</code></span> · <span>{copy.historySequence}：{row.sequence.toString()}</span> · <span>{copy.historyOrdinal}：{row.valueOrdinal.toString()}</span></td>
        </tr>;
      })}</tbody></table></div>
    {query!==null&&page!==null&&rows.length===0&&<p>{copy.historyEmpty}</p>}
    <div className="pagination"><button type="button" disabled={cursorStack.length===0||busy||inFlight!==null} onClick={goPrevious}>{copy.previousPage}</button>
    <button type="button" disabled={next===null||busy||inFlight!==null} onClick={goNext}>{copy.nextPage}</button></div>
  </section>;
}
