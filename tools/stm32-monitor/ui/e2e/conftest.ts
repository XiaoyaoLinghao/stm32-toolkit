import {spawn,type ChildProcess} from "node:child_process";
import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import type {Page} from "@playwright/test";

export type MonitorFixture={
  url:string;
  accessUrl:string;
  page:Page;
};

export async function startMonitor(projectRoot:string,evidenceRoot:string):Promise<{url:string;accessUrl:string}>{
  const repo=resolve("../../..");
  const python=process.env.STM32_MONITOR_PYTHON??"python";
  const child=spawn(python,[resolve("e2e/fake_runtime.py"),"--repo",repo],{
    cwd:resolve("."),
    stdio:["ignore","pipe","pipe"],
    windowsHide:true,
  });
  const output=await new Promise<string>((resolvePromise,reject)=>{
    let buffer="";
    const timeout=setTimeout(()=>{
      child.kill();
      reject(new Error("monitor did not start in time"));
    },15000);
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
  const parsed=JSON.parse(output) as {ok:boolean;accessUrl:string;url:string};
  if(!parsed.ok)throw new Error("monitor reported failure");
  void evidenceRoot;
  void projectRoot;
  (child as ChildProcess & {monitor?:boolean}).monitor=true;
  return{url:parsed.url,accessUrl:parsed.accessUrl};
}

export async function openMonitor(page:Page,accessUrl:string):Promise<void>{
  await page.goto(accessUrl,{waitUntil:"domcontentloaded"});
  await page.waitForTimeout(500);
}

export function fixtureToken(accessUrl:string):string{
  const match=/token=([0-9a-f]{64})/.exec(accessUrl);
  if(match===null)throw new Error("access URL lacks a 64-hex token");
  return match[1];
}
