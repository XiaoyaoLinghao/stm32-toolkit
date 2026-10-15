import type {JSX} from "preact";
import type {SamplingStatus} from "../api/contract";
import type {MonitorState} from "../state/model";
import {copy,samplingState} from "../presentation/zh";

export function TransportStatus(p:{sampling:SamplingStatus["state"];phase:MonitorState["transport"]["phase"];stale:boolean}):JSX.Element{
  const phase=p.phase==="open"?copy.streamConnected:p.phase==="checking"?copy.streamChecking
    :p.phase==="connecting"||p.phase==="idle"?copy.streamConnecting:copy.streamLost;
  return<>
    <span>{copy.samplingServerLabel}{samplingState(p.sampling)}</span>
    <span className={p.phase==="disconnected"?"stream-warning":"stream-connecting"} role="status">{phase}</span>
    {p.stale&&<span className="stream-warning">{copy.streamStale}</span>}
  </>;
}
