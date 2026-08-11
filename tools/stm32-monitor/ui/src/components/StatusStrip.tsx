import type {JSX} from "preact";
import type {DropTotals} from "../state/model";

export type StatusStripProps={
  actualRateHz:number;
  latencyNs:bigint;
  drops:DropTotals;
};

export function StatusStrip({actualRateHz,latencyNs,drops}:StatusStripProps):JSX.Element{
  return<section className="panel" aria-label="Sampling status">
    <p>Rate: <output>{actualRateHz.toFixed(2)} Hz</output> · Latency: <output>{latencyNs.toString()} ns</output></p>
    <p>Drops — subscriber: <output>{drops.subscriber.toString()}</output>, history: <output>{drops.history.toString()}</output>, deadline: <output>{drops.deadline.toString()}</output>, service: <output>{drops.service.toString()}</output></p>
  </section>;
}
