import {writeFileSync,mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import {resolve} from "node:path";
import {expect,test,type BrowserContext,type Page} from "@playwright/test";
import {
  assertSameServerDrops,
  collectFiveMinuteMetrics,
  createGroupViaApi,
  installSameOriginGuard,
  selectSeries,
  typedValues,
} from "./acceptance";
import {openMonitor,startMonitor} from "./conftest";

async function navigate(page:Page,monitor:{accessUrl:string}):Promise<void>{
  await openMonitor(page,monitor.accessUrl);
  await expect(page.getByLabel("STM32 Monitor")).toBeAttached();
}

test("five-minute production fixture stays bounded",async({page,context})=>{
  test.setTimeout(600_000);
  const monitor=await startMonitor(process.cwd(),process.env.STM32_MONITOR_EVIDENCE??process.cwd(),256);
  try{
    const guard=await installSameOriginGuard(context,monitor.url);

    // Create the 256-row group via the API before the page first loads, so the
    // app's initial groups load includes it and selects it as the first group.
    const groupId=await createGroupViaApi(monitor,"Perf Watch",256);
    expect(groupId.length).toBeGreaterThan(0);

    await navigate(page,monitor);
    await expect(page.getByRole("button",{name:"Perf Watch (256)"})).toBeVisible();

    await page.getByRole("button",{name:"Connect",exact:true}).click();
    await expect(page.getByText(/Connected: probe-a/)).toBeVisible();
    await page.getByRole("button",{name:"Start"}).click();
    await expect(page.getByLabel("Sampling controls").getByRole("status")).toContainText("RUNNING");

    await selectSeries(page,8);

    const warmupMs=Number(process.env.STM32_MONITOR_PERF_WARMUP_MS??120_000);
    const measureMs=Number(process.env.STM32_MONITOR_PERF_MEASURE_MS??180_000);
    const metrics=await collectFiveMinuteMetrics(page,monitor,{
      warmupMs,
      measureMs,
      producer:{hz:10,typedValues:typedValues(256)},
    });

    expect(metrics.realizedPoints).toBe(4800);
    expect(metrics.updateP95Ms).toBeLessThanOrEqual(150);
    expect(metrics.longTasksAtLeast200Ms).toBe(0);
    expect(metrics.queueGrowth).toBeLessThanOrEqual(0);
    expect(metrics.heapSlopeMiBPerMinute).toBeLessThanOrEqual(2);
    assertSameServerDrops(metrics.serverDropsBefore,metrics.serverDropsAfter);
    // A 10 Hz producer over the 180 s measured window targets ~1800 batches; the
    // fixture's per-sample serialization overhead yields a sustained rate of
    // ~9-10 Hz, so the assertion is tolerant rather than exact.
    expect(BigInt(metrics.sampleCount)).toBeGreaterThanOrEqual(1500n);
    expect(BigInt(metrics.sampleCount)).toBeLessThanOrEqual(1810n);
    expect(BigInt(metrics.assetSizes.rawBytes)).toBeGreaterThan(0n);
    expect(BigInt(metrics.assetSizes.gzipJsBytes)).toBeGreaterThan(0n);
    expect(BigInt(metrics.assetSizes.gzipCssBytes)).toBeGreaterThan(0n);
    expect(guard.attempts).toEqual([]);

    const evidenceRoot=process.env.STM32_MONITOR_EVIDENCE??resolve(tmpdir(),"stm32-monitor-evidence");
    const outDir=resolve(evidenceRoot,".performance-evidence");
    mkdirSync(outDir,{recursive:true});
    writeFileSync(resolve(outDir,"performance.json"),JSON.stringify(metrics,null,2),"utf-8");
  }finally{
    await monitor.stop();
  }
});
