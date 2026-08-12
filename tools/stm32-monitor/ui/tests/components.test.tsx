import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {IdentityBar} from "../src/components/IdentityBar";
import {ProbePanel} from "../src/components/ProbePanel";
import {GroupPanel} from "../src/components/GroupPanel";
import {LiveTable} from "../src/components/LiveTable";
import {StatusStrip} from "../src/components/StatusStrip";
import {NoticeRegion} from "../src/components/NoticeRegion";
import {ChartZoomControls} from "../src/components/ChartZoomControls";
import {HistoryPanel} from "../src/components/HistoryPanel";
import {ExportPanel} from "../src/components/ExportPanel";
import type {ProjectStatus,FirmwareStatus,WatchGroup,WatchItem} from "../src/api/contract";

const project:ProjectStatus={logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"};
const firmware:FirmwareStatus={buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"i".repeat(64),gitHead:"g".repeat(40),gitDirty:false,targetDevice:"STM32F407VG"};
const group:WatchGroup={groupId:"group",name:"Group",description:"",intervalMs:250,items:[{kind:"variable",expression:"counter"}],revision:1n,createdAtUtc:"2026-08-10T00:00:00Z",updatedAtUtc:"2026-08-10T00:00:00Z"};
const historyQuery={startNs:0n,endNs:1000000000n};

it("IdentityBar renders project and firmware and copies identity",async()=>{
  const copy=vi.fn();
  render(<IdentityBar project={project} firmware={firmware} onCopy={copy}/>);
  expect(screen.getByText("Project")).toBeTruthy();
  expect(screen.getByText("STM32F407VG")).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"Copy workspace identity"}));
  expect(copy).toHaveBeenCalled();
});

it("IdentityBar shows no-firmware state",()=>{
  render(<IdentityBar project={project} firmware={null} onCopy={vi.fn()}/>);
  expect(screen.getByText("No verified firmware identity.")).toBeTruthy();
});

it("ProbePanel lists probes and connects",async()=>{
  const connect=vi.fn();
  render(<ProbePanel probes={[{probeId:"p1",vendor:"ST",product:"ST-Link",boardName:null}]}
    connectedProbeId={null} canReconnect={false} leaseReason={null}
    onRefresh={vi.fn()} onConnect={connect} onReconnect={vi.fn()} onRelease={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button",{name:"Connect"}));
  expect(connect).toHaveBeenCalledWith("p1");
});

it("GroupPanel renders draft items and save button is disabled when empty",()=>{
  render(<GroupPanel groups={[group]} selectedGroupId="group"
    draft={{sourceGroupId:"group",expectedRevision:1n,name:"Group",description:"",intervalMs:250,items:[]}}
    failure={null} onSelect={vi.fn()} onDraftChange={vi.fn()} onRemove={vi.fn()}
    onNew={vi.fn()} onSave={vi.fn()} onDelete={vi.fn()}
    onImport={vi.fn()} onExport={vi.fn()}/>);
  expect(screen.getByRole("button",{name:"Group (1)"})).toBeTruthy();
  expect(screen.getByRole("button",{name:"Save group"})).toBeDisabled();
});

it("LiveTable renders rows and toggles series",async()=>{
  const toggle=vi.fn();
  const watch:WatchItem={kind:"variable",expression:"counter"};
  render(<LiveTable rows={[{watch,displayValue:"42",rawHex:null,typeName:"int",capturedAtUtc:"",trend:"up",errorCode:null,numericValue:42}]}
    selectedSeries={[]} onSeriesToggle={toggle}/>);
  expect(screen.getByText("42")).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"Off"}));
  expect(toggle).toHaveBeenCalledWith("variable:counter");
});

it("StatusStrip renders rate, latency and drops",()=>{
  render(<StatusStrip actualRateHz={10} latencyNs={2500000n}
    drops={{subscriber:1n,history:2n,deadline:3n,service:4n}}/>);
  expect(screen.getByText(/Rate:/)).toBeTruthy();
  expect(screen.getByText("10.00 Hz")).toBeTruthy();
  expect(screen.getByText("2500000 ns")).toBeTruthy();
});

it("NoticeRegion renders notices",()=>{
  render(<NoticeRegion notices={[{id:"1",kind:"view-reset",text:"View reset"}]}/>);
  expect(screen.getByText("View reset: View reset")).toBeTruthy();
});

it("ChartZoomControls fires zoom actions",async()=>{
  const onAction=vi.fn();
  render(<ChartZoomControls range={{start:0,end:100}} onAction={onAction}/>);
  await userEvent.click(screen.getByRole("button",{name:"Zoom in"}));
  expect(onAction).toHaveBeenCalledWith({type:"zoom.in"});
});

it("HistoryPanel loads edited bounds once and pages",async()=>{
  const load=vi.fn(),page=vi.fn();
  render(<HistoryPanel query={historyQuery} page={null} failure={null} onLoad={load} onPage={page}/>);
  await userEvent.click(screen.getByRole("button",{name:"Load history"}));
  expect(load).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("button",{name:"Next history page"})).toBeDisabled();
});

it("ExportPanel confirms creation after dialog",async()=>{
  const create=vi.fn();
  render(<ExportPanel range={{startNs:0n,endNs:3000000000n}} artifact={null} failure={null}
    onCreate={create} onRefresh={vi.fn()} onDownload={vi.fn()}/>);
  await userEvent.click(screen.getByRole("button",{name:"Create CSV export"}));
  expect(create).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Confirm export"}));
  expect(create).toHaveBeenCalledWith({startNs:0n,endNs:3000000000n,format:"csv",authorized:true});
});

it("ExportPanel renders verified artifact and downloads",async()=>{
  const download=vi.fn();
  render(<ExportPanel range={{startNs:0n,endNs:1000n}}
    artifact={{exportId:"e1",format:"csv",sha256:"a".repeat(64),bytes:123n,valueCount:4n}} failure={null}
    onCreate={vi.fn()} onRefresh={vi.fn()} onDownload={download}/>);
  expect(screen.getByText("123 bytes · 4 values")).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"Download verified CSV"}));
  expect(download).toHaveBeenCalledWith("e1");
});
