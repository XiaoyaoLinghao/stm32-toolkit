import {expect,it} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {parseEnvelope,registersGuard,variablesGuard} from "../src/api/contract";
import {CatalogPanel} from "../src/components/CatalogPanel";

const variable={selector:"counter",typeName:"uint32_t",kind:"base",byteSize:4,signed:false,encoding:null,
  qualifiers:[],aliases:[],enumValues:[],elementCount:null,elementKind:null,memberNames:[]};
const register={selector:"GPIO.A.CH0.VALUE",sizeBits:32,access:"read-only",readAction:null,
  resetValue:null,resetMask:null,fields:[],sampleable:true,requiresAccessAcknowledgement:false};
const envelope=(operation:string,data:unknown)=>JSON.stringify({protocol:"stm32-toolkit-monitor/1",toolkitVersion:"1.1.2",monitorVersion:"1.1.2",ok:true,operation,code:"OK",message:"",data,details:{}});

it("requires a strict catalog group while preserving descriptor guards",()=>{
  const payload={items:[{...variable,group:{id:"cu:3a9a",label:"App/vs10_app.c"}}],nextCursor:null};
  const accepted=parseEnvelope(envelope("monitor.catalog.variables",payload),"monitor.catalog.variables",variablesGuard);
  expect(accepted.ok).toBe(true);
  if(accepted.ok)expect(accepted.data.items[0]?.group).toEqual({id:"cu:3a9a",label:"App/vs10_app.c"});
  for(const item of [{...variable},{...variable,group:{id:"cu:3a9a",label:"x",extra:1}},
    {...variable,group:{id:"cu:3a9a",label:"C:\\secret\\file.c"}},
    {...variable,group:{id:"cu:3a9a",label:"bad\nlabel"}},
    {...variable,group:{id:"cu/path",label:"main.c"}},
    {...variable,group:{id:"cu:1",label:"../main.c"}},
    {...variable,group:{id:"cu:1",label:"x".repeat(513)}},
    {...variable,group:{id:"cu:1",label:"main.c"},unexpected:true}]){
    const result=parseEnvelope(envelope("monitor.catalog.variables",{items:[item],nextCursor:null}),"monitor.catalog.variables",variablesGuard);
    expect(result.ok).toBe(false);
  }
  const registers=parseEnvelope(envelope("monitor.catalog.registers",{items:[{...register,group:{id:"svd:abc",label:"GPIO.A"}}],nextCursor:null}),"monitor.catalog.registers",registersGuard);
  expect(registers.ok).toBe(true);
});

it("rejects every conflicting page without dropping or silently rebinding leaves",()=>{
  const conflict={items:[
    {...variable,group:{id:"cu:1",label:"first.c"}},
    {...variable,selector:"other",group:{id:"cu:1",label:"other.c"}},
  ],nextCursor:null};
  expect(parseEnvelope(envelope("monitor.catalog.variables",conflict),"monitor.catalog.variables",variablesGuard)).toMatchObject({ok:false,code:"MONITOR_RESPONSE_INVALID"});
  const selectorConflict={items:[{...variable,group:{id:"cu:1",label:"first.c"}},
    {...variable,group:{id:"cu:2",label:"second.c"}}],nextCursor:null};
  expect(parseEnvelope(envelope("monitor.catalog.variables",selectorConflict),"monitor.catalog.variables",variablesGuard)).toMatchObject({ok:false,code:"MONITOR_RESPONSE_INVALID"});
});

it("keeps same-label source CUs separate and retains native expansion across appended pages",async()=>{
  const first={...variable,selector:"a",group:{id:"cu:1",label:"main.c"}};
  const second={...variable,selector:"b",group:{id:"cu:2",label:"main.c"}};
  const catalog=(items:(typeof first)[],query="",nextCursor:string|null="next")=>({kind:"variables" as const,query,bindingKey:"w/s/p/3",cursor:null,items,nextCursor});
  const add=()=>undefined;
  const view=render(<CatalogPanel connected bindingEpoch={3n} variables={catalog([first,second])} registers={null}
    onSearch={add} onNext={add} onAdd={add}/>);
  let details=[...view.container.querySelectorAll("details")];
  expect(details).toHaveLength(2);
  expect(details.every(node=>!node.open)).toBe(true);
  expect(screen.getByText("已加载 2 项；还有更多结果，可加载下一页。")).toBeTruthy();
  const summary=details[0]!.querySelector("summary")!;
  summary.focus();
  expect(document.activeElement).toBe(summary);
  await userEvent.click(summary);
  expect(details[0]!.open).toBe(true);
  expect(details[1]!.open).toBe(false);
  view.rerender(<CatalogPanel connected bindingEpoch={3n} variables={catalog([first,second,{...variable,selector:"c",group:first.group}],"",null)} registers={null}
    onSearch={add} onNext={add} onAdd={add}/>);
  details=[...view.container.querySelectorAll("details")];
  expect(details[0]!.open).toBe(true);
  expect(details[1]!.open).toBe(false);
  expect(screen.getByText("已加载 3 项")).toBeTruthy();
  view.rerender(<CatalogPanel connected bindingEpoch={3n} variables={catalog([first,second],"a",null)} registers={null}
    onSearch={add} onNext={add} onAdd={add}/>);
  details=[...view.container.querySelectorAll("details")];
  expect(details.every(node=>node.open)).toBe(true);
  view.rerender(<CatalogPanel connected bindingEpoch={4n} bindingKey="w/s/p/4" variables={catalog([first,second],"a",null)} registers={null}
    onSearch={add} onNext={add} onAdd={add}/>);
  expect(view.container.querySelectorAll("details")).toHaveLength(0);
});

