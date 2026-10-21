import {expect,it} from "vitest";
import {initialState,reducer} from "../src/state/reducer";
import {chartSeries,liveRows,selectedGroup} from "../src/state/selectors";
import {buildChartOption} from "../src/chart/echarts";
import {watchKey} from "../src/state/watch";
import type {MonitorState,MonitorAction} from "../src/state/model";
import {statusResult,watchGroup} from "./fixtures";

function stateWith(actions:MonitorAction[]):MonitorState{
  return actions.reduce((s,action)=>reducer(s,action),initialState);
}

it("selectedGroup returns the selected group or null",()=>{
  const group=watchGroup();
  const state=stateWith([
    {type:"initial.loaded",status:statusResult(),probes:[],groups:[group]},
    {type:"group.selected",groupId:group.groupId},
  ]);
  expect(selectedGroup(state)?.groupId).toBe("group");
  const none=stateWith([{type:"group.selected",groupId:null}]);
  expect(selectedGroup(none)).toBeNull();
});

it("liveRows maps group items to rows preserving order",()=>{
  const group=watchGroup();
  const state=stateWith([
    {type:"initial.loaded",status:statusResult(),probes:[],groups:[group]},
    {type:"group.selected",groupId:group.groupId},
  ]);
  const rows=liveRows(state);
  expect(rows.length).toBe(1);
  expect(rows[0]?.watch).toEqual({kind:"variable",expression:"counter"});
  expect(rows[0]?.displayValue).toBe("");
});

it("chartSeries returns only selected series up to eight",()=>{
  const group=watchGroup();
  const state=stateWith([
    {type:"initial.loaded",status:statusResult(),probes:[],groups:[group]},
    {type:"series.toggled",key:"variable:counter"},
  ]);
  const series=chartSeries(state);
  expect(series.length).toBe(1);
  expect(series[0]?.key).toBe("variable:counter");
});

it("labels a combined chart series without changing its ordered identity",()=>{
  const watch={kind:"u16le" as const,lowExpression:"PC_send2[53]",highExpression:"PC_send2[54]"};
  const key=watchKey(watch);
  const state=stateWith([{type:"series.toggled",key}]);
  const series=chartSeries(state);
  expect(series).toEqual([{key,label:"PC_send2[53,54] (16位)",points:[]}]);
  const option=buildChartOption(series,{start:0,end:100});
  expect(option.series).toEqual([{id:key,name:"PC_send2[53,54] (16位)",type:"line",
    showSymbol:false,connectNulls:false,data:[]}]);
});
