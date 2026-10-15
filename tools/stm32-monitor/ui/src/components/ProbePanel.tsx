import type {JSX} from "preact";
import type {ProbeInfo} from "../api/contract";
import {copy} from "../presentation/zh";

export type ProbePanelProps={
  probes:readonly ProbeInfo[];
  connectedProbeId:string|null;
  canReconnect:boolean;
  leaseReason:string|null;
  busy?:boolean;
  onRefresh:()=>void|Promise<void>;
  onConnect:(probeId:string)=>void|Promise<void>;
  onReconnect:()=>void|Promise<void>;
  onRelease:()=>void|Promise<void>;
};

export function ProbePanel(p:ProbePanelProps):JSX.Element{
  const connected=p.probes.find(probe=>probe.probeId===p.connectedProbeId)??null;
  return<section className="panel" aria-label={copy.probeTitle}>
    <h2>{copy.probeTitle}</h2>
    <button type="button" onClick={()=>void p.onRefresh()}>{copy.probeRefresh}</button>
    {p.probes.length===0
      ?<p>{copy.probeNone}</p>
      :<ul>{p.probes.map(probe=>(
        <li key={probe.probeId}>
          <code>{probe.probeId}</code> {probe.vendor} {probe.product}{probe.boardName?` · ${probe.boardName}`:""}
          {probe.probeId===p.connectedProbeId
            ?<strong>{copy.probeOnline}</strong>
            :<button type="button" disabled={p.busy} onClick={()=>void p.onConnect(probe.probeId)}>{copy.probeConnect}</button>}
        </li>))}</ul>}
    {connected!==null&&(
      <p>{copy.probeConnectedPrefix}<code>{connected.probeId}</code>{p.leaseReason!==null?` · ${p.leaseReason}`:""}</p>
    )}
    <button type="button" disabled={!p.canReconnect||p.busy} onClick={()=>void p.onReconnect()}>{copy.probeReConnect}</button>
    <button type="button" disabled={connected===null||p.busy} onClick={()=>void p.onRelease()}>{copy.probeRelease}</button>
  </section>;
}
