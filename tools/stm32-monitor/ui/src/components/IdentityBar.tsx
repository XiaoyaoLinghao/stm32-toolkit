import type {JSX} from "preact";
import type {FirmwareStatus,ProjectStatus} from "../api/contract";

export type IdentityBarProps={
  project:ProjectStatus;
  firmware:FirmwareStatus|null;
  onCopy:()=>void|Promise<void>;
};

export function IdentityBar({project,firmware,onCopy}:IdentityBarProps):JSX.Element{
  return<header className="panel">
    <h1>{project.name}</h1>
    <p>Logical project: <code>{project.logicalProjectId}</code> · Target: <code>{project.targetDevice}</code></p>
    {firmware===null
      ?<p>No verified firmware identity.</p>
      :<p>Firmware <code>{firmware.buildId}</code> · ELF <code>{firmware.elfSha256}</code> · Git {firmware.gitDirty?"dirty":firmware.gitHead} · {firmware.targetDevice}</p>}
    <button type="button" onClick={()=>void onCopy()}>Copy workspace identity</button>
  </header>;
}
