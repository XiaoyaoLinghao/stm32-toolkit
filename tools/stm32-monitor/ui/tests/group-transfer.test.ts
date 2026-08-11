import {expect,it} from "vitest";
import {IntegerToken} from "../src/api/wire";
import type {WatchGroup} from "../src/api/contract";
import {parseGroupImportDocument,previewGroupImport,toGroupImportDocument} from "../src/state/group-transfer";

const group:WatchGroup={groupId:"id",name:"Straße",description:"d",intervalMs:250,items:[{kind:"variable",expression:"x"},{kind:"register",registerPath:"RCC.CSR"}],revision:9223372036854775807n,createdAtUtc:"created",updatedAtUtc:"updated"};
it("exports precisely transfer schema fields and preserves item order",()=>{
  const document=toGroupImportDocument([group]);
  expect(document).toEqual({schemaVersion:1,groups:[{name:"Straße",description:"d",intervalMs:250,items:group.items}]});
  expect(JSON.stringify(document)).not.toMatch(/groupId|revision|createdAtUtc|updatedAtUtc/);
});
it("uses the frozen import guard and does not guess Unicode/case conflicts",()=>{
  const parsed=parseGroupImportDocument({schemaVersion:new IntegerToken("1"),groups:[{name:"STRASSE",description:"",intervalMs:new IntegerToken("250"),items:[]}]});
  expect(parsed).toEqual({ok:true,data:{schemaVersion:1,groups:[{name:"STRASSE",description:"",intervalMs:250,items:[]}]}});
  if(parsed.ok)expect(previewGroupImport(parsed.data,[group])).toEqual({groupCount:1,itemCount:0});
  expect(parseGroupImportDocument({schemaVersion:new IntegerToken("2"),groups:[]})).toEqual({ok:false,code:"MONITOR_IMPORT_INVALID",message:"Group import document is invalid"});
});
