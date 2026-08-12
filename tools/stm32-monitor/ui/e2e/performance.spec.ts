import {expect,test,type BrowserContext,type Page} from "@playwright/test";
import {openMonitor,startMonitor} from "./conftest";

type GuardEvidence={attempts:string[]};

async function installSameOriginGuard(context:BrowserContext,allowed:string):Promise<GuardEvidence>{
  const base=new URL(allowed);
  const attempts:string[]=[];
  await context.route("**/*",async route=>{
    const url=new URL(route.request().url());
    if(url.hostname!==base.hostname||url.port!==base.port||url.protocol!==base.protocol){
      attempts.push(url.origin);
      await route.abort("blockedbyclient");
    }else await route.continue();
  });
  return{attempts};
}

type HeapSample={minute:number;bytes:number};

function heapSlope(samples:readonly HeapSample[]):number{
  if(samples.length<2)return 0;
  const xm=samples.reduce((n,x)=>n+x.minute,0)/samples.length;
  const ym=samples.reduce((n,x)=>n+x.bytes,0)/samples.length;
  const numerator=samples.reduce((n,x)=>n+(x.minute-xm)*(x.bytes-ym),0);
  const denominator=samples.reduce((n,x)=>n+(x.minute-xm)**2,0);
  return denominator===0?0:numerator/denominator/1048576;
}

test("production fixture stays bounded under a continuous live stream",async({page,context})=>{
  test.setTimeout(90_000);
  const monitor=await startMonitor(process.cwd(),process.env.STM32_MONITOR_EVIDENCE??process.cwd());
  try{
    const guard=await installSameOriginGuard(context,monitor.url);
    await openMonitor(page,monitor.accessUrl);
    await expect(page.getByLabel("STM32 Monitor")).toBeAttached();
    await page.getByRole("button",{name:"Connect",exact:true}).click();
    await expect(page.getByText(/Connected: probe-a/)).toBeVisible();

    await page.getByRole("button",{name:"New group"}).click();
    for(const expression of ["counter","faulty"]){
      await page.getByLabel("Search").fill(expression);
      await expect(page.getByRole("button",{name:"Add to group"})).toBeVisible();
      await page.getByRole("button",{name:"Add to group"}).click();
    }
    await page.getByLabel("Name").fill("Perf Watch");
    await page.getByRole("button",{name:"Create group"}).click();
    await page.getByRole("button",{name:"Start"}).click();
    await expect(page.getByLabel("Sampling controls").getByRole("status")).toContainText("RUNNING");

    await page.evaluate(()=>{
      const target=window as unknown as {__longTasks:number[]};
      target.__longTasks=[];
      const observer=new PerformanceObserver(list=>{
        target.__longTasks.push(...list.getEntries().map(entry=>entry.duration));
      });
      observer.observe({entryTypes:["longtask"]});
      (window as unknown as {__observer:PerformanceObserver}).__observer=observer;
    });

    const table=page.getByRole("region",{name:"Live values"}).getByRole("table");
    await expect(table).toContainText("counter");
    const heaps:HeapSample[]=[];
    const started=Date.now();
    while(Date.now()-started<10_000){
      await page.waitForTimeout(1_000);
      const heap=await page.evaluate(()=>
        (performance as unknown as {memory?:{usedJSHeapSize:number}}).memory?.usedJSHeapSize??0
      );
      heaps.push({minute:(Date.now()-started)/60_000,bytes:heap});
    }

    const longTasks=await page.evaluate(()=>{
      const tasks=(window as unknown as {__longTasks:number[]}).__longTasks??[];
      (window as unknown as {__observer:PerformanceObserver|undefined}).__observer=undefined;
      return tasks;
    });
    const realizedRows=await table.locator("tbody tr").count();

    expect(longTasks.filter(value=>value>=200).length).toBe(0);
    expect(heapSlope(heaps)).toBeLessThanOrEqual(2);
    expect(realizedRows).toBeGreaterThan(0);
    await expect(page.getByLabel("Sampling controls").getByRole("status")).toContainText("RUNNING");
    expect(guard.attempts).toEqual([]);
  }finally{
    monitor.stop();
  }
});
