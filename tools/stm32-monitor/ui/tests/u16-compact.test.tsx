import {expect,it,vi} from "vitest";
import {fireEvent,render,screen} from "@testing-library/preact";
import {GroupPanel} from "../src/components/GroupPanel";
import {LiveTable} from "../src/components/LiveTable";
import {watchItemGuard,type GroupDraft,type HistoryPage,type ObservationBinding,type SampleBatch,type WatchGroup} from "../src/api/contract";
import {appendAuthoritativeSample,emptyLive,projectHistoryPage} from "../src/chart/series";
import {watchFullLabel,watchKey,watchLabel} from "../src/state/watch";

const low={kind:"variable" as const,expression:"PC_send2[53]"};
const high={kind:"variable" as const,expression:"PC_send2[54]"};
const combined={kind:"u16le" as const,lowExpression:low.expression,highExpression:high.expression};
const group:WatchGroup={groupId:"group",name:"Group",description:"",intervalMs:250,
  items:[low,high,combined],revision:1n,createdAtUtc:"2026-10-21T00:00:00Z",updatedAtUtc:"2026-10-21T00:00:00Z"};

it("validates the fixed pair, preserves ordered identity and shortens adjacent array labels",()=>{
  expect(watchItemGuard({kind:"u16le",lowExpression:" PC_send2[53] ",highExpression:"PC_send2[54]"})).toEqual(combined);
  expect(watchItemGuard({kind:"u16le",lowExpression:"😀".repeat(512),highExpression:"b"})).toMatchObject({kind:"u16le"});
  expect(()=>watchItemGuard({kind:"u16le",lowExpression:"a\n",highExpression:"b"})).toThrow();
  expect(()=>watchItemGuard({kind:"u16le",lowExpression:"a",highExpression:"b",formula:"a+b"})).toThrow();
  expect(watchKey(combined)).not.toBe(watchKey({kind:"u16le",lowExpression:high.expression,highExpression:low.expression}));
  expect(watchLabel(combined)).toBe("PC_send2[53,54] (16位)");
  expect(watchFullLabel(combined)).toBe("u16(PC_send2[53], PC_send2[54])");
});

it("adds one combination through the existing draft callback and retains its saved label",()=>{
  const onDraftChange=vi.fn();
  const draft:GroupDraft={sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items:[low,high]};
  const props={groups:[group],selectedGroupId:"group",draft,editorGeneration:1n,failure:null,
    onSelect:vi.fn(),onDraftChange,onRemove:vi.fn(),onNew:vi.fn(),onSave:vi.fn(),onDelete:vi.fn(),
    onImport:vi.fn(),onExport:vi.fn()};
  const view=render(<GroupPanel {...props}/>);
  expect(screen.queryByLabelText("低字节")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"合并16位"}));
  expect(screen.getByLabelText("低字节")).toHaveValue(low.expression);
  expect(screen.getByLabelText("高字节")).toHaveValue(high.expression);
  fireEvent.click(screen.getByRole("button",{name:"添加组合"}));
  expect(onDraftChange).toHaveBeenCalledWith({...draft,items:[low,high,combined]});
  view.rerender(<GroupPanel {...props} draft={{...draft,items:[low,high,combined]}}/>);
  expect(screen.getByText("PC_send2[53,54] (16位)")).toHaveAttribute("title",watchFullLabel(combined));
  expect(screen.getByRole("button",{name:"添加组合"})).toBeDisabled();
  view.rerender(<GroupPanel {...props} editorGeneration={2n} draft={{...draft,items:[low,high,combined]}}/>);
  expect(screen.queryByLabelText("低字节")).toBeNull();
});

it("projects the combined number as a selectable live and history curve and gaps errors",()=>{
  const typed={expression:watchFullLabel(combined),typeName:"uint16_t",value:5312,rawHex:"0x14c0",bitWidth:16};
  const batch:SampleBatch={binding:{} as ObservationBinding,groupId:"group",groupRevision:1n,runId:"run",sequence:0n,
    scheduledUnixNs:100n,capturedUnixNs:200n,scheduledAtUtc:"2026-10-21T00:00:00Z",capturedAtUtc:"2026-10-21T00:00:00Z",
    latencyNs:100n,actualRateHz:4,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,
    values:[{watch:low,status:"OK",typedValue:{expression:low.expression,typeName:"uint8_t",value:192,rawHex:"0xc0",bitWidth:8},code:null,definition:null},
      {watch:high,status:"OK",typedValue:{expression:high.expression,typeName:"uint8_t",value:20,rawHex:"0x14",bitWidth:8},code:null,definition:null},
      {watch:combined,status:"OK",typedValue:typed,code:null,definition:{kind:"u16le",lowExpression:low.expression,highExpression:high.expression}}]};
  const key=watchKey(combined);
  const live=appendAuthoritativeSample(emptyLive(),batch,group,new Set([key]));
  expect(live.rows.get(key)?.displayValue).toBe("5312");
  expect(live.series.get(key)?.[0]?.value).toBe(5312);
  const toggle=vi.fn();
  render(<LiveTable rows={[live.rows.get(key)!]} selectedSeries={[]} onSeriesToggle={toggle}/>);
  fireEvent.click(screen.getByRole("button",{name:"显示曲线"}));
  expect(toggle).toHaveBeenCalledWith(key);
  const page:HistoryPage={batches:[{...batch,startOrdinal:0n,batchValueCount:3n}],valueCount:3n,nextCursor:null,serializedBytes:1n};
  expect(projectHistoryPage(page,new Map([["group",group]]),new Set([key])).series.get(key)?.[0]?.value).toBe(5312);
  const errorBatch={...batch,sequence:1n,values:[...batch.values.slice(0,2),{watch:combined,status:"ERROR" as const,typedValue:null,code:"MONITOR_DERIVED_INPUT_UNAVAILABLE",definition:null}]};
  const errored=appendAuthoritativeSample(live,errorBatch,group,new Set([key]));
  expect(errored.series.get(key)?.[1]?.value).toBeNull();
  expect(errored.rows.get(key)?.errorCode).toBe("MONITOR_DERIVED_INPUT_UNAVAILABLE");
});
