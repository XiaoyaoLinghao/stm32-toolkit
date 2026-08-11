import {existsSync,readFileSync,readdirSync,rmSync,statSync} from "node:fs";
import {tmpdir} from "node:os";
import {join,resolve,relative} from "node:path";
import {execFileSync} from "node:child_process";

const uiRoot=resolve(".");
const committed=resolve("../src/stm32_monitor/ui_dist");
const buildCommand=()=>{
  const comspec=process.env.ComSpec||"cmd.exe";
  const script=join(uiRoot,"node_modules/.bin/vite");
  const viteBin=existsSync(script+".cmd")?script+".cmd":script;
  return{comspec,args:["/c",viteBin,"build","--outDir","REPLACE","--emptyOutDir"]};
};

if(!existsSync(join(committed,"index.html"))||!existsSync(join(committed,".vite/manifest.json")))throw new Error("committed ui_dist is incomplete");
const collect=dir=>{const names=[];const walk=current=>{for(const name of readdirSync(current)){const path=join(current,name),info=statSync(path);if(info.isDirectory())walk(path);else names.push(relative(dir,path).split("\\").join("/"));}};walk(dir);return names.sort();};
const committedFiles=collect(committed);
const manifest=JSON.parse(readFileSync(join(committed,".vite/manifest.json"),"utf8"));
for(const record of Object.values(manifest)){
  if(typeof record!=="object")continue;
  for(const field of ["file","css"]){
    const value=record[field];
    if(typeof value==="string"&&!committedFiles.includes(value))throw new Error(`manifest references missing ${value}`);
    if(Array.isArray(value))for(const item of value)if(typeof item==="string"&&!committedFiles.includes(item))throw new Error(`manifest references missing ${item}`);
  }
}
if(committedFiles.some(name=>name.endsWith(".map")))throw new Error("committed ui_dist contains source maps");

const temp=join(tmpdir(),`stm32tk-ui-dist-${process.pid}-${Date.now()}`);
rmSync(temp,{recursive:true,force:true});
try{
  const {comspec,args}=buildCommand();
  execFileSync(comspec,args.map(arg=>arg==="REPLACE"?temp:arg),{cwd:uiRoot,stdio:"pipe"});
  const rebuilt=collect(temp);
  if(rebuilt.join("\n")!==committedFiles.join("\n"))throw new Error(`rebuilt ui_dist inventory differs: expected ${committedFiles.length} files, got ${rebuilt.length}`);
  for(const name of committedFiles){
    const after=readFileSync(join(temp,name));
    const before=readFileSync(join(committed,name));
    if(!before.equals(after))throw new Error(`ui_dist ${name} is not byte-identical`);
  }
  console.log(`verify:dist OK (${committedFiles.length} files byte-identical)`);
}finally{
  rmSync(temp,{recursive:true,force:true});
}
