import type {JSX} from "preact";
import type {DropTotals} from "../state/model";
import {copy,latencyText} from "../presentation/zh";

export type StatusStripProps={
  actualRateHz:number;
  latencyNs:bigint;
  drops:DropTotals;
};

export function StatusStrip({actualRateHz,latencyNs,drops}:StatusStripProps):JSX.Element{
  const hasDrops=Object.values(drops).some(value=>value>0n);
  return<footer className={`status-strip ${hasDrops?"has-drops":""}`} aria-label={copy.statusSummary}>
    <span>{copy.actualRate} <output>{actualRateHz.toFixed(2)} Hz</output></span>
    <span>{copy.latency} <output>{latencyText(latencyNs)}</output><details><summary>{copy.rawNs}</summary><code>{latencyNs.toString()} ns</code></details></span>
    <span>{copy.dropsSubscriber} <output>{drops.subscriber.toString()}</output> · {copy.dropsHistory} <output>{drops.history.toString()}</output> · {copy.dropsDeadline} <output>{drops.deadline.toString()}</output> · {copy.dropsService} <output>{drops.service.toString()}</output></span>
  </footer>;
}
