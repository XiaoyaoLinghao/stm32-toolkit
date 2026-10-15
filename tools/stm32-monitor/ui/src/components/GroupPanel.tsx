import type {JSX} from "preact";
import {useEffect,useRef,useState} from "preact/hooks";
import type {ApiFailure,GroupDraft,GroupImportDocument,WatchGroup,WatchItem} from "../api/contract";
import {
  parseGroupImportDocument,
  previewGroupImport,
  toGroupImportDocument,
} from "../state/group-transfer";
import {parseLossless} from "../api/wire";
import {copy,errorText,formatCopy} from "../presentation/zh";
import {FailureMessage} from "./FailureMessage";

export type GroupPanelProps={
  groups:readonly WatchGroup[];
  selectedGroupId:string|null;
  draft:GroupDraft;
  failure:ApiFailure|null;
  onSelect:(groupId:string)=>void|Promise<void>;
  onDraftChange:(draft:GroupDraft)=>void|Promise<void>;
  onRemove:(key:string)=>void|Promise<void>;
  onNew:()=>void|Promise<void>;
  onSave:()=>void|Promise<void>;
  onDelete:(groupId:string)=>void|Promise<void>;
  onImport:(value:unknown)=>void|Promise<void>;
  onExport:()=>void|Promise<void>;
  compact?:boolean;
};

function watchKey(watch:WatchItem):string{
  return watch.kind==="variable"?`variable:${watch.expression}`:`register:${watch.registerPath}`;
}

type ImportState=
  |{kind:"closed"}
  |{kind:"selecting"}
  |{kind:"reading"}
  |{kind:"preview";generation:number;document:GroupImportDocument}
  |{kind:"error";message:string;diagnostic:string|null};

