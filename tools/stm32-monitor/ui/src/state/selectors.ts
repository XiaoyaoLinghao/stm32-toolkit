import type {WatchGroup} from "../api/contract";
import {emptyRow,watchKey,type LiveRow} from "../chart/series";
import type {DisplaySeries,MonitorState} from "./model";
export const selectedGroup=(state:MonitorState):WatchGroup|null=>state.selectedGroupId===null?null:state.groups.find(group=>group.groupId===state.selectedGroupId)??null;
export const liveRows=(state:MonitorState):readonly LiveRow[]=>{const group=selectedGroup(state);return group===null?[]:group.items.map(watch=>state.live.rows.get(watchKey(watch))??emptyRow(watch));};
export const chartSeries=(state:MonitorState):readonly DisplaySeries[]=>[...state.selectedSeries].slice(0,8).map(key=>({key,label:key,points:state.live.series.get(key)??[]}));
