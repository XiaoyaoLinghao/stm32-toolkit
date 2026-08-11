export class IntegerToken{constructor(readonly decimal:string){}}
const integer=/^-?(?:0|[1-9]\d*)$/;
export function parseLossless(text:string):unknown{
  let sentinel="__stm32_i64__";while(text.includes(sentinel))sentinel+="_";
  let out="",index=0,inString=false,escaped=false;
  while(index<text.length){const c=text[index]!;
    if(inString){out+=c;index++;if(escaped){escaped=false;}else if(c==="\\"){escaped=true;}else if(c==='"'){inString=false;}continue;}
    if(c==='"'){inString=true;out+=c;index++;continue;}
    if(c==='-'||(c>='0'&&c<='9')){let end=index+1;while(end<text.length&&/[0-9.eE+-]/.test(text[end]!))end++;
      const token=text.slice(index,end);out+=integer.test(token)?JSON.stringify(sentinel+token):token;index=end;continue;}
    out+=c;index++;
  }
  return JSON.parse(out,(_key,value)=>typeof value==="string"&&value.startsWith(sentinel)
    ?new IntegerToken(value.slice(sentinel.length)):value);
}
export const i64=(value:unknown):bigint=>{if(!(value instanceof IntegerToken)||!integer.test(value.decimal))throw new Error("expected integer");const result=BigInt(value.decimal);if(result<-(1n<<63n)||result>(1n<<63n)-1n)throw new Error("integer outside signed-int64");return result;};
export function encodeJson(value:unknown):string{
  if(value===null)return"null";if(typeof value==="bigint")return value.toString(10);
  if(typeof value==="string"||typeof value==="boolean")return JSON.stringify(value);
  if(typeof value==="number"){if(!Number.isFinite(value))throw new Error("non-finite JSON number");return JSON.stringify(value);}
  if(Array.isArray(value))return`[${value.map(encodeJson).join(",")}]`;
  if(typeof value==="object")return`{${Object.keys(value).filter(key=>Reflect.get(value,key)!==undefined).map(key=>`${JSON.stringify(key)}:${encodeJson(Reflect.get(value,key))}`).join(",")}}`;
  throw new Error("unsupported JSON value");
}
