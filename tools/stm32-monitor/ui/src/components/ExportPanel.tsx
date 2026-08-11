import type {JSX} from "preact";
import {useState} from "preact/hooks";
import type {ApiFailure,ExportArtifact} from "../api/contract";
import {historyInput,inputNs} from "./HistoryPanel";
import {useDialogFocus} from "./dialog-focus";

export type ExportRequest={startNs:bigint;endNs:bigint;format:"csv"|"jsonl";authorized:true};
export type ExportPanelProps={
  range:{startNs:bigint;endNs:bigint};
  artifact:ExportArtifact|null;
  failure:ApiFailure|null;
  onCreate:(request:ExportRequest)=>void|Promise<void>;
  onRefresh:(exportId:string)=>void|Promise<void>;
  onDownload:(exportId:string)=>void|Promise<void>;
};

export function ExportPanel(p:ExportPanelProps):JSX.Element{
  const [pending,setPending]=useState<"csv"|"jsonl"|null>(null);
  const [start,setStart]=useState(()=>historyInput(p.range.startNs));
  const [end,setEnd]=useState(()=>historyInput(p.range.endNs));
  const dialog=useDialogFocus(pending!==null,()=>setPending(null));
  const confirm=():void=>{
    if(pending===null)return;
    const startNs=inputNs(start),endNs=inputNs(end);
    if(startNs===null||endNs===null||endNs<=startNs)return;
    const format=pending;setPending(null);
    void p.onCreate({startNs,endNs,format,authorized:true});
  };
  return<section className="panel" aria-label="Export">
    <h2>Export</h2>
    <label>Export start <input type="datetime-local" step="0.001" value={start}
      onInput={event=>setStart(event.currentTarget.value)}/></label>
    <label>Export end <input type="datetime-local" step="0.001" value={end}
      onInput={event=>setEnd(event.currentTarget.value)}/></label>
    <button type="button" onClick={event=>{dialog.rememberTrigger(event.currentTarget);setPending("csv");}}>Create CSV export</button>
    <button type="button" onClick={event=>{dialog.rememberTrigger(event.currentTarget);setPending("jsonl");}}>Create JSONL export</button>
    {pending!==null&&(
      <div role="dialog" aria-label="Confirm history export" tabIndex={-1} ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
        <p>Export the selected current-session time range as {pending.toUpperCase()}?</p>
        <button type="button" onClick={confirm}>Confirm export</button>
        <button type="button" onClick={()=>setPending(null)}>Cancel</button>
      </div>)}
    {p.artifact!==null&&(
      <>
        <p>{p.artifact.bytes.toString()} bytes · {p.artifact.valueCount.toString()} values</p>
        <output>{p.artifact.sha256}</output>
        <button type="button" onClick={()=>void p.onRefresh(p.artifact!.exportId)}>Refresh export status</button>
        <button type="button" onClick={()=>void p.onDownload(p.artifact!.exportId)}>Download verified {p.artifact.format.toUpperCase()}</button>
      </>)}
    {p.failure!==null&&<p role="alert">{p.failure.code}: {p.failure.message}</p>}
  </section>;
}
