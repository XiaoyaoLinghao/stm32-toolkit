import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {IdentityBar} from "../src/components/IdentityBar";
import {ProbePanel} from "../src/components/ProbePanel";
import {LiveTable} from "../src/components/LiveTable";
import {NoticeRegion} from "../src/components/NoticeRegion";
import {useDialogFocus} from "../src/components/dialog-focus";
import type {FirmwareStatus,ProbeInfo,ProjectStatus} from "../src/api/contract";

const project:ProjectStatus={logicalProjectId:"project",name:"Project",targetDevice:"STM32F407VG"};
const firmware:FirmwareStatus={buildId:"b".repeat(64),elfSha256:"e".repeat(64),inputSnapshotSha256:"i".repeat(64),gitHead:"g".repeat(40),gitDirty:true,targetDevice:"STM32F407VG"};

it("IdentityBar shows dirty firmware state",()=>{
  render(<IdentityBar project={project} firmware={firmware} onCopy={vi.fn()}/>);
  expect(screen.getByText(/Git dirty/)).toBeTruthy();
});

it("ProbePanel renders a connected probe with a board name and lease reason",async()=>{
  const probes:readonly ProbeInfo[]=[{probeId:"p1",vendor:"ST",product:"ST-Link",boardName:"Nucleo"}];
  const onReconnect=vi.fn(),onRelease=vi.fn();
  render(<ProbePanel probes={probes} connectedProbeId="p1" canReconnect leaseReason="leased"
    onRefresh={vi.fn()} onConnect={vi.fn()} onReconnect={onReconnect} onRelease={onRelease}/>);
  expect(screen.getByText(/Nucleo/)).toBeTruthy();
  expect(screen.getByText(/connected/)).toBeTruthy();
  expect(screen.getByText(/leased/)).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"Reconnect"}));
  expect(onReconnect).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button",{name:"Release"}));
  expect(onRelease).toHaveBeenCalled();
});

it("ProbePanel shows the no-probes message and disables actions",()=>{
  render(<ProbePanel probes={[]} connectedProbeId={null} canReconnect={false} leaseReason={null}
    onRefresh={vi.fn()} onConnect={vi.fn()} onReconnect={vi.fn()} onRelease={vi.fn()}/>);
  expect(screen.getByText("No probes detected.")).toBeTruthy();
  expect(screen.getByRole("button",{name:"Reconnect"})).toBeDisabled();
  expect(screen.getByRole("button",{name:"Release"})).toBeDisabled();
});

it("ProbePanel renders an unconnected probe with a connect button and no lease line",async()=>{
  const probes:readonly ProbeInfo[]=[{probeId:"p1",vendor:"ST",product:"ST-Link",boardName:null}];
  const onConnect=vi.fn();
  render(<ProbePanel probes={probes} connectedProbeId={null} canReconnect={false} leaseReason={null}
    onRefresh={vi.fn()} onConnect={onConnect} onReconnect={vi.fn()} onRelease={vi.fn()}/>);
  expect(screen.queryByText(/Connected:/)).toBeNull();
  await userEvent.click(screen.getByRole("button",{name:"Connect"}));
  expect(onConnect).toHaveBeenCalledWith("p1");
});

it("LiveTable renders an error row and a register row with type dash",async()=>{
  const toggle=vi.fn();
  const errorRow={watch:{kind:"variable" as const,expression:"bad"},displayValue:"",rawHex:null,typeName:null,capturedAtUtc:"",trend:"none" as const,errorCode:"OVERRUN",numericValue:null};
  const registerRow={watch:{kind:"register" as const,registerPath:"RCC.CSR"},displayValue:"0x1",rawHex:"0x1",typeName:null,capturedAtUtc:"",trend:"down" as const,errorCode:null,numericValue:1};
  render(<LiveTable rows={[errorRow,registerRow]} selectedSeries={["variable:bad"]} onSeriesToggle={toggle}/>);
  expect(screen.getByText("OVERRUN")).toBeTruthy();
  expect(screen.getByText("RCC.CSR")).toBeTruthy();
  expect(screen.getAllByText("-")).toHaveLength(2);
  expect(screen.getByRole("button",{name:"On"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button",{name:"On"}));
  expect(toggle).toHaveBeenCalledWith("variable:bad");
});

it("LiveTable shows the empty message when there are no rows",()=>{
  render(<LiveTable rows={[]} selectedSeries={[]} onSeriesToggle={vi.fn()}/>);
  expect(screen.getByText("No watches in the selected group.")).toBeTruthy();
});

it("NoticeRegion renders a non-view-reset notice without a prefix",()=>{
  render(<NoticeRegion notices={[{id:"1",kind:"drop",text:"dropped"}]}/>);
  expect(screen.getByText("dropped")).toBeTruthy();
  expect(screen.queryByText(/View reset:/)).toBeNull();
});

it("useDialogFocus focuses the dialog and cancels on Escape",async()=>{
  const onCancel=vi.fn();
  function Probe(){
    const dialog=useDialogFocus(true,onCancel);
    return(
      <div>
        <button type="button" onClick={event=>dialog.rememberTrigger(event.currentTarget)}>trigger</button>
        <div role="dialog" tabIndex={-1} ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
          <p>dialog</p>
        </div>
      </div>
    );
  }
  render(<Probe/>);
  const dialog=screen.getByRole("dialog");
  expect(document.activeElement).toBe(dialog);
  await userEvent.click(screen.getByRole("button",{name:"trigger"}));
  dialog.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));
  expect(onCancel).toHaveBeenCalled();
});

it("useDialogFocus tolerates Escape when no trigger was remembered",()=>{
  const onCancel=vi.fn();
  function Probe(){
    const dialog=useDialogFocus(true,onCancel);
    return(
      <div>
        <div role="dialog" tabIndex={-1} ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
          <p>dialog</p>
        </div>
      </div>
    );
  }
  render(<Probe/>);
  const dialog=screen.getByRole("dialog");
  dialog.dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}));
  expect(onCancel).toHaveBeenCalled();
});

it("useDialogFocus ignores non-Escape keys",()=>{
  const onCancel=vi.fn();
  function Probe(){
    const dialog=useDialogFocus(true,onCancel);
    return(
      <div>
        <div role="dialog" tabIndex={-1} ref={dialog.dialogRef} onKeyDown={dialog.onDialogKeyDown}>
          <p>dialog</p>
        </div>
      </div>
    );
  }
  render(<Probe/>);
  const dialog=screen.getByRole("dialog");
  dialog.dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));
  expect(onCancel).not.toHaveBeenCalled();
});

it("NoticeRegion renders an empty footer for no notices",()=>{
  render(<NoticeRegion notices={[]}/>);
  expect(screen.getByLabelText("Notices")).toBeTruthy();
});
