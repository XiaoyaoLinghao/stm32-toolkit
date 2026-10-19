import type {JSX} from "preact";
import {useState} from "preact/hooks";
import type {SourceCatalogItem} from "../api/contract";
import type {OperationFailure,RequestScope,SourceCatalogState} from "../state/model";
import {copy,formatCopy,sourceReasonText} from "../presentation/zh";

export type SourceCatalogPanelProps={source:SourceCatalogState;pending:boolean;childPending:boolean;selectionPending:boolean;editBusy:boolean;
 failures:Readonly<Partial<Record<"catalog.source"|"catalog.source-child"|"catalog.source-selection",OperationFailure|undefined>>>;
 onRetry:(scope:RequestScope,id:bigint)=>void;onFirmware:()=>void;
 onSearch:(query:string)=>void|Promise<void>;onNext:()=>void|Promise<void>;
 onChildren:(parentId:string,next?:boolean)=>void|Promise<void>;onSelect:(item:SourceCatalogItem)=>void|Promise<void>};

function SourceRow({item,source,editBusy,selectionPending,childPending,onChildren,onSelect,depth=0}:Pick<SourceCatalogPanelProps,"source"|"editBusy"|"selectionPending"|"childPending"|"onChildren"|"onSelect">&{item:SourceCatalogItem;depth?:number}):JSX.Element{
 const [open,setOpen]=useState(false),children=source.children[item.id];
 const toggle=()=>{const next=!open;setOpen(next);if(next&&children===undefined)void onChildren(item.id);};
 return<li className="source-item" data-depth={depth}>
   <div className="source-item-line">
     {item.expandable?<button type="button" className="source-expand" aria-expanded={open} aria-label={`${open?copy.sourceCollapse:copy.sourceExpand} ${item.name}`}
       onClick={toggle}>{open?"▾":"▸"}</button>:<span className="source-expand-placeholder" aria-hidden="true"/>}
     <span className="source-item-label"><code>{item.name}</code> <small>{item.typeName}</small>
       <small>{item.file}{item.line===null?"":`:${item.line}`}</small>
       {item.reason!==null&&<small className="source-reason">{sourceReasonText(item.reason)}</small>}
       {item.truncated&&<small className="source-reason">{copy.sourceTruncated}</small>}
       {source.lastAddedId===item.id&&<small role="status">{copy.sourceAdded}</small>}
     </span>
     <button type="button" aria-label={`${copy.addDraft} ${item.name}`} title={item.reason===null?copy.addDraft:sourceReasonText(item.reason)}
       disabled={!item.canAdd||editBusy||selectionPending} onClick={()=>void onSelect(item)}>+</button>
   </div>
   {open&&<div className="source-children">
     {children===undefined?<p role="status">{childPending?copy.sourceChildrenLoading:copy.sourceExpandPrompt}</p>:<>
       <ul>{children.items.map(child=><SourceRow key={child.id} item={child} source={source} editBusy={editBusy}
         selectionPending={selectionPending} childPending={childPending}
         onChildren={onChildren} onSelect={onSelect} depth={depth+1}/>)}</ul>
       <p>{copy.sourceCount(children.items.length,children.total)}</p>
       {children.nextCursor===null&&children.items.length<children.total&&<small className="source-reason">{copy.sourceTruncated}</small>}
       {children.nextCursor!==null&&<button type="button" onClick={()=>void onChildren(item.id,true)}>{copy.nextPage}</button>}
     </>}
   </div>}
 </li>;
}

type Group={file:string;functions:Map<string,SourceCatalogItem[]>};
function grouped(items:readonly SourceCatalogItem[]):Group[]{
 const byFile=new Map<string,Group>();
 for(const item of items){
   let file=byFile.get(item.file);if(file===undefined){file={file:item.file,functions:new Map()};byFile.set(item.file,file);}
   const scope=item.scope.function??copy.sourceGlobalScope;
   const rows=file.functions.get(scope)??[];rows.push(item);file.functions.set(scope,rows);
 }
 return [...byFile.values()].sort((a,b)=>a.file.localeCompare(b.file));
}

