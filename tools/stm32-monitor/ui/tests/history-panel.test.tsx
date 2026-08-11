import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {HistoryPanel,flattenHistory,historyInput,inputNs,historyQueryKey} from "../src/components/HistoryPanel";

const query={startNs:0n,endNs:3000000000n};
const page={
  batches:[{binding:{workspaceId:"w",logicalProjectId:"p",sessionId:"s",probeId:"pr",targetDevice:"T",physicalTarget:"T",buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"i".repeat(64),gitHead:"g".repeat(40),gitDirty:false,flashSessionId:"f",leaseId:"l",dwarfSha256:"d".repeat(64),svdSha256:null},
    groupId:"g",groupRevision:1n,runId:"r",sequence:1n,startOrdinal:0n,batchValueCount:1n,scheduledUnixNs:0n,scheduledAtUtc:"2026-08-10T00:00:00Z",capturedUnixNs:0n,capturedAtUtc:"2026-08-10T00:00:00Z",latencyNs:1n,actualRateHz:1,subscriberDrops:0n,historyDrops:0n,deadlineDrops:0n,serviceDrops:0n,
    values:[{watch:{kind:"variable",expression:"counter"},status:"OK",typedValue:{value:5},code:null,definition:null}]}],
  valueCount:1n,nextCursor:"cursor-2",serializedBytes:1n,
};

it("flattens history batches into rows",()=>{
  const rows=flattenHistory(page);
  expect(rows.length).toBe(1);
  expect(rows[0]?.valueOrdinal).toBe(0n);
  expect(rows[0]?.value.status).toBe("OK");
});

it("historyInput and inputNs round-trip nanoseconds",()=>{
  expect(inputNs(historyInput(3000000000n))).toBe(3000000000n);
  expect(inputNs("not-a-date")).toBeNull();
  expect(historyQueryKey({startNs:1n,endNs:2n,runId:"r",groupId:"g",selectorKind:"variable",selector:"counter"}))
    .toBe("1|2|r|g|variable|counter");
});

it("loads edited bounds once",async()=>{
  const load=vi.fn();
  render(<HistoryPanel query={query} page={null} failure={null} onLoad={load} onPage={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button",{name:"Load history"}));
  expect(load).toHaveBeenCalledTimes(1);
});

it("pages next and previous with visited cursor stack",async()=>{
  const load=vi.fn(),pageFn=vi.fn();
  render(<HistoryPanel query={query} page={page} failure={null} onLoad={load} onPage={pageFn}/>);
  expect(screen.getByRole("button",{name:"Previous history page"})).toBeDisabled();
  await userEvent.click(screen.getByRole("button",{name:"Next history page"}));
  expect(pageFn).toHaveBeenCalledWith("cursor-2");
});

it("renders failure alert and keeps inputs",()=>{
  render(<HistoryPanel query={query} page={page} failure={{ok:false,code:"HISTORY_FAILED",message:"query failed"}} onLoad={vi.fn()} onPage={vi.fn()}/>);
  expect(screen.getByRole("alert")).toHaveTextContent("HISTORY_FAILED");
  expect(screen.getByLabelText("History start")).toHaveValue("1970-01-01T00:00");
});

it("renders flattened rows in a table",()=>{
  render(<HistoryPanel query={query} page={page} failure={null} onLoad={vi.fn()} onPage={vi.fn()}/>);
  expect(screen.getByText("counter")).toBeTruthy();
});
