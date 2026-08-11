import {existsSync,readFileSync,readdirSync,statSync} from "node:fs";
import {resolve,relative,sep} from "node:path";
if(process.argv.includes("--dist")&&!existsSync("dist"))throw new Error("dist is absent");
const root=resolve("src");
const excluded=new Set([resolve("src/main.tsx"),resolve("src/env.d.ts")]);
const coveragePath=resolve("coverage/coverage-final.json");
if(!existsSync(coveragePath))throw new Error("coverage-final.json is absent; run vitest with coverage first");
const coverage=JSON.parse(readFileSync(coveragePath,"utf8"));
const normalized=new Map(Object.entries(coverage).map(([path,value])=>[resolve(path),value]));
const files=[];
const walk=dir=>{for(const name of readdirSync(dir)){const path=resolve(dir,name),info=statSync(path);
  if(info.isDirectory())walk(path);else if(/\.(?:ts|tsx)$/.test(name)&&!name.endsWith(".d.ts")&&!excluded.has(path))files.push(path);}};
walk(root);
const failures=[];
for(const file of files.sort()){
  const entry=normalized.get(file);
  if(entry===undefined){failures.push(`${relative(root,file).split(sep).join("/")}: no coverage record`);continue;}
  const counters=Object.values(entry.b).flat();
  const covered=counters.filter(value=>value>0).length;
  const percent=counters.length===0?100:covered*100/counters.length;
  if(percent<90)failures.push(`${relative(root,file).split(sep).join("/")}: branches ${percent.toFixed(2)}%`);
}
if(failures.length!==0){console.error(failures.join("\n"));process.exit(1);}
console.log("branch coverage: all src files >= 90%");
