import {describe,expect,it,vi} from "vitest";
import type {Page} from "@playwright/test";
import {collectFiveMinuteMetrics,sampleRetainedHeap} from "../e2e/acceptance";
import type {MonitorHandle} from "../e2e/conftest";

describe("retained heap sampling",()=>{
  it("requests garbage collection before reading used JS heap",async()=>{
    const calls:string[]=[];
    const page={
      requestGC:vi.fn(async()=>{calls.push("gc");}),
      evaluate:vi.fn(async()=>{calls.push("heap");return 12_345_678;}),
    };

    await expect(sampleRetainedHeap(page)).resolves.toBe(12_345_678);
    expect(calls).toEqual(["gc","heap"]);
  });

  it("garbage-collects every heap sample in the measurement loop",async()=>{
    let now=0;
    const calls:string[]=[];
    const dateNow=vi.spyOn(Date,"now").mockImplementation(()=>now);
    const originalMemory=Object.getOwnPropertyDescriptor(performance,"memory");
    const originalObserver=globalThis.PerformanceObserver;
    Object.defineProperty(performance,"memory",{configurable:true,value:{usedJSHeapSize:12_345_678}});
    Object.defineProperty(globalThis,"PerformanceObserver",{
      configurable:true,
      value:class {observe():void{}},
    });
    const page={
      evaluate:vi.fn(async <T>(callback:()=>T)=>{calls.push("evaluate");return callback();}),
      requestGC:vi.fn(async()=>{calls.push("gc");}),
      waitForTimeout:vi.fn(async(ms:number)=>{
        now+=ms;
        window.dispatchEvent(new CustomEvent("stm32-monitor:chart-update",{detail:{durationMs:1}}));
      }),
      locator:vi.fn(()=>({getAttribute:vi.fn(async()=>"4800")})),
    } as unknown as Page;
    let samples=0n;
    const monitor={
      startProducer:vi.fn(async()=>({active:true})),
      producerActive:vi.fn(async()=>true),
      stopProducer:vi.fn(async()=>undefined),
      dropTotals:vi.fn(async()=>({subscriber:0n,history:0n,deadline:0n,service:0n})),
      sampleCount:vi.fn(async()=>samples++),
      assetSizes:vi.fn(async()=>({rawBytes:1n,gzipJsBytes:1n,gzipCssBytes:1n})),
    } as unknown as MonitorHandle;
    try{
      await collectFiveMinuteMetrics(page,monitor,{
        warmupMs:0,
        measureMs:5_001,
        producer:{hz:10,typedValues:[]},
      });
      expect(page.requestGC).toHaveBeenCalledTimes(2);
      const gcIndexes=calls.flatMap((call,index)=>call==="gc"?[index]:[]);
      expect(gcIndexes).toHaveLength(2);
      expect(gcIndexes.every(index=>calls[index+1]==="evaluate")).toBe(true);
    }finally{
      dateNow.mockRestore();
      if(originalMemory===undefined)delete (performance as unknown as {memory?:unknown}).memory;
      else Object.defineProperty(performance,"memory",originalMemory);
      Object.defineProperty(globalThis,"PerformanceObserver",{configurable:true,value:originalObserver});
    }
  });
});
