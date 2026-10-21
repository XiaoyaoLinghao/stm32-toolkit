import type {WatchItem} from "../api/contract";

export const watchKey=(watch:WatchItem):string=>{
  if(watch.kind==="variable")return `variable:${watch.expression}`;
  if(watch.kind==="register")return `register:${watch.registerPath}`;
  return `u16le:${JSON.stringify([watch.lowExpression,watch.highExpression])}`;
};

export const watchFullLabel=(watch:WatchItem):string=>{
  if(watch.kind==="variable")return watch.expression;
  if(watch.kind==="register")return watch.registerPath;
  return `u16(${watch.lowExpression}, ${watch.highExpression})`;
};

export const watchLabel=(watch:WatchItem):string=>{
  if(watch.kind!=="u16le")return watchFullLabel(watch);
  const low=/^(.*)\[(\d+)\]$/.exec(watch.lowExpression);
  const high=/^(.*)\[(\d+)\]$/.exec(watch.highExpression);
  if(low!==null&&high!==null&&low[1]===high[1]&&Number(high[2])===Number(low[2])+1)
    return `${low[1]}[${low[2]},${high[2]}] (16位)`;
  return watchFullLabel(watch);
};

export const watchLabelFromKey=(key:string):string=>{
  if(key.startsWith("variable:"))return key.slice(9);
  if(key.startsWith("register:"))return key.slice(9);
  if(key.startsWith("u16le:")){
    try{
      const pair:unknown=JSON.parse(key.slice(6));
      if(Array.isArray(pair)&&pair.length===2&&pair.every(value=>typeof value==="string"))
        return watchLabel({kind:"u16le",lowExpression:pair[0] as string,highExpression:pair[1] as string});
    }catch{/* An unknown key remains visible as received. */}
  }
  return key;
};
