import {expect,it} from "vitest";
import {initialZoom,zoomReducer} from "../src/chart/zoom";
it("clamps a nonzero ordered zoom range and resets it",()=>{
  expect(zoomReducer({start:25,end:75},{type:"zoom.in"})).toEqual({start:35,end:65});
  expect(zoomReducer({start:25,end:75},{type:"zoom.out"})).toEqual({start:15,end:85});
  expect(zoomReducer({start:25,end:75},{type:"zoom.set",start:100,end:0})).toEqual(initialZoom);
  expect(zoomReducer({start:25,end:75},{type:"zoom.reset"})).toEqual(initialZoom);
});
