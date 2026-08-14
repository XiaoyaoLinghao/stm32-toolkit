import {mkdirSync,mkdtempSync,rmSync,writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {dirname,join,resolve} from "node:path";
import {spawnSync} from "node:child_process";
import {afterEach,describe,expect,test} from "vitest";

const checker=resolve(process.cwd(),"tests","check-coverage.mjs");
const roots:string[]=[];

type CoverageRecord={b:Record<string,number[]>};

function runChecker(recordsFor:(source:string)=>Record<string,CoverageRecord>){
  const root=mkdtempSync(join(tmpdir(),"stm32-monitor-coverage-checker-"));
  roots.push(root);
  const source=resolve(root,"src","sample.ts");
  mkdirSync(dirname(source),{recursive:true});
  mkdirSync(resolve(root,"coverage"),{recursive:true});
  writeFileSync(source,"export const sample = true;\n");
  writeFileSync(
    resolve(root,"coverage","coverage-final.json"),
    JSON.stringify(recordsFor(source)),
  );
  const result=spawnSync(process.execPath,[checker],{cwd:root,encoding:"utf8"});
  return result;
}

function branches(covered:number,total:number):CoverageRecord{
  return {b:{0:[...Array(covered).fill(1),...Array(total-covered).fill(0)]}};
}

afterEach(()=>{
  for(const root of roots.splice(0))rmSync(root,{recursive:true,force:true});
});
describe("coverage checker",()=>{
  test("rejects a missing coverage record",()=>{
    const result=runChecker(()=>({}));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("sample.ts: no coverage record");
  });

  test("rejects 89.99 percent branch coverage",()=>{
    const result=runChecker(source=>({[source]:branches(8_999,10_000)}));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("branches 89.99%");
  });

  test("treats a source file with no branches as fully covered",()=>{
    const result=runChecker(source=>({[source]:{b:{}}}));
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("all src files >= 90%");
  });

  test("matches Windows path separators and case",()=>{
    const result=runChecker(source=>({
      [source.toUpperCase().replaceAll("\\","/")]:branches(1,1),
    }));
    expect(result.status).toBe(0);
  });

  test("rejects duplicate normalized coverage paths",()=>{
    const result=runChecker(source=>({
      [source]:branches(1,1),
      [source.toUpperCase().replaceAll("\\","/")]:branches(1,1),
    }));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain("duplicate coverage record");
  });
});
