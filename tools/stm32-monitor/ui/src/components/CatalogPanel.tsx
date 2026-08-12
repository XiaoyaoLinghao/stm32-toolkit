import type {JSX} from "preact";
import {useState} from "preact/hooks";
import type {RegisterDescriptor,VariableDescriptor,WatchItem} from "../api/contract";
import type {VariableCatalog,RegisterCatalog,CatalogKind} from "../state/model";

export type CatalogPanelProps={
  connected:boolean;
  bindingEpoch:bigint;
  variables:VariableCatalog|null;
  registers:RegisterCatalog|null;
  onSearch:(kind:CatalogKind,query:string)=>void|Promise<void>;
  onNext:(kind:CatalogKind)=>void|Promise<void>;
  onAdd:(watch:WatchItem)=>void|Promise<void>;
};

export type CatalogResult<T>={kind:CatalogKind;query:string;bindingEpoch:bigint;items:readonly T[];nextCursor:string|null};

function addWatch(descriptor:VariableDescriptor|RegisterDescriptor,onAdd:(watch:WatchItem)=>void|Promise<void>):void{
  if("expression" in descriptor||"memberNames" in descriptor||"elementCount" in descriptor){
    void onAdd({kind:"variable",expression:descriptor.selector});
  }else{
    void onAdd({kind:"register",registerPath:descriptor.selector});
  }
}

export function CatalogPanel(p:CatalogPanelProps):JSX.Element{
  const [kind,setKind]=useState<CatalogKind>("variables");
  const [query,setQuery]=useState("");
  const current=kind==="variables"?p.variables:p.registers;
  const resultIdentityMatches=current!==null&&current.query===query.trim()&&current.bindingKey.includes(String(p.bindingEpoch));

  return<section className="panel" aria-label="Catalog">
    <h2>Symbol &amp; register catalog</h2>
    <div role="tablist" aria-label="Catalog kind">
      <button type="button" role="tab" aria-selected={kind==="variables"} onClick={()=>setKind("variables")}>Variables</button>
      <button type="button" role="tab" aria-selected={kind==="registers"} onClick={()=>setKind("registers")}>Registers</button>
    </div>
    <label>Search <input value={query} placeholder="symbol or register prefix" disabled={!p.connected}
      onInput={event=>{const value=event.currentTarget.value;setQuery(value);void p.onSearch(kind,value.trim());}}/></label>
    {!p.connected&&<p>Connect a probe to search the catalog.</p>}
    {p.connected&&current!==null&&resultIdentityMatches&&(
      <table><thead><tr><th>Selector</th><th>Type</th><th>Action</th></tr></thead>
        <tbody>{(kind==="variables"?current.items:current.items as RegisterDescriptor[]).map(item=>{
          const descriptor=item as VariableDescriptor|RegisterDescriptor;
          return<tr key={descriptor.selector}>
            <td><code>{descriptor.selector}</code></td>
            <td>{"typeName" in descriptor?descriptor.typeName:`${descriptor.sizeBits} bit`}</td>
            <td><button type="button" onClick={()=>addWatch(descriptor,p.onAdd)}>Add to group</button></td>
          </tr>;})}</tbody></table>)}
    <button type="button" disabled={!resultIdentityMatches||current?.nextCursor===null} onClick={()=>void p.onNext(kind)}>Next page</button>
  </section>;
}
