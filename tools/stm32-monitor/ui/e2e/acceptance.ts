import {expect,type BrowserContext,type Page} from "@playwright/test";
import type {AssetSizes,DropTotals,MonitorHandle,ProducerOptions} from "./conftest";

export type GuardEvidence={attempts:string[]};

export async function installSameOriginGuard(context:BrowserContext,allowed:string):Promise<GuardEvidence>{
  const base=new URL(allowed);
  const attempts:string[]=[];
  const permitted=(candidate:URL,websocket:boolean)=>candidate.hostname===base.hostname&&candidate.port===base.port&&candidate.protocol===(websocket?(base.protocol==="https:"?"wss:":"ws:"):base.protocol);
  await context.route("**/*",async route=>{
    const url=new URL(route.request().url());
    if(!permitted(url,false)){attempts.push(url.origin);await route.abort("blockedbyclient");}
    else await route.continue();
  });
  await context.routeWebSocket(/.*/,async socket=>{
    const url=new URL(socket.url());
    if(!permitted(url,true)){attempts.push(url.origin);await socket.close();}
    else socket.connectToServer();
  });
  return{attempts};
}

export const typedValues=(count:number):readonly Record<string,unknown>[]=>Array.from({length:count},(_,index)=>({expression:`v${index}`,typeName:"uint32_t",value:index,rawHex:`0x${index.toString(16).padStart(8,"0")}`,bitWidth:32}));

export async function realizedChartPointCount(page:Page):Promise<number>{
  const value=await page.locator("[data-chart-realized-points]").getAttribute("data-chart-realized-points");
  return value===null?0:Number(value);
}

export type InstrumentedWindow=Window&{__monitorUpdates?:number[];__monitorLongTasks?:number[];__monitorLongTaskObserver?:PerformanceObserver;__monitorQueue?:number[]};

export type HeapSample={minute:number;bytes:number};

export type DropEvidence={subscriber:string;history:string;deadline:string;service:string};
export type AssetEvidence={rawBytes:string;gzipJsBytes:string;gzipCssBytes:string};

export type PerformanceEvidence={
  updateP50Ms:number;
  updateP95Ms:number;
  updateMaxMs:number;
  longTasksAtLeast200Ms:number;
  queueGrowth:number;
  heapSlopeMiBPerMinute:number;
  serverDropsBefore:DropEvidence;
  serverDropsAfter:DropEvidence;
  realizedPoints:number;
  sampleCount:string;
  assetSizes:AssetEvidence;
  warmupMs:number;
  measureMs:number;
};

export async function createGroupViaApi(monitor:MonitorHandle,name:string,rows:number):Promise<string>{
  const token=/(?:token=)([0-9a-f]{64})/.exec(monitor.accessUrl)?.[1];
  if(token===undefined)throw new Error("access URL lacks a token");
  const items=Array.from({length:rows},(_,index)=>({kind:"variable",expression:`v${index}`}));
  const response=await fetch(monitor.url+"/api/v1/groups",{
    method:"POST",
    headers:{authorization:`Bearer ${token}`,"content-type":"application/json",origin:monitor.url},
    body:JSON.stringify({name,description:"",intervalMs:100,items,authorized:true}),
  });
  const envelope=(await response.json()) as {ok:boolean;data?:{groupId:string}};
  if(!envelope.ok||envelope.data===undefined)throw new Error("group creation failed");
  return envelope.data.groupId;
}

export async function selectSeries(page:Page,count:number):Promise<void>{
  for(let index=0;index<count;index++){
    await page.getByRole("button",{name:"Off"}).first().click();
  }
}

