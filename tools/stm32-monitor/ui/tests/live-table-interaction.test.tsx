import {expect,it,vi} from "vitest";
import {render,screen} from "@testing-library/preact";
import userEvent from "@testing-library/user-event";
import {LiveTable} from "../src/components/LiveTable";

it("labels each curve button with its next action while reducer selection remains authoritative",async()=>{
  const toggle=vi.fn();
  const row={watch:{kind:"variable" as const,expression:"counter"},displayValue:"42",rawHex:null,
    typeName:"int",capturedAtUtc:"",trend:"up" as const,errorCode:null,numericValue:42};
  const view=render(<LiveTable rows={[row]} selectedSeries={[]} onSeriesToggle={toggle}/>);
  const show=screen.getByRole("button",{name:"显示曲线"});
  expect(show).toHaveAttribute("aria-pressed","false");
  await userEvent.click(show);
  expect(toggle).toHaveBeenCalledExactlyOnceWith("variable:counter");

  view.rerender(<LiveTable rows={[row]} selectedSeries={["variable:counter"]} onSeriesToggle={toggle}/>);
  const hide=screen.getByRole("button",{name:"隐藏曲线"});
  expect(hide).toHaveAttribute("aria-pressed","true");
  await userEvent.click(hide);
  expect(toggle).toHaveBeenCalledTimes(2);
  expect(toggle).toHaveBeenLastCalledWith("variable:counter");

  view.rerender(<LiveTable rows={[row]} selectedSeries={[]} onSeriesToggle={toggle}/>);
  expect(screen.getByRole("button",{name:"显示曲线"})).toHaveAttribute("aria-pressed","false");
});
