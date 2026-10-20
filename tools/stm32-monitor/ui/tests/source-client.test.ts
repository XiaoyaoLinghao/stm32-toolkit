import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {describe,expect,it} from "vitest";
import {createMonitorApi} from "../src/api/client";

const wire=readFileSync(resolve(process.cwd(),"../tests/fixtures/source_catalog_envelope.json"),"utf8");
const treeWire=readFileSync(resolve(process.cwd(),"../tests/fixtures/source_tree_envelope.json"),"utf8");
const origin="http://monitor.test";
const response=(text:string)=>new Response(text,{headers:{"Content-Type":"application/json"}});

describe("source catalog shared backend wire",()=>{
  it("parses complete source files from the backend tree envelope",async()=>{
    let requested="";
    const api=createMonitorApi(async input=>{requested=String(input);return response(treeWire);},origin);
    const result=await api.sourceTree("");
    expect(requested).toContain("/api/v1/catalog/source-tree");
    expect(result.ok).toBe(true);
    if(!result.ok)return;
    expect(result.data.items.map(item=>item.file)).toEqual(["Src/main.c","Src/safe.c","Src/empty.c"]);
    expect(result.data.items[2]).toMatchObject({kind:"file",variableCount:0,scopeCount:0});
  });

  it("accepts only the closed optional compiled-debug coverage and sends explicit refresh",async()=>{
    const document=JSON.parse(treeWire) as Record<string,unknown>;
    const data=document.data as {coverage:Record<string,unknown>};
    data.coverage={...data.coverage,compiledDebug:{available:true,variableCount:9,functionCount:2,fileCount:1}};
    let requested="";
    const api=createMonitorApi(async input=>{requested=String(input);return response(JSON.stringify(document));},origin);
    const result=await api.sourceTree("",undefined,undefined,undefined,true);
    expect(requested).toContain("refresh=1");
    expect(result.ok).toBe(true);
    if(result.ok)expect(result.data.coverage.compiledDebug).toEqual({available:true,variableCount:9,functionCount:2,fileCount:1});
    (data.coverage.compiledDebug as Record<string,unknown>).unrecognized=1;
    expect((await api.sourceTree("")).ok).toBe(false);
  });

  it("parses the backend-emitted envelope through the real client without a probe",async()=>{
    let requested="";
    const api=createMonitorApi(async input=>{requested=String(input);return response(wire);},origin);
    const result=await api.sourceVariables("counter");
    expect(requested).toContain("/api/v1/catalog/source-variables?query=counter");
    expect(result.ok).toBe(true);
    if(!result.ok)return;
    expect(result.data.coverage).toMatchObject({complete:true,totalUnits:1,parsedUnits:1});
    expect(result.data.identity.bindingEpoch).toBe(0n);
    expect(result.data.items[0]).toMatchObject({name:"counter",file:"Src/main.c",canAdd:false,reason:"probe_required",
      declaration:{kind:"unknown",definitionSite:null}});
  });

  it("accepts legacy omitted declaration metadata and rejects forged roles or definition paths",async()=>{
    const base=JSON.parse(wire) as {data:{items:Record<string,unknown>[]}};
    const accept=async(document:typeof base)=>createMonitorApi(async()=>response(JSON.stringify(document)),origin).sourceVariables("");
    const old=structuredClone(base);delete old.data.items[0]!.declaration;
    expect((await accept(old)).ok).toBe(true);
    const proved=structuredClone(base);
    proved.data.items[0]!.declaration={kind:"extern_declaration",definitionSite:{file:"Src/timer.c",line:7}};
    const result=await accept(proved);
    expect(result.ok).toBe(true);
    if(result.ok)expect(result.data.items[0]?.declaration?.definitionSite).toEqual({file:"Src/timer.c",line:7});
    for(const declaration of [
      {kind:"invented",definitionSite:null},
      {kind:"extern_declaration",definitionSite:{file:"../secret.c",line:7}},
      {kind:"extern_declaration",definitionSite:{file:"C:/secret.c",line:7}},
      {kind:"extern_declaration",definitionSite:{file:"Src/timer.c",line:0}},
      {kind:"extern_declaration",definitionSite:null,extra:1},
    ]){
      const invalid=structuredClone(base);invalid.data.items[0]!.declaration=declaration;
      expect((await accept(invalid)).ok).toBe(false);
    }
  });

  it("rejects duplicate IDs, bad parent and catalog, and invalid selection acknowledgement",async()=>{
    const document=JSON.parse(wire) as Record<string,unknown>;
    const data=document.data as Record<string,unknown>;
    data.items=[...(data.items as unknown[]),...(data.items as unknown[])];
    expect((await createMonitorApi(async()=>response(JSON.stringify(document)),origin).sourceVariables("")).ok).toBe(false);
    data.items=(data.items as unknown[]).slice(0,1);
    const api=createMonitorApi(async()=>response(JSON.stringify(document)),origin);
    expect((await api.sourceVariables("",undefined,"c".repeat(64),"a".repeat(64))).ok).toBe(false);
    expect((await api.sourceVariables("",undefined,undefined,"d".repeat(64))).ok).toBe(false);
    const selection={...document,operation:"monitor.catalog.source.selection",data:{catalogId:"a".repeat(64),item:{kind:"variable",expression:"other"}}};
    const selected=await createMonitorApi(async()=>response(JSON.stringify(selection)),origin)
      .sourceSelection("a".repeat(64),"c".repeat(64),"counter");
    expect(selected).toMatchObject({ok:false,code:"MONITOR_RESPONSE_INVALID"});
  });
});
