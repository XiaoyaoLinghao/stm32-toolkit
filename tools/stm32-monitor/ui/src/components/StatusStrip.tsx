import type {JSX} from "preact";
import type {DropTotals} from "../state/model";
import {copy,latencyText} from "../presentation/zh";

export type StatusStripProps={
  actualRateHz:number;
  latencyNs:bigint;
  lastSampleCapturedAtUtc:string|null;
  fresh:boolean;
  drops:DropTotals;
};

export function StatusStrip({actualRateHz,latencyNs,lastSampleCapturedAtUtc,fresh,drops}:StatusStripProps):JSX.Element{
  const hasDrops=Object.values(drops).some(value=>value>0n);
  const hasSample=lastSampleCapturedAtUtc!==null;
  return<footer className={`status-strip ${hasDrops?"has-drops":""}`} aria-label={copy.statusSummary}>
    <span>{copy.actualRate} <output>{hasSample?`${actualRateHz.toFixed(2)} Hz`:copy.noSampleYet}</output></span>
    <span>{copy.latency} <output>{hasSample?latencyText(latencyNs):copy.noSampleYet}</output>
      {hasSample&&<details><summary>{copy.rawNs}</summary><code>{latencyNs.toString()} ns</code></details>}</span>
    {hasSample&&<span className={fresh?"":"stale-label"}>{fresh?copy.historyCaptured:copy.lastSample}：<time>{lastSampleCapturedAtUtc}</time></span>}
    <span>{copy.dropsSubscriber} <output>{drops.subscriber.toString()}</output> · {copy.dropsHistory} <output>{drops.history.toString()}</output> · {copy.dropsDeadline} <output>{drops.deadline.toString()}</output> · {copy.dropsService} <output>{drops.service.toString()}</output></span>
  </footer>;
}
