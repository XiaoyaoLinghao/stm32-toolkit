import type {JSX} from "preact";
import {useEffect,useState} from "preact/hooks";
import type {ApiFailure,ExportArtifact} from "../api/contract";
import {historyInput,inputNs} from "./HistoryPanel";
import {useDialogFocus} from "./dialog-focus";
import {copy,formatCopy} from "../presentation/zh";
import {FailureMessage} from "./FailureMessage";

export type ExportRequest={startNs:bigint;endNs:bigint;format:"csv"|"jsonl";authorized:true};
export type ExportPanelProps={
  range:{startNs:bigint;endNs:bigint}|null;
  artifact:ExportArtifact|null;
  failure:ApiFailure|null;
  onCreate:(request:ExportRequest)=>void|Promise<void>;
  onRefresh:(exportId:string)=>void|Promise<void>;
  onDownload:(exportId:string)=>void|Promise<void>;
};

export function ExportPanel(p:ExportPanelProps):JSX.Element{
  const [pending,setPending]=useState<"csv"|"jsonl"|null>(null);
  const rangeStart=p.range===null?"":historyInput(p.range.startNs);
  const rangeEnd=p.range===null?"":historyInput(p.range.endNs);
  const rangeKey=p.range===null?"":`${p.range.startNs}:${p.range.endNs}`;
  const [draft,setDraft]=useState(()=>({start:rangeStart,end:rangeEnd,syncedStart:rangeStart,syncedEnd:rangeEnd,retained:false}));
  const [validation,setValidation]=useState(false);
  const [pendingSubmission,setPendingSubmission]=useState<{priorId:string|null;range:{startNs:bigint;endNs:bigint}}|null>(null);
  const [artifactRanges,setArtifactRanges]=useState<Record<string,{startNs:bigint;endNs:bigint}>>({});
  useEffect(()=>{
    setDraft(current=>current.start===current.syncedStart&&current.end===current.syncedEnd
      ?{start:rangeStart,end:rangeEnd,syncedStart:rangeStart,syncedEnd:rangeEnd,retained:false}
      :{...current,syncedStart:rangeStart,syncedEnd:rangeEnd,retained:p.range!==null});
  },[rangeKey]);
  useEffect(()=>{
    if(pendingSubmission!==null&&p.artifact!==null&&p.artifact.exportId!==pendingSubmission.priorId){
      const id=p.artifact.exportId,range=pendingSubmission.range;
      setArtifactRanges(current=>({...current,[id]:range}));
      setPendingSubmission(null);
    }
  },[p.artifact?.exportId,pendingSubmission]);
  useEffect(()=>{if(p.failure!==null)setPendingSubmission(null);},[p.failure]);
  const dialog=useDialogFocus(pending!==null,()=>setPending(null));
  const confirm=():void=>{
    if(pending===null||pendingSubmission!==null)return;
    const startNs=inputNs(draft.start),endNs=inputNs(draft.end);
    if(startNs===null||endNs===null||endNs<=startNs){setValidation(true);return;}
    setValidation(false);
    const format=pending;setPending(null);
    setPendingSubmission({priorId:p.artifact?.exportId??null,range:{startNs,endNs}});
    void p.onCreate({startNs,endNs,format,authorized:true});
  };
  return<section className="panel export-panel" aria-label={copy.exportRegion}>
    <h2>{copy.exportTitle}</h2>
    <p className="hint">{copy.exportHint}</p>
    <div className="form-row"><label>{copy.exportStart} <input type="datetime-local" step="0.001" value={draft.start}
      onInput={event=>{const value=event.currentTarget.value;setDraft(current=>({...current,start:value}));}}/></label>
    <label>{copy.exportEnd} <input type="datetime-local" step="0.001" value={draft.end}
      onInput={event=>{const value=event.currentTarget.value;setDraft(current=>({...current,end:value}));}}/></label></div>
    {draft.retained&&<p role="status">{copy.exportRetained}</p>}
    {p.range!==null&&<button type="button" onClick={()=>setDraft({start:rangeStart,end:rangeEnd,syncedStart:rangeStart,syncedEnd:rangeEnd,retained:false})}>{copy.exportUseQuery}</button>}
    <div className="form-row"><button type="button" disabled={pendingSubmission!==null} onClick={event=>{dialog.rememberTrigger(event.currentTarget);setPending("csv");}}>{copy.exportCsv}</button>
    <button type="button" disabled={pendingSubmission!==null} onClick={event=>{dialog.rememberTrigger(event.currentTarget);setPending("jsonl");}}>{copy.exportJsonl}</button></div>
    {validation&&<p role="alert">{copy.invalidRange}</p>}
    {pending!==null&&(
      <div role="dialog" aria-modal="true" aria-label={copy.exportConfirmTitle} tabIndex={-1} ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
        <div><p>{formatCopy.exportQuestion(pending.toUpperCase())}</p>
        <button type="button" onClick={confirm}>{copy.exportConfirm}</button>
        <button type="button" onClick={()=>setPending(null)}>{copy.cancel}</button></div>
      </div>)}
    {p.artifact!==null&&(
      <>
        <p>{formatCopy.artifactSummary(p.artifact.bytes,p.artifact.valueCount)}</p>
        {artifactRanges[p.artifact.exportId]!==undefined&&<p>{formatCopy.submittedRange(historyInput(artifactRanges[p.artifact.exportId]!.startNs),historyInput(artifactRanges[p.artifact.exportId]!.endNs))}</p>}
        <details><summary>{copy.diagnostics}</summary><code>SHA-256：{p.artifact.sha256}</code></details>
        <button type="button" onClick={()=>void p.onRefresh(p.artifact!.exportId)}>{copy.exportRefresh}</button>
        <button type="button" onClick={()=>void p.onDownload(p.artifact!.exportId)}>{copy.exportDownload}{p.artifact.format.toUpperCase()}</button>
      </>)}
    {p.failure!==null&&<FailureMessage failure={p.failure}/>}
  </section>;
}