export function SourceCatalogPanel(p:SourceCatalogPanelProps):JSX.Element{
 const [query,setQuery]=useState("");
 const page=p.source.page,previous=page!==null&&p.source.query!==query.trim();
 return<section className="panel source-catalog-panel" aria-label={copy.sourceTitle}>
   <h2>{copy.sourceTitle}</h2>
   <label>{copy.search} <input value={query} placeholder={copy.sourceSearchPlaceholder} maxLength={128}
     onInput={event=>setQuery(event.currentTarget.value)} onKeyDown={event=>{if(event.key==="Enter")void p.onSearch(query.trim());}}/></label>
   <div className="source-actions"><button type="button" disabled={p.pending} onClick={()=>void p.onSearch(query.trim())}>{copy.search}</button>
     <button type="button" disabled={p.pending} onClick={()=>void p.onSearch(p.source.query)}>{copy.sourceRefresh}</button></div>
   {p.pending&&<p role="status">{copy.sourceLoading}</p>}
   {p.failures["catalog.source"]!==undefined&&<p role="alert">{copy.sourceIndexFailed} <code>{p.failures["catalog.source"].code}</code>
     <button type="button" onClick={()=>p.onRetry("catalog.source",p.failures["catalog.source"]!.requestId)}>{copy.retry}</button>
     <button type="button" onClick={p.onFirmware}>{copy.sourceUseFirmware}</button></p>}
   {page===null&&!p.pending&&p.failures["catalog.source"]===undefined&&<p>{copy.sourceEmptyPrompt}</p>}
   {page!==null&&<>
     {previous&&<p role="status">{copy.previousCatalog}</p>}
     <p role="status">{copy.sourceCount(page.items.length,page.total)} · {copy.sourceUnits(page.coverage.parsedUnits,page.coverage.totalUnits)}</p>
     {!page.coverage.complete&&<div className="source-coverage" role="status">
       <strong>{copy.sourcePartial}</strong>
       {page.coverage.truncated&&<span>{copy.sourceTruncated}</span>}
       {page.coverage.issues.slice(0,5).map((issue,index)=><small key={`${issue.code}-${index}`}>{issue.unit??copy.sourceUnknownUnit} · {issue.code}</small>)}
       <button type="button" disabled={p.pending} onClick={()=>void p.onSearch(p.source.query)}>{copy.retry}</button>
     </div>}
     <div className="source-tree" role="region" aria-label={copy.sourceResults} tabIndex={0}>
       {grouped(page.items).map(group=><details key={group.file} open={p.source.query!==""}>
         <summary>{group.file} · {formatCopy.catalogLoaded([...group.functions.values()].reduce((sum,items)=>sum+items.length,0))}</summary>
         {[...group.functions].map(([name,items])=><details key={name} open={p.source.query!==""}>
           <summary>{name} · {items.length}</summary>
           <ul>{items.map(item=><SourceRow key={item.id} item={item} source={p.source} editBusy={p.editBusy}
             selectionPending={p.selectionPending} childPending={p.childPending}
             onChildren={p.onChildren} onSelect={p.onSelect}/>)}</ul>
         </details>)}
       </details>)}
     </div>
     {page.nextCursor!==null&&<button type="button" disabled={p.pending} onClick={()=>void p.onNext()}>{copy.nextPage}</button>}
     {p.childPending&&<p role="status">{copy.sourceChildrenLoading}</p>}
     {p.failures["catalog.source-child"]!==undefined&&<p role="alert">{copy.sourceChildFailed} <code>{p.failures["catalog.source-child"].code}</code>
       <button type="button" onClick={()=>p.onRetry("catalog.source-child",p.failures["catalog.source-child"]!.requestId)}>{copy.retry}</button></p>}
     {p.selectionPending&&<p role="status">{copy.sourceChecking}</p>}
     {p.failures["catalog.source-selection"]!==undefined&&<p role="alert">{copy.sourceSelectionFailed} <code>{p.failures["catalog.source-selection"].code}</code>
       <button type="button" onClick={()=>p.onRetry("catalog.source-selection",p.failures["catalog.source-selection"]!.requestId)}>{copy.retry}</button></p>}
   </>}
 </section>;
}
