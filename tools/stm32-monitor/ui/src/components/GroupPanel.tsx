import type {JSX} from "preact";
import {useCallback,useEffect,useRef,useState} from "preact/hooks";
import type {ApiFailure,GroupDraft,GroupImportDocument,WatchGroup,WatchItem} from "../api/contract";
import {
  parseGroupImportDocument,
  previewGroupImport,
  toGroupImportDocument,
} from "../state/group-transfer";
import {parseLossless} from "../api/wire";
import type {GroupNavigation} from "../state/model";
import {copy,errorText,formatCopy} from "../presentation/zh";
import {FailureMessage} from "./FailureMessage";
import {useDialogFocus} from "./dialog-focus";

export type GroupPanelProps={
  groups:readonly WatchGroup[];
  selectedGroupId:string|null;
  draft:GroupDraft;
  dirty?:boolean;
  navigation?:GroupNavigation|null;
  navigationMissing?:boolean;
  sourceProblem?:"missing"|"changed"|null;
  nameReviewRequired?:boolean;
  editorGeneration?:bigint;
  failure:ApiFailure|null;
  busy?:boolean;
  onSelect:(groupId:string)=>void|Promise<void>;
  onDraftChange:(draft:GroupDraft)=>void|Promise<void>;
  onRemove:(key:string)=>void|Promise<void>;
  onNew:()=>void|Promise<void>;
  onSave:()=>void|Promise<void>;
  onDelete:(groupId:string,expectedRevision?:bigint,editorGeneration?:bigint)=>void|Promise<void>;
  onNavigateConfirm?:()=>void;
  onNavigateCancel?:()=>void;
  onSaveAsNew?:()=>void;
  onNameReviewed?:()=>void;
  onReload?:()=>void;
  onRefresh?:()=>void|Promise<void>;
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
  const [confirmDelete,setConfirmDelete]=useState<{groupId:string;revision:bigint;generation:bigint}|null>(null);
  const deleteConfirmation=useRef<{groupId:string;revision:bigint;generation:bigint}|null>(null);
  const [importState,setImportState]=useState<ImportState>({kind:"closed"});
  const [editorOpen,setEditorOpen]=useState(!p.compact);
  const fileRef=useRef<HTMLInputElement>(null);
  const importGeneration=useRef(0);
  const mounted=useRef(true);
  const navigation=p.navigation??null;
  const navigationDialog=useDialogFocus(navigation!==null,()=>p.onNavigateCancel?.());
  const locked=Boolean(p.busy||navigation!==null);
  const clearDelete=useCallback(()=>{deleteConfirmation.current=null;setConfirmDelete(null);},[]);
  useEffect(()=>{
    mounted.current=true;
    return()=>{mounted.current=false;importGeneration.current+=1;};
  },[]);
  useEffect(()=>{
    if(confirmDelete===null)return;
    const current=p.groups.find(group=>group.groupId===confirmDelete.groupId);
    if(current?.revision!==confirmDelete.revision||(p.editorGeneration??0n)!==confirmDelete.generation)
      clearDelete();
  },[confirmDelete,p.groups,p.editorGeneration,clearDelete]);
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
    if(locked)return;
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
    if(locked||importState.kind!=="preview"||!mounted.current||importState.generation!==importGeneration.current)return;
    const doc=importState.document;
    cancelImport();
    void p.onImport(doc);
  };

  return<section className="panel group-panel" aria-label={copy.groupTitle}>
    <h2>{copy.groupTitle}</h2>
    <ul>{p.groups.map(group=>(
      <li key={group.groupId}>
        <button type="button" aria-pressed={group.groupId===p.selectedGroupId}
          disabled={locked} onClick={event=>{clearDelete();navigationDialog.rememberTrigger(event.currentTarget);void p.onSelect(group.groupId);}}>{group.name} ({group.items.length})</button>
        {group.groupId===p.selectedGroupId&&confirmDelete?.groupId!==group.groupId&&(
          <button type="button" disabled={locked} onClick={()=>{
            const captured={groupId:group.groupId,revision:group.revision,generation:p.editorGeneration??0n};
            deleteConfirmation.current=captured;setConfirmDelete(captured);
          }}>{copy.groupDelete}</button>
        )}
        {confirmDelete?.groupId===group.groupId&&(
          <>
            <span>{formatCopy.groupDelete(group.name)}</span>
            <button type="button" disabled={locked||group.revision!==confirmDelete.revision||(p.editorGeneration??0n)!==confirmDelete.generation}
              onClick={()=>{
                const captured=confirmDelete;
                const valid=captured!==null&&deleteConfirmation.current===captured;
                clearDelete();
                if(valid&&captured!==null&&group.revision===captured.revision&&(p.editorGeneration??0n)===captured.generation)
                  void p.onDelete(group.groupId,captured.revision,captured.generation);
              }}>{copy.groupConfirmDelete}</button>
            <button type="button" disabled={locked} onClick={clearDelete}>{copy.cancel}</button>
          </>
        )}
      </li>))}</ul>
    {p.groups.length===0&&<p>{copy.groupNone}</p>}
    {p.navigationMissing&&<p role="alert">{copy.groupNavigationMissing}</p>}
    <div className="group-actions">
      <button type="button" disabled={locked} onClick={event=>{clearDelete();navigationDialog.rememberTrigger(event.currentTarget);setEditorOpen(true);void p.onNew();}}>{copy.groupNew}</button>
      <button type="button" onClick={()=>setEditorOpen(value=>!value)} aria-expanded={editorOpen}>{editorOpen?copy.groupCollapse:copy.groupEdit}</button>
      <button type="button" onClick={exportBlob}>{copy.groupExport}</button>
      <button type="button" disabled={locked} onClick={()=>importState.kind==="closed"?setImportState({kind:"selecting"}):cancelImport()}>{copy.groupImport}</button>
      {p.onRefresh&&<button type="button" disabled={locked} onClick={()=>{clearDelete();void p.onRefresh?.();}}>{copy.groupRefresh}</button>}
    </div>
    {navigation!==null&&<div role="dialog" aria-modal="true" aria-label={copy.groupUnsavedTitle}
      tabIndex={-1} ref={navigationDialog.dialogRef} onKeyDown={navigationDialog.onDialogKeyDown}>
      <div><p>{copy.groupUnsavedQuestion}</p>
        <button type="button" disabled={p.busy} onClick={()=>p.onNavigateCancel?.()}>{copy.groupKeepEditing}</button>
        <button type="button" disabled={p.busy} onClick={()=>p.onNavigateConfirm?.()}>{copy.groupDiscardContinue}</button>
      </div>
    </div>}
    {importState.kind!=="closed"&&(
      <div>
        <label>{copy.groupFile} <input ref={fileRef} type="file" accept="application/json" data-testid="group-import-file"
          disabled={locked} onChange={readImportFile}/></label>
        {importState.kind==="reading"&&<p role="status">{copy.importReading}</p>}
        {importState.kind==="error"&&<div role="alert">{importState.message}{importState.diagnostic!==null&&<details><summary>{copy.diagnostics}</summary><code>{importState.diagnostic}</code></details>}</div>}
        {importState.kind==="preview"&&(()=>{
          const preview=previewGroupImport(importState.document,p.groups);
          return(
            <div>
              <p>{formatCopy.importPreview(preview.groupCount,preview.itemCount)}</p>
              <ul>{importState.document.groups.map((group,index)=><li key={`${index}-${group.name}`}>{group.name} · {group.items.length} {copy.groupImportItems}</li>)}</ul>
              <p>{copy.groupImportNoOverwrite}</p>
              <button type="button" disabled={locked} onClick={confirmImport}>{copy.groupConfirmImport}</button>
            </div>
          );
        })()}
        <button type="button" disabled={locked} onClick={cancelImport}>{copy.cancel}</button>
      </div>)}
    <div className="group-editor" hidden={!editorOpen}>
    <h3>{isNew?copy.groupNewDraft:copy.groupEditDraft}</h3>
    <p className="hint">{isNew?copy.groupUnsaved:copy.groupDraftHint}{p.dirty?` · ${copy.groupDirty}`:""}</p>
    {p.sourceProblem!==null&&p.sourceProblem!==undefined&&<div role="alert">
      <p>{p.sourceProblem==="missing"?copy.groupSourceDeleted:copy.groupSourceChanged}</p>
      {p.sourceProblem==="changed"&&p.onReload&&<button type="button" disabled={locked} onClick={()=>{clearDelete();p.onReload?.();}}>{copy.groupReloadLatest}</button>}
      {p.onSaveAsNew&&<button type="button" disabled={locked} onClick={()=>{clearDelete();p.onSaveAsNew?.();}}>{copy.groupSaveAsNew}</button>}
    </div>}
    {p.nameReviewRequired&&<div role="status"><p>{copy.groupReviewName}</p>
      <button type="button" disabled={locked||p.draft.name===""} onClick={()=>p.onNameReviewed?.()}>{copy.groupConfirmName}</button>
    </div>}
    <label>{copy.name} <input value={p.draft.name} disabled={locked}
      onInput={event=>void p.onDraftChange({...p.draft,name:event.currentTarget.value})}/></label>
    <label>{copy.description} <input value={p.draft.description} disabled={locked}
      onInput={event=>void p.onDraftChange({...p.draft,description:event.currentTarget.value})}/></label>
    <label>{copy.interval} <input type="number" min="100" max="5000" step="100" value={String(p.draft.intervalMs)} disabled={locked}
      onInput={event=>{const intervalMs=Number(event.currentTarget.value);if(Number.isFinite(intervalMs))void p.onDraftChange({...p.draft,intervalMs});}}/></label>
    <table><thead><tr><th>{copy.watch}</th><th>{copy.action}</th></tr></thead>
      <tbody>{p.draft.items.map(item=>{
        const key=watchKey(item);
        return<tr key={key}><td><code>{item.kind==="variable"?item.expression:item.registerPath}</code></td>
          <td><button type="button" disabled={locked} onClick={()=>void p.onRemove(key)}>{copy.remove}</button></td></tr>;})}</tbody></table>
    {p.failure!==null&&<FailureMessage failure={p.failure}/>}
    <button type="button" onClick={()=>void p.onSave()} disabled={p.draft.name===""||p.draft.items.length===0||locked||p.nameReviewRequired||p.sourceProblem!==null&&p.sourceProblem!==undefined}>
      {isNew?copy.groupCreate:copy.groupSave}
    </button>
    </div>
  </section>;
}
