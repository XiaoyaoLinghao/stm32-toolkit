import {spawn,type ChildProcess} from "node:child_process";
import {resolve} from "node:path";
import type {Page} from "@playwright/test";

export type DropTotals={subscriber:bigint;history:bigint;deadline:bigint;service:bigint};
export type AssetSizes={rawBytes:bigint;gzipJsBytes:bigint;gzipCssBytes:bigint};
export type ProducerOptions={hz:number;typedValues:readonly unknown[]};

export type MonitorHandle={
  url:string;
  accessUrl:string;
  stop:()=>void;
  startProducer:(options:ProducerOptions)=>Promise<{active:boolean;confirmedAtUnixNs:bigint}>;
  stopProducer:()=>Promise<void>;
  producerActive:()=>Promise<boolean>;
  dropTotals:()=>Promise<DropTotals>;
  sampleCount:()=>Promise<bigint>;
  assetSizes:()=>Promise<AssetSizes>;
  rows:()=>Promise<number>;
};

async function controlCall(controlUrl:string,method:string,path:string,body?:unknown):Promise<Record<string,unknown>>{
  const init:RequestInit={method};
  if(body!==undefined){
    init.headers={"content-type":"application/json"};
    init.body=JSON.stringify(body);
  }
  const response=await fetch(controlUrl+path,init);
  if(!response.ok)throw new Error(`control ${path} returned ${response.status}`);
  const parsed=(await response.json()) as Record<string,unknown>;
  if(parsed.ok!==true)throw new Error(`control ${path} failed: ${String(parsed.code??"unknown")}`);
  return parsed;
}

export async function startMonitor(projectRoot:string,evidenceRoot:string,rows?:number):Promise<MonitorHandle>{
  const repo=resolve("../../..");
  const python=process.env.STM32_MONITOR_PYTHON??"python";
  const args=[resolve("e2e/fake_runtime.py"),"--repo",repo];
  if(rows!==undefined)args.push("--rows",String(rows));
  const child=spawn(python,args,{
    cwd:resolve("."),
    stdio:["ignore","pipe","pipe"],
    windowsHide:true,
  });
  const output=await new Promise<string>((resolvePromise,reject)=>{
    let buffer="";
    const timeout=setTimeout(()=>{
      child.kill();
      reject(new Error("monitor did not start in time"));
    },20000);
    child.stdout!.on("data",(chunk:Buffer)=>{
      buffer+=chunk.toString();
      const line=buffer.split("\n").find(line=>line.startsWith("{"));
      if(line!==undefined){
        clearTimeout(timeout);
        resolvePromise(line);
      }
    });
    child.stderr!.on("data",(chunk:Buffer)=>{
      if(chunk.toString().includes("Traceback")){
        clearTimeout(timeout);
        reject(new Error(`monitor failed: ${chunk.toString()}`));
      }
    });
    child.on("exit",code=>{
      clearTimeout(timeout);
      reject(new Error(`monitor exited early with ${code}`));
    });
    child.unref();
  });
  const parsed=JSON.parse(output) as {ok:boolean;accessUrl:string;url:string;controlUrl?:string};
  if(!parsed.ok)throw new Error("monitor reported failure");
  void evidenceRoot;
  void projectRoot;
  (child as ChildProcess & {monitor?:boolean}).monitor=true;
  const controlUrl=parsed.controlUrl??"";
  return{
    url:parsed.url,
    accessUrl:parsed.accessUrl,
    stop:()=>{child.kill();},
    startProducer:async(options)=>{
      const started=await controlCall(controlUrl,"POST","/producer/start",{hz:options.hz});
      return{active:started.active===true,confirmedAtUnixNs:BigInt(Date.now())*1000000n};
    },
    stopProducer:async()=>{[void(await controlCall(controlUrl,"POST","/producer/stop"))];},
    producerActive:async()=>{
      const status=await controlCall(controlUrl,"GET","/producer/status");
      return status.active===true;
    },
    dropTotals:async()=>{
      const result=await controlCall(controlUrl,"GET","/drops");
      const drops=result.drops as Record<string,unknown>;
      return{
        subscriber:BigInt(String(drops.subscriber??"0")),
        history:BigInt(String(drops.history??"0")),
        deadline:BigInt(String(drops.deadline??"0")),
        service:BigInt(String(drops.service??"0")),
      };
    },
    sampleCount:async()=>{
      const result=await controlCall(controlUrl,"GET","/sample-count");
      return BigInt(String(result.count??"0"));
    },
    assetSizes:async()=>{
      const result=await controlCall(controlUrl,"GET","/assets");
      const assets=result.assets as Record<string,unknown>;
      return{
        rawBytes:BigInt(String(assets.rawBytes??"0")),
        gzipJsBytes:BigInt(String(assets.gzipJsBytes??"0")),
        gzipCssBytes:BigInt(String(assets.gzipCssBytes??"0")),
      };
    },
    rows:async()=>{
      const result=await controlCall(controlUrl,"GET","/rows");
      return Number(result.rows??0);
    },
  };
}

export async function openMonitor(page:Page,accessUrl:string):Promise<void>{
  await page.goto(accessUrl,{waitUntil:"domcontentloaded"});
  await page.waitForTimeout(500);
}

export function fixtureToken(accessUrl:string):string{
  const match=/token=([0-9a-f]{64})/.exec(accessUrl);
  if(match===null)throw new Error("access URL lacks a 64-hex token");
  const token=match[1];
  if(token===undefined)throw new Error("access URL lacks a 64-hex token");
  return token;
}
