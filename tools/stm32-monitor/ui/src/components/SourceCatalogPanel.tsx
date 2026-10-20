import type {JSX} from "preact";
import {useState} from "preact/hooks";
import type {SourceCatalogItem,SourceFileNode,SourceScopeNode} from "../api/contract";
import type {OperationFailure,PendingRequest,RequestScope,SourceCatalogState} from "../state/model";
import {copy,sourceReasonText,sourceRoleText} from "../presentation/zh";

export type SourceCatalogPanelProps={source:SourceCatalogState;
 pending:Readonly<Partial<Record<RequestScope,PendingRequest>>>;
 failures:Readonly<Partial<Record<RequestScope,OperationFailure>>>;
 editBusy:boolean;onRetry:(scope:RequestScope,id:bigint)=>void;onFirmware:()=>void;
 onSearch:(query:string,refresh?:boolean)=>void|Promise<void>;
 onChildren:(parentId:string,next?:boolean)=>void|Promise<void>;
 onSelect:(item:SourceCatalogItem)=>void|Promise<void>};
const nodeScope=(id:string):RequestScope=>`catalog.source-node.${id}`;
type NodeProps=Pick<SourceCatalogPanelProps,"source"|"pending"|"failures"|"editBusy"|"onRetry"|"onChildren"|"onSelect">;

function NodeFeedback({id,pending,failures,onRetry}:Pick<NodeProps,"pending"|"failures"|"onRetry">&{id:string}):JSX.Element|null{
 const scope=nodeScope(id),failure=failures[scope];
 if(failure!==undefined)return<p role="alert">{copy.sourceChildFailed} <code>{failure.code}</code>
   <button type="button" onClick={()=>onRetry(scope,failure.requestId)}>{copy.retry}</button></p>;
 return pending[scope]!==undefined?<p role="status">{copy.sourceChildrenLoading}</p>:null;
}
function SourceRow({item,source,pending,failures,editBusy,onRetry,onChildren,onSelect,depth=0}:NodeProps&
 {item:SourceCatalogItem;depth?:number}):JSX.Element{
 const [open,setOpen]=useState(false),children=source.children[item.id],scope=nodeScope(item.id);
 const role=item.declaration?.kind??"unknown",definition=item.declaration?.definitionSite;
 const status=item.canAdd?copy.sourceSampleable:item.reason==="probe_required"?copy.sourceNeedsProbe:
   item.expandable?copy.sourceExpandMembers:copy.sourceBrowseOnly;
 const owner=[item.file+(item.line===null?"":`:${item.line}`),item.scope.function??copy.sourceGlobalScope,
   ...item.scope.path].join(" / ");
 return<li className="source-item" data-depth={depth}>
   <div className="source-item-line">
     {item.expandable?<button type="button" className="source-expand" aria-expanded={open}
       aria-label={`${open?copy.sourceCollapse:copy.sourceExpand} ${item.name}`}
       onClick={()=>{setOpen(!open);if(!open&&children===undefined)void onChildren(item.id);}}>{open?"▾":"▸"}</button>
       :<span className="source-expand-placeholder" aria-hidden="true"/>}
     <span className="source-item-label"><span className="source-item-heading"><code>{item.name}</code>
       <span className="source-role-badge">{sourceRoleText(role)}</span>
       <span className={`source-status-badge ${item.canAdd?"source-status-ready":""}`}>{status}</span></span>
       <small className="source-owner">{item.typeName} · {copy.sourceOwnership} {owner}
         {item.parentId!==null&&<> · {copy.sourceMemberPath} {[...item.scope.path,item.name].join(".")}</>}</small>
       {role==="extern_declaration"&&definition!==null&&definition!==undefined&&
         <small className="source-definition">{copy.sourceDefinition} {definition.file}:{definition.line}</small>}
       {item.reason!==null&&<small className="source-reason">{sourceReasonText(item.reason)}</small>}
       {item.truncated&&<small className="source-reason">{copy.sourceTruncated}</small>}
       {source.lastAddedId===item.id&&<small role="status">{copy.sourceAdded}</small>}
     </span>
     <button type="button" aria-label={`${copy.addDraft} ${item.name}`} title={item.reason===null?copy.addDraft:sourceReasonText(item.reason)}
       disabled={!item.canAdd||editBusy||pending["catalog.source-selection"]!==undefined} onClick={()=>void onSelect(item)}>+</button>
   </div>
   {open&&<div className="source-children">
     <NodeFeedback id={item.id} pending={pending} failures={failures} onRetry={onRetry}/>
     {children!==undefined&&<>
       <ul>{children.items.map(child=><SourceRow key={child.id} item={child} source={source} pending={pending}
         failures={failures} editBusy={editBusy} onRetry={onRetry} onChildren={onChildren} onSelect={onSelect} depth={depth+1}/>)}</ul>
       <p>{copy.sourceDeclarationCount(children.items.length,children.total)}</p>
       {children.nextCursor===null&&children.items.length<children.total&&<small className="source-reason">{copy.sourceTruncated}</small>}
       {children.nextCursor!==null&&<button type="button" disabled={pending[scope]!==undefined}
         onClick={()=>void onChildren(item.id,true)}>{copy.nextPage}</button>}
     </>}
   </div>}
 </li>;
}

