import type {JSX} from "preact";
import {useRef,useState} from "preact/hooks";
import type {ApiFailure,GroupDraft,GroupImportDocument,WatchGroup,WatchItem} from "../api/contract";
import {
  parseGroupImportDocument,
  previewGroupImport,
  toGroupImportDocument,
} from "../state/group-transfer";
import {parseLossless} from "../api/wire";

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
};

function watchKey(watch:WatchItem):string{
  return watch.kind==="variable"?`variable:${watch.expression}`:`register:${watch.registerPath}`;
}

export function GroupPanel(p:GroupPanelProps):JSX.Element{
  const [confirmDelete,setConfirmDelete]=useState<string|null>(null);
  const [importState,setImportState]=useState<"idle"|"preview">("idle");
  const [importDoc,setImportDoc]=useState<GroupImportDocument|null>(null);
  const [importError,setImportError]=useState<string|null>(null);
  const fileRef=useRef<HTMLInputElement>(null);
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
    const text=await new Promise<string>((resolve,reject)=>{
      const reader=new FileReader();
      reader.onload=()=>resolve(reader.result as string);
      reader.onerror=()=>reject(new Error("read failed"));
      reader.readAsText(file);
    });
    try{
      let value:unknown;
      try{value=parseLossless(text);}catch{setImportDoc(null);setImportError("Import file is not valid JSON");return;}
      const parsed=parseGroupImportDocument(value);
      if(!parsed.ok){setImportDoc(null);setImportError(parsed.message);return;}
      setImportDoc(parsed.data);setImportError(null);setImportState("preview");
    }catch{
      setImportDoc(null);setImportError("Import file could not be read");
    }finally{
      if(fileRef.current!==null)fileRef.current.value="";
    }
  };

  const confirmImport=(doc:GroupImportDocument):void=>{
    void p.onImport(doc);
    setImportDoc(null);setImportState("idle");
  };
  const cancelImport=():void=>{setImportDoc(null);setImportState("idle");setImportError(null);};

  return<section className="panel" aria-label="Watch groups">
    <h2>Watch groups</h2>
    <ul>{p.groups.map(group=>(
      <li key={group.groupId}>
        <button type="button" aria-pressed={group.groupId===p.selectedGroupId}
          onClick={()=>void p.onSelect(group.groupId)}>{group.name} ({group.items.length})</button>
        {group.groupId===p.selectedGroupId&&confirmDelete!==group.groupId&&(
          <button type="button" onClick={()=>setConfirmDelete(group.groupId)}>Delete</button>
        )}
        {confirmDelete===group.groupId&&(
          <>
            <span>Delete {group.name}?</span>
            <button type="button" onClick={()=>{void p.onDelete(group.groupId);setConfirmDelete(null);}}>Confirm delete</button>
            <button type="button" onClick={()=>setConfirmDelete(null)}>Cancel</button>
          </>
        )}
      </li>))}</ul>
    <button type="button" onClick={()=>void p.onNew()}>New group</button>
    <button type="button" onClick={exportBlob}>Export groups JSON</button>
    <button type="button" onClick={()=>setImportState(v=>v==="idle"?"preview":"idle")}>Import groups</button>
    {importState!=="idle"&&(
      <div>
        <input ref={fileRef} type="file" accept="application/json" data-testid="group-import-file"
          onChange={readImportFile}/>
        {importError!==null&&<p role="alert">{importError}</p>}
        {importDoc!==null&&(()=>{
          const preview=previewGroupImport(importDoc,p.groups);
          return(
            <div>
              <p>Import {preview.groupCount} groups ({preview.itemCount} watches)?</p>
              <button type="button" onClick={()=>confirmImport(importDoc)}>Confirm import</button>
              <button type="button" onClick={cancelImport}>Cancel</button>
            </div>
          );
        })()}
      </div>)}
    <h3>{isNew?"New group":"Edit group"}</h3>
    <label>Name <input value={p.draft.name}
      onInput={event=>void p.onDraftChange({...p.draft,name:event.currentTarget.value})}/></label>
    <label>Description <input value={p.draft.description}
      onInput={event=>void p.onDraftChange({...p.draft,description:event.currentTarget.value})}/></label>
    <label>Interval ms <input type="number" min="100" max="5000" step="100" value={String(p.draft.intervalMs)}
      onInput={event=>{const intervalMs=Number(event.currentTarget.value);if(Number.isFinite(intervalMs))void p.onDraftChange({...p.draft,intervalMs});}}/></label>
    <table><thead><tr><th>Watch</th><th>Actions</th></tr></thead>
      <tbody>{p.draft.items.map(item=>{
        const key=watchKey(item);
        return<tr key={key}><td><code>{item.kind==="variable"?item.expression:item.registerPath}</code></td>
          <td><button type="button" onClick={()=>void p.onRemove(key)}>Remove</button></td></tr>;})}</tbody></table>
    {p.failure!==null&&<p role="alert">{p.failure.code}: {p.failure.message}</p>}
    <button type="button" onClick={()=>void p.onSave()} disabled={p.draft.name===""||p.draft.items.length===0}>
      {isNew?"Create group":"Save group"}
    </button>
  </section>;
}
