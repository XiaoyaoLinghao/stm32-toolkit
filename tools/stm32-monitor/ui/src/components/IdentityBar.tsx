import type {JSX} from "preact";
import type {FirmwareStatus,ProjectStatus} from "../api/contract";
import {copy} from "../presentation/zh";

export type IdentityBarProps={
  project:ProjectStatus;
  firmware:FirmwareStatus|null;
  onCopy:()=>void|Promise<void>;
};

export function IdentityBar({project,firmware,onCopy}:IdentityBarProps):JSX.Element{
  return<section className="panel" aria-label={copy.identityTitle}>
    <h2>{copy.identityTitle}</h2>
    <p>{project.name}</p>
    <p>{copy.logicalProject}<code>{project.logicalProjectId}</code> · {copy.targetDevice}<code>{project.targetDevice}</code></p>
    {firmware===null
      ?<p>{copy.noFirmware}</p>
      :firmware.gitHead===null
        ?<p>{copy.firmwareBuild}<code>{firmware.buildId}</code> · {copy.elfLabel}<code>{firmware.elfSha256}</code> · {copy.inputSnapshotLabel}<code>{firmware.inputSnapshotSha256}</code> · {copy.gitUnavailable} · {firmware.targetDevice}</p>
        :<p>{copy.firmwareBuild}<code>{firmware.buildId}</code> · {copy.elfLabel}<code>{firmware.elfSha256}</code> · {copy.gitLabel}{firmware.gitDirty?copy.gitDirty:firmware.gitHead} · {firmware.targetDevice}</p>}
    <button type="button" onClick={()=>void onCopy()}>{copy.copyIdentity}</button>
  </section>;
}