export function GroupPanel(p:GroupPanelProps):JSX.Element{
  const [confirmDelete,setConfirmDelete]=useState<string|null>(null);
  const [importState,setImportState]=useState<ImportState>({kind:"closed"});
  const [editorOpen,setEditorOpen]=useState(!p.compact);
  const fileRef=useRef<HTMLInputElement>(null);
  const importGeneration=useRef(0);
  const mounted=useRef(true);
  useEffect(()=>{
    mounted.current=true;
    return()=>{mounted.current=false;importGeneration.current+=1;};
  },[]);
  const isNew=p.draft.sourceGroupId===null;
  const exportDoc=toGroupImportDocument(p.groups);
  const exportBlob=()=>{
    const blob=new Blob([JSON.stringify(exportDoc,null,2)],{type:"application/json"});
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement("a");
    anchor.href=url;anchor.download="monitor-groups.json";anchor.click();
    URL.revokeObjectURL(url);
  };

  const readImportFile=async(event:Event):Promise<void>=>{
    const input=event.currentTarget as HTMLInputElement;
    const file=input.files?.[0];
    if(file===undefined)return;
    const generation=++importGeneration.current;
    const isCurrent=()=>mounted.current&&generation===importGeneration.current;
    input.value="";
    setImportState({kind:"reading"});
    try{
      const text=await new Promise<string>((resolve,reject)=>{
        const reader=new FileReader();
        reader.onload=()=>typeof reader.result==="string"?resolve(reader.result):reject(new Error("read failed"));
        reader.onerror=()=>reject(new Error("read failed"));
        reader.onabort=()=>reject(new Error("read aborted"));
        reader.readAsText(file);
      });
      if(!isCurrent())return;
      let value:unknown;
      try{value=parseLossless(text);}catch{setImportState({kind:"error",message:copy.importJsonInvalid,diagnostic:null});return;}
      const parsed=parseGroupImportDocument(value);
      if(!parsed.ok){setImportState({kind:"error",message:`${errorText(parsed.code).title}。${errorText(parsed.code).action}`,diagnostic:`${parsed.code}: ${parsed.message}`});return;}
      setImportState({kind:"preview",generation,document:parsed.data});
    }catch{
      if(isCurrent())setImportState({kind:"error",message:copy.importReadFailed,diagnostic:null});
    }
  };

  const cancelImport=():void=>{
    importGeneration.current+=1;
    setImportState({kind:"closed"});
    if(fileRef.current!==null)fileRef.current.value="";
  };
  const confirmImport=():void=>{
    if(importState.kind!=="preview"||!mounted.current||importState.generation!==importGeneration.current)return;
    const doc=importState.document;
    cancelImport();
    void p.onImport(doc);
  };

  return<section className="panel group-panel" aria-label={copy.groupTitle}>
    <h2>{copy.groupTitle}</h2>
    <ul>{p.groups.map(group=>(
      <li key={group.groupId}>
        <button type="button" aria-pressed={group.groupId===p.selectedGroupId}
          onClick={()=>void p.onSelect(group.groupId)}>{group.name} ({group.items.length})</button>
        {group.groupId===p.selectedGroupId&&confirmDelete!==group.groupId&&(
          <button type="button" onClick={()=>setConfirmDelete(group.groupId)}>{copy.groupDelete}</button>
        )}
        {confirmDelete===group.groupId&&(
          <>
            <span>{formatCopy.groupDelete(group.name)}</span>
            <button type="button" onClick={()=>{void p.onDelete(group.groupId);setConfirmDelete(null);}}>{copy.groupConfirmDelete}</button>
            <button type="button" onClick={()=>setConfirmDelete(null)}>{copy.cancel}</button>
          </>
        )}
      </li>))}</ul>
    {p.groups.length===0&&<p>{copy.groupNone}</p>}
    <div className="group-actions">
      <button type="button" onClick={()=>{setEditorOpen(true);void p.onNew();}}>{copy.groupNew}</button>
      <button type="button" onClick={()=>setEditorOpen(value=>!value)} aria-expanded={editorOpen}>{editorOpen?copy.groupCollapse:copy.groupEdit}</button>
      <button type="button" onClick={exportBlob}>{copy.groupExport}</button>
      <button type="button" onClick={()=>importState.kind==="closed"?setImportState({kind:"selecting"}):cancelImport()}>{copy.groupImport}</button>
    </div>
    {importState.kind!=="closed"&&(
      <div>
        <label>{copy.groupFile} <input ref={fileRef} type="file" accept="application/json" data-testid="group-import-file"
          onChange={readImportFile}/></label>
        {importState.kind==="reading"&&<p role="status">{copy.importReading}</p>}
        {importState.kind==="error"&&<div role="alert">{importState.message}{importState.diagnostic!==null&&<details><summary>{copy.diagnostics}</summary><code>{importState.diagnostic}</code></details>}</div>}
        {importState.kind==="preview"&&(()=>{
          const preview=previewGroupImport(importState.document,p.groups);
          return(
            <div>
              <p>{formatCopy.importPreview(preview.groupCount,preview.itemCount)}</p>
              <button type="button" onClick={confirmImport}>{copy.groupConfirmImport}</button>
            </div>
          );
        })()}
        <button type="button" onClick={cancelImport}>{copy.cancel}</button>
      </div>)}
    <div className="group-editor" hidden={!editorOpen}>
    <h3>{isNew?copy.groupNewDraft:copy.groupEditDraft}</h3>
    <p className="hint">{copy.groupDraftHint}</p>
    <label>{copy.name} <input value={p.draft.name}
      onInput={event=>void p.onDraftChange({...p.draft,name:event.currentTarget.value})}/></label>
    <label>{copy.description} <input value={p.draft.description}
      onInput={event=>void p.onDraftChange({...p.draft,description:event.currentTarget.value})}/></label>
    <label>{copy.interval} <input type="number" min="100" max="5000" step="100" value={String(p.draft.intervalMs)}
      onInput={event=>{const intervalMs=Number(event.currentTarget.value);if(Number.isFinite(intervalMs))void p.onDraftChange({...p.draft,intervalMs});}}/></label>
    <table><thead><tr><th>{copy.watch}</th><th>{copy.action}</th></tr></thead>
      <tbody>{p.draft.items.map(item=>{
        const key=watchKey(item);
        return<tr key={key}><td><code>{item.kind==="variable"?item.expression:item.registerPath}</code></td>
          <td><button type="button" onClick={()=>void p.onRemove(key)}>{copy.remove}</button></td></tr>;})}</tbody></table>
    {p.failure!==null&&<FailureMessage failure={p.failure}/>}
    <button type="button" onClick={()=>void p.onSave()} disabled={p.draft.name===""||p.draft.items.length===0}>
      {isNew?copy.groupCreate:copy.groupSave}
    </button>
    </div>
  </section>;
}