type Folder={name:string;path:string;folders:Map<string,Folder>;files:SourceFileNode[]};
function fileFolders(files:readonly SourceFileNode[]):Folder{
 const root:Folder={name:"",path:"",folders:new Map(),files:[]};
 for(const file of files){const parts=file.file.split("/");let folder=root;
  for(const part of parts.slice(0,-1)){let child=folder.folders.get(part);
   if(child===undefined){child={name:part,path:folder.path?`${folder.path}/${part}`:part,folders:new Map(),files:[]};folder.folders.set(part,child);}folder=child;}
  folder.files.push(file);}
 return root;
}
const ordered=<T extends {name:string}>(items:Iterable<T>):T[]=>[...items].sort((a,b)=>a.name.localeCompare(b.name));
function TreeContent(p:NodeProps):JSX.Element{
 type Expansion={generation:bigint;closedFolders:ReadonlySet<string>;openFiles:ReadonlySet<string>;openScopes:ReadonlySet<string>};
 const [saved,setSaved]=useState<Expansion>({generation:p.source.generation,closedFolders:new Set(),openFiles:new Set(),openScopes:new Set()});
 const current:Expansion=saved.generation===p.source.generation?saved:{generation:p.source.generation,
  closedFolders:new Set(),openFiles:new Set(),openScopes:new Set()};
 const {closedFolders,openFiles,openScopes}=current;
 const tree=p.source.tree!,root=fileFolders(tree.items);
 const toggle=(field:"closedFolders"|"openFiles"|"openScopes",id:string)=>{
  const next=new Set(current[field]);if(next.has(id))next.delete(id);else next.add(id);
  setSaved({...current,[field]:next});};
 const scopeRow=(scope:SourceScopeNode):JSX.Element=>{
  const open=openScopes.has(scope.id),page=p.source.scopePages[scope.id],scopeKey=nodeScope(scope.id);
  return<li key={scope.id} className="source-scope">
    <button type="button" aria-expanded={open} aria-label={`${open?copy.sourceCollapse:copy.sourceExpand} ${scope.name}`}
      onClick={()=>{toggle("openScopes",scope.id);if(!open&&page===undefined)void p.onChildren(scope.id);}}>
      {open?"▾":"▸"} {scope.function??copy.sourceGlobalScope}{scope.line===null?"":`:${scope.line}`} · {scope.variableCount} {copy.sourceDeclaration}</button>
    {open&&<div className="source-children">
      <NodeFeedback id={scope.id} pending={p.pending} failures={p.failures} onRetry={p.onRetry}/>
      {page!==undefined&&<><ul>{page.items.map(item=><SourceRow key={item.id} item={item} {...p}/>)}</ul>
        <p className="source-page-count">{copy.sourceDeclarationCount(page.items.length,page.total)}</p>
        {page.items.length===0&&<p>{tree.coverage.complete?copy.sourceNoVariables:copy.sourceInfoUnavailable}</p>}
        {page.nextCursor!==null&&<button type="button" disabled={p.pending[scopeKey]!==undefined}
          onClick={()=>void p.onChildren(scope.id,true)}>{copy.nextPage}</button>}</>}
    </div>}
   </li>;
 };
 const fileRow=(file:SourceFileNode):JSX.Element=>{
  const open=openFiles.has(file.id),branch=p.source.branches[file.id];
  return<li key={file.id} className="source-file">
    <button type="button" aria-expanded={open} aria-label={`${open?copy.sourceCollapse:copy.sourceExpand} ${file.file}`}
      onClick={()=>{toggle("openFiles",file.id);if(!open&&branch===undefined)void p.onChildren(file.id);}}>
      {open?"▾":"▸"} <span className="source-file-path">{file.file}</span>
      <small>{file.scopeCount} {copy.sourceScopesLabel} · {file.variableCount} {copy.sourceDeclaration}</small></button>
    {open&&<div className="source-children">
      <NodeFeedback id={file.id} pending={p.pending} failures={p.failures} onRetry={p.onRetry}/>
      {branch!==undefined&&<><ul>{branch.items.map(scopeRow)}</ul>
        <p className="source-page-count">{copy.sourceScopeCount(branch.items.length,branch.total)}</p></>}
      {branch!==undefined&&branch.items.length===0&&<p>{tree.coverage.complete?copy.sourceNoScopes:copy.sourceInfoUnavailable}</p>}
    </div>}
   </li>;
 };
 const folderRows=(folder:Folder):JSX.Element[]=>[
  ...ordered(folder.folders.values()).map(child=>{const open=!closedFolders.has(child.path);
   return<li key={`folder:${child.path}`} className="source-folder">
     <button type="button" aria-expanded={open} aria-label={`${open?copy.sourceCollapse:copy.sourceExpand} ${child.path}`}
       onClick={()=>toggle("closedFolders",child.path)}>{open?"▾":"▸"} {child.name}/</button>
     {open&&<ul className="source-children">{folderRows(child)}</ul>}
    </li>;}),
  ...ordered(folder.files).map(fileRow),
 ];
 return<div className="source-tree" role="region" aria-label={copy.sourceResults} tabIndex={0}><ul>{folderRows(root)}</ul></div>;
}

