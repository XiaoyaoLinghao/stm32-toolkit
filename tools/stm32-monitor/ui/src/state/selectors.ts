import type {WatchGroup} from "../api/contract";
import {emptyRow,watchKey,type LiveRow} from "../chart/series";
import type {DisplaySeries,MonitorState} from "./model";
export const selectedGroup=(state:MonitorState):WatchGroup|null=>state.selectedGroupId===null?null:state.groups.find(group=>group.groupId===state.selectedGroupId)??null;
export const activeGroup=(state:MonitorState):WatchGroup|null=>{
 const sampling=state.status?.sampling;
 return sampling?.runId===null||sampling?.runId===undefined||sampling.groupId===null||sampling.groupRevision===null
  ?null:state.groups.find(group=>group.groupId===sampling.groupId&&group.revision===sampling.groupRevision)??null;
};
export const liveRows=(state:MonitorState):readonly LiveRow[]=>{
 const runId=state.status?.sampling.runId;
 if(runId===null||runId===undefined){
  if(state.live.retained&&state.live.groupId!==null){
   const group=state.groups.find(item=>item.groupId===state.live.groupId&&item.revision===state.live.groupRevision);
   return group===undefined?[]:group.items.map(watch=>state.live.rows.get(watchKey(watch))??emptyRow(watch));
  }
  const group=selectedGroup(state);return group===null?[]:group.items.map(emptyRow);
 }
 const group=activeGroup(state);
 if(state.live.runId!==runId)return group===null?[]:group.items.map(emptyRow);
 return group===null?[...state.live.rows.values()].filter(row=>row.capturedAtUtc!==""):
  group.items.map(watch=>state.live.rows.get(watchKey(watch))??emptyRow(watch));
};
export const chartSeries=(state:MonitorState):readonly DisplaySeries[]=>{
 const visible=state.live.retained?state.status?.sampling.runId===null:
  state.status?.sampling.runId!==null&&state.status?.sampling.runId===state.live.runId;
 return [...state.selectedSeries].slice(0,8).map(key=>({key,label:key,
  points:visible?state.live.series.get(key)??[]:[]}));
};
