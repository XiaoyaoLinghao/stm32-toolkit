import {expect,it} from "vitest";
import {initialZoom,zoomReducer} from "../src/chart/zoom";
import {initialState,reducer} from "../src/state/reducer";
it("clamps a nonzero ordered zoom range and resets it",()=>{
  expect(zoomReducer({start:25,end:75},{type:"zoom.in"})).toEqual({start:35,end:65});
  expect(zoomReducer({start:25,end:75},{type:"zoom.out"})).toEqual({start:15,end:85});
  expect(zoomReducer({start:25,end:75},{type:"zoom.set",start:100,end:0})).toEqual({start:25,end:75});
  expect(zoomReducer({start:25,end:75},{type:"zoom.reset"})).toEqual(initialZoom);
});

it("stops at a 1 percent window through repeated toolbar zoom, then expands from its center",()=>{
  let range={...initialZoom};
  for(let index=0;index<10;index++)range=zoomReducer(range,{type:"zoom.in"});
  expect(range).toEqual({start:49.5,end:50.5});
  expect(zoomReducer(range,{type:"zoom.in"})).toBe(range);
  expect(zoomReducer(range,{type:"zoom.out"})).toEqual({start:39.5,end:60.5});
  expect(zoomReducer(initialZoom,{type:"zoom.out"})).toBe(initialZoom);
});

it("normalizes narrow gestures at the edges, rejects invalid values, and preserves equal state identity",()=>{
  const current={start:25,end:75};
  expect(zoomReducer(current,{type:"zoom.set",start:0,end:0.2})).toEqual({start:0,end:1});
  expect(zoomReducer(current,{type:"zoom.set",start:99.8,end:100})).toEqual({start:99,end:100});
  for(const [start,end] of [[80,20],[Number.NaN,80],[0,Number.POSITIVE_INFINITY],[40,40]] as const)
    expect(zoomReducer(current,{type:"zoom.set",start,end})).toBe(current);
  expect(zoomReducer(current,{type:"zoom.set",start:25,end:75})).toBe(current);
});

it("does not publish another reducer state for an unchanged gesture",()=>{
  const zoomed=reducer(initialState,{type:"zoom.changed",action:{type:"zoom.set",start:20,end:80}});
  expect(reducer(zoomed,{type:"zoom.changed",action:{type:"zoom.set",start:20,end:80}})).toBe(zoomed);
});
