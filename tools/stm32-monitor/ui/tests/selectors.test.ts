import {expect,it} from "vitest";
import {initialState,reducer} from "../src/state/reducer";
import {chartSeries,liveRows,selectedGroup} from "../src/state/selectors";
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
