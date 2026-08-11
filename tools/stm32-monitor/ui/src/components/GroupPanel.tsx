import type {JSX} from "preact";
import {useRef,useState} from "preact/hooks";
import type {ApiFailure,GroupDraft,WatchGroup,WatchItem} from "../api/contract";
import {toGroupImportDocument} from "../state/group-transfer";

export type GroupPanelProps={
  groups:readonly WatchGroup[];
  selectedGroupId:string|null;
  draft:GroupDraft;
  failure:ApiFailure|null;
  onSelect:(groupId:string)=>void|Promise<void>;
  onDraftChange:(draft:GroupDraft)=>void|Promise<void>;
  onRemove:(key:string)=>void|Promise<void>;
  onCreate:()=>void|Promise<void>;
  onSave:()=>void|Promise<void>;
  onDelete:(groupId:string)=>void|Promise<void>;
  onReadImport:()=>Promise<{ok:true;data:unknown}|{ok:false;code:string;message:string}>;
  onImport:(value:unknown)=>void|Promise<void>;
  onExport:()=>void|Promise<void>;
  onRefresh:()=>void|Promise<void>;
};

function watchKey(watch:WatchItem):string{
  return watch.kind==="variable"?`variable:${watch.expression}`:`register:${watch.registerPath}`;
}

export function GroupPanel(p:GroupPanelProps):JSX.Element{
  const [showImport,setShowImport]=useState(false);
  const fileRef=useRef<HTMLInputElement>(null);
  const isNew=p.draft.sourceGroupId===null;
  const exportDoc=toGroupImportDocument(p.groups);
  const exportBlob=()=>{const blob=new Blob([JSON.stringify(exportDoc,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=url;anchor.download="monitor-groups.json";anchor.click();URL.revokeObjectURL(url);};

  return<section className="panel" aria-label="Watch groups">
    <h2>Watch groups</h2>
    <ul>{p.groups.map(group=>(
      <li key={group.groupId}>
        <button type="button" aria-pressed={group.groupId===p.selectedGroupId}
          onClick={()=>void p.onSelect(group.groupId)}>{group.name} ({group.items.length})</button>
        {group.groupId===p.selectedGroupId&&<button type="button" onClick={()=>void p.onDelete(group.groupId)}>Delete</button>}
      </li>))}</ul>
    <button type="button" onClick={()=>void p.onCreate()}>New group</button>
    <button type="button" onClick={exportBlob}>Export groups JSON</button>
    <button type="button" onClick={()=>setShowImport(v=>!v)}>Import groups</button>
    {showImport&&(
      <div>
        <input ref={fileRef} type="file" accept="application/json" data-testid="group-import-file"
          onChange={async event=>{
            const file=event.currentTarget.files?.[0];
            if(file===undefined)return;
            const read=await p.onReadImport();
            void p.onImport(read.ok?read.data:null);
            if(fileRef.current!==null)fileRef.current.value="";
          }}/>
      </div>)}
    <h3>{isNew?"New group":"Edit group"}</h3>
    <label>Name <input value={p.draft.name}
      onInput={event=>void p.onDraftChange({...p.draft,name:event.currentTarget.value})}/></label>
    <label>Description <input value={p.draft.description}
      onInput={event=>void p.onDraftChange({...p.draft,description:event.currentTarget.value})}/></label>
    <label>Interval ms <input type="number" min="100" max="5000" step="100" value={String(p.draft.intervalMs)}
      onInput={event=>{const intervalMs=Number(event.currentTarget.value);if(Number.isFinite(intervalMs))void p.onDraftChange({...p.draft,intervalMs});}}/></label>
    <table><thead><tr><th>Watch</th><th></th></tr></thead>
      <tbody>{p.draft.items.map(item=>{
        const key=watchKey(item);
        return<tr key={key}><td><code>{item.kind==="variable"?item.expression:item.registerPath}</code></td>
          <td><button type="button" onClick={()=>void p.onRemove(key)}>Remove</button></td></tr>;})}</tbody></table>
    {p.failure!==null&&<p role="alert">{p.failure.code}: {p.failure.message}</p>}
    <button type="button" onClick={()=>void p.onSave()} disabled={isNew||p.draft.name===""||p.draft.items.length===0}>
      {isNew?"Create group":"Save group"}
    </button>
  </section>;
}