export async function collectFiveMinuteMetrics(
  page:Page,
  monitor:MonitorHandle,
  options:{warmupMs:number;measureMs:number;producer:ProducerOptions},
):Promise<PerformanceEvidence>{
  await page.evaluate(()=>{
    const target=window as unknown as InstrumentedWindow;
    target.__monitorUpdates=[];
    target.__monitorLongTasks=[];
    target.__monitorQueue=[];
    addEventListener("stm32-monitor:chart-update",(event)=>{
      const value=(event as CustomEvent<{durationMs:number}>).detail.durationMs;
      if(Number.isFinite(value))target.__monitorUpdates!.push(value);
    });
    target.__monitorLongTaskObserver=new PerformanceObserver(list=>{
      target.__monitorLongTasks!.push(...list.getEntries().map(entry=>entry.duration));
    });
    target.__monitorLongTaskObserver.observe({entryTypes:["longtask"]});
  });

  const producer=await monitor.startProducer(options.producer);
  if(!producer.active)throw new Error("producer did not become active");
  if(!await monitor.producerActive())throw new Error("producer is not active");

  const warmStarted=Date.now();
  await page.waitForTimeout(options.warmupMs);
  if(Date.now()-warmStarted<options.warmupMs)throw new Error("warmup window ended early");

  await page.evaluate(()=>{
    const target=window as unknown as InstrumentedWindow;
    target.__monitorUpdates=[];
    target.__monitorLongTasks=[];
    target.__monitorQueue=[];
  });

  const heaps:HeapSample[]=[];
  const queues:number[]=[];
  const before=await monitor.dropTotals();
  const baseline=await monitor.sampleCount();
  const measureStarted=Date.now();
  while(Date.now()-measureStarted<options.measureMs){
    const remaining=options.measureMs-(Date.now()-measureStarted);
    await page.waitForTimeout(Math.min(5_000,remaining));
    const elapsed=Date.now()-measureStarted;
    const heap=await page.evaluate(()=>(performance as unknown as {memory?:{usedJSHeapSize:number}}).memory?.usedJSHeapSize??0);
    const queue=await page.evaluate(()=>(window as unknown as InstrumentedWindow).__monitorQueue?.length??0);
    heaps.push({minute:elapsed/60_000,bytes:heap});
    queues.push(queue);
  }

  await monitor.stopProducer();
  const longTasks=await page.evaluate(()=>(window as unknown as InstrumentedWindow).__monitorLongTasks??[]);
  const updates=await page.evaluate(()=>(window as unknown as InstrumentedWindow).__monitorUpdates??[]);
  const after=await monitor.dropTotals();
  const realizedPoints=await realizedChartPointCount(page);
  const sampleCount=(await monitor.sampleCount())-baseline;
  const assetSizes=await monitor.assetSizes();

  return summarizePerformance({
    updates,
    heaps,
    queues,
    longTasks,
    dropsBefore:before,
    dropsAfter:after,
    realizedPoints,
    sampleCount,
    assetSizes,
    warmupMs:options.warmupMs,
    measureMs:options.measureMs,
  });
}

type PerformanceInput={
  updates:readonly number[];
  heaps:readonly HeapSample[];
  queues:readonly number[];
  longTasks:readonly number[];
  dropsBefore:DropTotals;
  dropsAfter:DropTotals;
  realizedPoints:number;
  sampleCount:bigint;
  assetSizes:AssetSizes;
  warmupMs:number;
  measureMs:number;
};

function percentile(values:readonly number[],fraction:number):number{
  if(values.length===0)throw new Error("performance sample is empty");
  const sorted=[...values].sort((a,b)=>a-b);
  return sorted[Math.min(sorted.length-1,Math.ceil(sorted.length*fraction)-1)]!;
}

function heapSlope(samples:readonly HeapSample[]):number{
  if(samples.length<2)return 0;
  const xm=samples.reduce((n,x)=>n+x.minute,0)/samples.length;
  const ym=samples.reduce((n,x)=>n+x.bytes,0)/samples.length;
  const numerator=samples.reduce((n,x)=>n+(x.minute-xm)*(x.bytes-ym),0);
  const denominator=samples.reduce((n,x)=>n+(x.minute-xm)**2,0);
  return denominator===0?0:numerator/denominator/1048576;
}

function dropEvidence(value:DropTotals):DropEvidence{
  return{subscriber:value.subscriber.toString(),history:value.history.toString(),deadline:value.deadline.toString(),service:value.service.toString()};
}

function assetEvidence(value:AssetSizes):AssetEvidence{
  return{rawBytes:value.rawBytes.toString(),gzipJsBytes:value.gzipJsBytes.toString(),gzipCssBytes:value.gzipCssBytes.toString()};
}

export function summarizePerformance(input:PerformanceInput):PerformanceEvidence{
  if(input.queues.length<2||input.heaps.length<2)throw new Error("real performance evidence is incomplete");
  return{
    updateP50Ms:percentile(input.updates,0.5),
    updateP95Ms:percentile(input.updates,0.95),
    updateMaxMs:Math.max(...input.updates),
    longTasksAtLeast200Ms:input.longTasks.filter(value=>value>=200).length,
    queueGrowth:input.queues.at(-1)!-input.queues[0]!,
    heapSlopeMiBPerMinute:heapSlope(input.heaps),
    serverDropsBefore:dropEvidence(input.dropsBefore),
    serverDropsAfter:dropEvidence(input.dropsAfter),
    realizedPoints:input.realizedPoints,
    sampleCount:input.sampleCount.toString(),
    assetSizes:assetEvidence(input.assetSizes),
    warmupMs:input.warmupMs,
    measureMs:input.measureMs,
  };
}

export function assertSameServerDrops(before:DropEvidence,after:DropEvidence):void{
  expect(before).toEqual(after);
}
