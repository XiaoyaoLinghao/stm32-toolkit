import type {JSX} from "preact";
import {useRef,useState} from "preact/hooks";
import type {CatalogGroup,RegisterCatalogItem,VariableCatalogItem,WatchItem} from "../api/contract";
import type {VariableCatalog,RegisterCatalog,CatalogKind} from "../state/model";
import {copy,formatCopy} from "../presentation/zh";

export type CatalogPanelProps={
  connected:boolean;
  bindingEpoch:bigint;
  bindingKey?:string;
  editBusy?:boolean;
  variables:VariableCatalog|null;
  registers:RegisterCatalog|null;
  pending?:boolean;
  onSearch:(kind:CatalogKind,query:string)=>void|Promise<void>;
  onNext:(kind:CatalogKind)=>void|Promise<void>;
  onAdd:(watch:WatchItem)=>void|Promise<void>;
};

type CatalogItem=VariableCatalogItem|RegisterCatalogItem;
type OpenChoices={key:string;overrides:ReadonlyMap<string,boolean>};

function groups(items:readonly CatalogItem[]):{group:CatalogGroup;items:CatalogItem[]}[]{
  const result:{group:CatalogGroup;items:CatalogItem[]}[]=[],byId=new Map<string,number>();
  for(const item of items){
    let index=byId.get(item.group.id);
    if(index===undefined){index=result.length;byId.set(item.group.id,index);result.push({group:item.group,items:[]});}
    result[index]!.items.push(item);
  }
  return result;
}

function addWatch(item:CatalogItem,onAdd:(watch:WatchItem)=>void|Promise<void>):void{
  if("typeName" in item)void onAdd({kind:"variable",expression:item.selector});
  else if(item.sampleable)void onAdd({kind:"register",registerPath:item.selector});
}

export function CatalogPanel(p:CatalogPanelProps):JSX.Element{
  const [kind,setKind]=useState<CatalogKind>("variables");
  const [query,setQuery]=useState("");
  const variableOpen=useRef<OpenChoices>({key:"",overrides:new Map()});
  const registerOpen=useRef<OpenChoices>({key:"",overrides:new Map()});
  const bindingIdentity=p.bindingKey??String(p.bindingEpoch);
  const matchesBinding=(catalog:VariableCatalog|RegisterCatalog|null)=>catalog!==null&&(
    p.bindingKey===undefined?catalog.bindingKey.endsWith("/"+String(p.bindingEpoch)):catalog.bindingKey===p.bindingKey);
  const variableKey=JSON.stringify([bindingIdentity,"variables",matchesBinding(p.variables)?p.variables!.query:null]);
  const registerKey=JSON.stringify([bindingIdentity,"registers",matchesBinding(p.registers)?p.registers!.query:null]);
  if(variableOpen.current.key!==variableKey)variableOpen.current={key:variableKey,overrides:new Map()};
  if(registerOpen.current.key!==registerKey)registerOpen.current={key:registerKey,overrides:new Map()};
  const current=kind==="variables"?p.variables:p.registers;
  const resultIdentityMatches=matchesBinding(current);
  const isPrevious=resultIdentityMatches&&current!==null&&current.query!==query.trim();
  const visibleGroups=resultIdentityMatches&&current!==null?groups(current.items):[];
  const openChoices=kind==="variables"?variableOpen:registerOpen;
  const overrides=openChoices.current.overrides;
  const setGroupOpen=(id:string,open:boolean)=>{
    const previous=openChoices.current;
    const updated=new Map(previous.overrides);
    updated.set(id,open);
    openChoices.current={...previous,overrides:updated};
  };
  const labelCounts=new Map<string,number>();
  for(const entry of visibleGroups)labelCounts.set(entry.group.label,(labelCounts.get(entry.group.label)??0)+1);
  const labelOrdinals=new Map<string,number>();

  return<section className="panel catalog-panel" aria-label={copy.catalogTitle}>
    <h2>{copy.catalogTitle}</h2>
    <div role="tablist" aria-label={copy.catalogKind}>
      <button type="button" role="tab" aria-selected={kind==="variables"} onClick={()=>setKind("variables")}>{copy.variables}</button>
      <button type="button" role="tab" aria-selected={kind==="registers"} onClick={()=>setKind("registers")}>{copy.registers}</button>
    </div>
    <label>{copy.search} <input value={query} placeholder={copy.searchPlaceholder} disabled={!p.connected}
      onInput={event=>setQuery(event.currentTarget.value)}/></label>
    <button type="button" disabled={!p.connected||p.pending} onClick={()=>void p.onSearch(kind,query.trim())}>{copy.catalogLoad}</button>
    {!p.connected&&<p>{copy.catalogNeedsProbe}</p>}
    {p.connected&&current!==null&&resultIdentityMatches&&(
      <>
      {isPrevious&&<p role="status">{copy.previousCatalog}</p>}
      <p role="status">{formatCopy.catalogLoaded(current.items.length)}{current.nextCursor!==null&&copy.catalogMore}</p>
      <div className="table-scroll catalog-tree" role="region" aria-label={copy.catalogResults} tabIndex={0}>
      {visibleGroups.map(entry=>{
        const ordinal=(labelOrdinals.get(entry.group.label)??0)+1;
        labelOrdinals.set(entry.group.label,ordinal);
        const repeated=(labelCounts.get(entry.group.label)??0)>1;
        const summary=entry.group.label+(repeated?` (${ordinal})`:"")+" · "+formatCopy.catalogLoaded(entry.items.length);
        const open=overrides.get(entry.group.id)??current.query!=="";
        return<details key={entry.group.id} open={open}>
          <summary onClick={event=>setGroupOpen(entry.group.id,!(event.currentTarget.parentElement as HTMLDetailsElement).open)}>{summary}</summary>
          <ul className="catalog-leaves">{entry.items.map(item=><li key={item.selector}>
            <div className="catalog-leaf-text"><code>{item.selector}</code>
              <small>{"typeName" in item?item.typeName:formatCopy.bits(item.sizeBits)}</small>
              {"sampleable" in item&&!item.sampleable&&<small>{formatCopy.registerUnavailable(item.access,item.readAction)}</small>}
              {"requiresAccessAcknowledgement" in item&&item.requiresAccessAcknowledgement&&<small>{copy.registerAccessAcknowledgement}</small>}
            </div>
            <button type="button" aria-label={copy.addDraft} title={copy.addDraft}
              disabled={isPrevious||p.pending||p.editBusy||("sampleable" in item&&!item.sampleable)}
              onClick={()=>{if(!isPrevious&&!p.pending&&!p.editBusy)addWatch(item,p.onAdd);}}>+</button>
          </li>)}</ul>
        </details>;
      })}</div></>)}
    <button type="button" disabled={!resultIdentityMatches||isPrevious||current?.nextCursor===null||p.pending} onClick={()=>void p.onNext(kind)}>{copy.nextPage}</button>
  </section>;
}
