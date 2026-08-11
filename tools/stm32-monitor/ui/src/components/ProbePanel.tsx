import type {JSX} from "preact";
import type {ProbeInfo} from "../api/contract";

export type ProbePanelProps={
  probes:readonly ProbeInfo[];
  connectedProbeId:string|null;
  canReconnect:boolean;
  leaseReason:string|null;
  onRefresh:()=>void|Promise<void>;
  onConnect:(probeId:string)=>void|Promise<void>;
  onReconnect:()=>void|Promise<void>;
  onRelease:()=>void|Promise<void>;
};

export function ProbePanel(p:ProbePanelProps):JSX.Element{
  const connected=p.probes.find(probe=>probe.probeId===p.connectedProbeId)??null;
  return<section className="panel" aria-label="Probe">
    <h2>Probe</h2>
    <button type="button" onClick={()=>void p.onRefresh()}>Refresh probes</button>
    {p.probes.length===0
      ?<p>No probes detected.</p>
      :<ul>{p.probes.map(probe=>(
        <li key={probe.probeId}>
          <code>{probe.probeId}</code> {probe.vendor} {probe.product}{probe.boardName?` · ${probe.boardName}`:""}
          {probe.probeId===p.connectedProbeId
            ?<strong> (connected)</strong>
            :<button type="button" onClick={()=>void p.onConnect(probe.probeId)}>Connect</button>}
        </li>))}</ul>}
    {connected!==null&&(
      <p>Connected: <code>{connected.probeId}</code>{p.leaseReason!==null?` · ${p.leaseReason}`:""}</p>
    )}
    <button type="button" disabled={!p.canReconnect} onClick={()=>void p.onReconnect()}>Reconnect</button>
    <button type="button" disabled={connected===null} onClick={()=>void p.onRelease()}>Release</button>
  </section>;
}