export function SourceCatalogPanel(p:SourceCatalogPanelProps):JSX.Element{
 const [query,setQuery]=useState("");
 const tree=p.source.tree,previous=tree!==null&&p.source.query!==query.trim();
 const rootFailure=p.failures["catalog.source"],selectionFailure=p.failures["catalog.source-selection"];
 return<section className="panel source-catalog-panel" aria-label={copy.sourceTitle}>
   <h2>{copy.sourceTitle}</h2>
   <label>{copy.search} <input value={query} placeholder={copy.sourceSearchPlaceholder} maxLength={128}
     onInput={event=>setQuery(event.currentTarget.value)} onKeyDown={event=>{if(event.key==="Enter")void p.onSearch(query.trim());}}/></label>
   <div className="source-actions"><button type="button" disabled={p.pending["catalog.source"]!==undefined}
     onClick={()=>void p.onSearch(query.trim())}>{copy.search}</button>
     <button type="button" disabled={p.pending["catalog.source"]!==undefined}
       onClick={()=>void p.onSearch(p.source.query,true)}>{copy.sourceRefresh}</button></div>
   {p.pending["catalog.source"]!==undefined&&<p role="status">{copy.sourceLoading}</p>}
   {rootFailure!==undefined&&<p role="alert">{copy.sourceIndexFailed} <code>{rootFailure.code}</code>
     <button type="button" onClick={()=>p.onRetry("catalog.source",rootFailure.requestId)}>{copy.retry}</button>
     <button type="button" onClick={p.onFirmware}>{copy.sourceUseFirmware}</button></p>}
   {tree===null&&p.pending["catalog.source"]===undefined&&rootFailure===undefined&&<p>{copy.sourceEmptyPrompt}</p>}
   {tree!==null&&<>
     {previous&&<p role="status">{copy.previousCatalog}</p>}
     {tree.coverage.compiledDebug?.available&&<p role="status">{copy.sourceCompiled(tree.coverage.compiledDebug.variableCount,
       tree.coverage.compiledDebug.functionCount,tree.coverage.compiledDebug.fileCount)}</p>}
     <p role="status">{copy.sourceFileCount(tree.items.length,tree.total)} · {copy.sourceUnits(tree.coverage.parsedUnits,tree.coverage.totalUnits)}</p>
     {!tree.coverage.complete&&<div className="source-coverage" role="status">
       <strong>{copy.sourcePartial}</strong>
       {tree.coverage.truncated&&<span>{copy.sourceTruncated}</span>}
       {tree.coverage.issues.length>0&&<details><summary>{copy.sourceIssues}</summary>
         {tree.coverage.issues.map((issue,index)=><small key={`${issue.code}-${index}`}>
           {issue.code==="MONITOR_SOURCE_UNTRACKED_AST"&&issue.unit!==null?
             copy.sourceUntrackedHeader(issue.unit):
            issue.code==="MONITOR_SOURCE_OUTSIDE_SNAPSHOT_POLICY"&&issue.unit!==null?
             copy.sourceOutsideSnapshotPolicy(issue.unit):`${issue.unit??copy.sourceUnknownUnit} · ${issue.message}`}</small>)}
       </details>}
       <button type="button" disabled={p.pending["catalog.source"]!==undefined}
         onClick={()=>void p.onSearch(p.source.query,true)}>{copy.retry}</button>
     </div>}
     {!tree.coverage.complete&&tree.items.every(file=>file.scopeCount===0)&&
       (tree.coverage.compiledDebug?.variableCount??0)===0&&
       (tree.coverage.compiledDebug?.functionCount??0)===0&&
       <p role="status">{copy.sourceInfoUnavailable}</p>}
     <TreeContent key={p.source.generation.toString()} {...p}/>
     {p.pending["catalog.source-selection"]!==undefined&&<p role="status">{copy.sourceChecking}</p>}
     {selectionFailure!==undefined&&<p role="alert">{copy.sourceSelectionFailed} <code>{selectionFailure.code}</code>
       <button type="button" onClick={()=>p.onRetry("catalog.source-selection",selectionFailure.requestId)}>{copy.retry}</button></p>}
   </>}
 </section>;
}