it("treats prototype-named group IDs as independent expansion choices across pages",async()=>{
  const items=["__proto__","constructor","toString"].map((id,index)=>({...variable,
    selector:`value${index}`,group:{id,label:`source${index}.c`}}));
  const catalog=(pageItems:typeof items,query="")=>({kind:"variables" as const,query,
    bindingKey:"w/s/p/3",cursor:null,items:pageItems,nextCursor:null});
  const noop=()=>undefined;
  const view=render(<CatalogPanel connected bindingEpoch={3n} variables={catalog(items)} registers={null}
    onSearch={noop} onNext={noop} onAdd={noop}/>);
  let details=[...view.container.querySelectorAll("details")];
  expect(details.map(node=>node.open)).toEqual([false,false,false]);
  await userEvent.click(details[0]!.querySelector("summary")!);
  details=[...view.container.querySelectorAll("details")];
  expect(details.map(node=>node.open)).toEqual([true,false,false]);
  view.rerender(<CatalogPanel connected bindingEpoch={3n} variables={catalog([...items,{...variable,
    selector:"later",group:items[0]!.group}])} registers={null}
    onSearch={noop} onNext={noop} onAdd={noop}/>);
  details=[...view.container.querySelectorAll("details")];
  expect(details.map(node=>node.open)).toEqual([true,false,false]);
  view.rerender(<CatalogPanel connected bindingEpoch={3n} variables={catalog(items,"value")} registers={null}
    onSearch={noop} onNext={noop} onAdd={noop}/>);
  details=[...view.container.querySelectorAll("details")];
  expect(details.map(node=>node.open)).toEqual([true,true,true]);
});

it("resets an expansion choice after a binding round-trip even when the other binding has no result",async()=>{
  const item={...variable,group:{id:"cu:1",label:"main.c"}};
  const a={kind:"variables" as const,query:"",bindingKey:"w/s/p/3",cursor:null,items:[item],nextCursor:null};
  const view=render(<CatalogPanel connected bindingEpoch={3n} bindingKey="w/s/p/3" variables={a} registers={null}
    onSearch={()=>undefined} onNext={()=>undefined} onAdd={()=>undefined}/>);
  await userEvent.click(view.container.querySelector("summary")!);
  expect(view.container.querySelector("details")?.open).toBe(true);
  view.rerender(<CatalogPanel connected bindingEpoch={4n} bindingKey="w/s/p/4" variables={a} registers={null}
    onSearch={()=>undefined} onNext={()=>undefined} onAdd={()=>undefined}/>);
  view.rerender(<CatalogPanel connected bindingEpoch={3n} bindingKey="w/s/p/3" variables={a} registers={null}
    onSearch={()=>undefined} onNext={()=>undefined} onAdd={()=>undefined}/>);
  expect(view.container.querySelector("details")?.open).toBe(false);
});

it("keeps variable and register expansion choices separate",async()=>{
  const variables={kind:"variables" as const,query:"",bindingKey:"w/s/p/3",cursor:null,
    items:[{...variable,group:{id:"cu:1",label:"main.c"}}],nextCursor:null};
  const registers={kind:"registers" as const,query:"",bindingKey:"w/s/p/3",cursor:null,
    items:[{...register,group:{id:"svd:gpio",label:"GPIO.A"}}],nextCursor:null};
  const view=render(<CatalogPanel connected bindingEpoch={3n} variables={variables} registers={registers}
    onSearch={()=>undefined} onNext={()=>undefined} onAdd={()=>undefined}/>);
  await userEvent.click(view.container.querySelector("summary")!);
  expect(view.container.querySelector("details")?.open).toBe(true);
  await userEvent.click(screen.getByRole("tab",{name:"寄存器"}));
  expect(view.container.querySelector("details")?.open).toBe(false);
  await userEvent.click(screen.getByRole("tab",{name:"变量"}));
  expect(view.container.querySelector("details")?.open).toBe(true);
});
