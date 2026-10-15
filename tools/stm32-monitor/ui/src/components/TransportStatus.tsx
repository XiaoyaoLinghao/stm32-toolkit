import type {JSX} from "preact";
import type {SamplingStatus} from "../api/contract";
import {copy,samplingState} from "../presentation/zh";

export function TransportStatus(p:{sampling:SamplingStatus["state"];open:boolean;stale:boolean}):JSX.Element{
  return<>
    <span>{copy.samplingServerLabel}{samplingState(p.sampling)}</span>
    {p.stale?<span className="stream-warning" role="status">{copy.streamLost}</span>
      :!p.open?<span className="stream-connecting" role="status">{copy.streamConnecting}</span>:null}
  </>;
}
