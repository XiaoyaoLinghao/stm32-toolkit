import {groupImportGuard,type ApiResult,type GroupImportDocument,type WatchGroup} from "../api/contract";
export type ImportPreview={groupCount:number;itemCount:number};
export const toGroupImportDocument=(groups:readonly WatchGroup[]):GroupImportDocument=>({schemaVersion:1,groups:groups.map(({name,description,intervalMs,items})=>({name,description,intervalMs,items:[...items]}))});
export function parseGroupImportDocument(value:unknown):ApiResult<GroupImportDocument>{try{return{ok:true,data:groupImportGuard(value)};}catch{return{ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import document is invalid"};}}
export const previewGroupImport=(document:GroupImportDocument,current:readonly WatchGroup[]):ImportPreview=>{void current;return{groupCount:document.groups.length,itemCount:document.groups.reduce((count,group)=>count+group.items.length,0)}};
