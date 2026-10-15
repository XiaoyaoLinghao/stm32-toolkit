import type {JSX} from "preact";
import {useState} from "preact/hooks";
import type {RegisterDescriptor,VariableDescriptor,WatchItem} from "../api/contract";
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

export type CatalogResult<T>={kind:CatalogKind;query:string;bindingEpoch:bigint;items:readonly T[];nextCursor:string|null};

function addWatch(descriptor:VariableDescriptor|RegisterDescriptor,onAdd:(watch:WatchItem)=>void|Promise<void>):void{
  if("expression" in descriptor||"memberNames" in descriptor||"elementCount" in descriptor){
    void onAdd({kind:"variable",expression:descriptor.selector});
  }else{
    if(!descriptor.sampleable)return;
    void onAdd({kind:"register",registerPath:descriptor.selector});
  }
}

export function CatalogPanel(p:CatalogPanelProps):JSX.Element{
  const [kind,setKind]=useState<CatalogKind>("variables");
  const [query,setQuery]=useState("");
  const current=kind==="variables"?p.variables:p.registers;
  const resultIdentityMatches=current!==null&&(p.bindingKey===undefined
    ?current.bindingKey.endsWith("/"+String(p.bindingEpoch)):current.bindingKey===p.bindingKey);
  const isPrevious=resultIdentityMatches&&current.query!==query.trim();

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
      <div className="table-scroll" role="region" aria-label={copy.catalogResults} tabIndex={0}>
      <table><thead><tr><th>{copy.selector}</th><th>{copy.type}</th><th>{copy.action}</th></tr></thead>
        <tbody>{(kind==="variables"?current.items:current.items as RegisterDescriptor[]).map(item=>{
          const descriptor=item as VariableDescriptor|RegisterDescriptor;
          return<tr key={descriptor.selector}>
            <td><code>{descriptor.selector}</code></td>
            <td>{"typeName" in descriptor?descriptor.typeName:formatCopy.bits(descriptor.sizeBits)}</td>
            <td><button type="button" disabled={isPrevious||p.pending||p.editBusy||("sampleable" in descriptor&&!descriptor.sampleable)}
              onClick={()=>{if(!isPrevious&&!p.pending&&!p.editBusy)addWatch(descriptor,p.onAdd);}}>{copy.addDraft}</button>
              {"sampleable" in descriptor&&!descriptor.sampleable&&<span>{formatCopy.registerUnavailable(descriptor.access,descriptor.readAction)}</span>}
              {"requiresAccessAcknowledgement" in descriptor&&descriptor.requiresAccessAcknowledgement&&<span>{copy.registerAccessAcknowledgement}</span>}
            </td>
          </tr>;})}</tbody></table></div></>)}
    <button type="button" disabled={!resultIdentityMatches||isPrevious||current?.nextCursor===null||p.pending} onClick={()=>void p.onNext(kind)}>{copy.nextPage}</button>
  </section>;
}
