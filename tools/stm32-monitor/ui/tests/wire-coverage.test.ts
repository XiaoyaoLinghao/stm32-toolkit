import {describe,expect,it} from "vitest";
import {IntegerToken,encodeJson,i64,parseLossless} from "../src/api/wire";

describe("parseLossless",()=>{
  it("handles backslash and quote escapes inside strings",()=>{
    expect(parseLossless('"a\\\\b"')).toBe("a\\b");
    expect(parseLossless('"a\\"b"')).toBe('a"b');
  });
  it("preserves numbers outside strings as IntegerToken when integral",()=>{
    const value=parseLossless('{"n":123,"f":1.5,"neg":-7,"zero":0,"e":1e3}');
    const record=value as Record<string,unknown>;
    expect(record["n"]).toBeInstanceOf(IntegerToken);
    expect(record["f"]).toBe(1.5);
    expect(record["neg"]).toBeInstanceOf(IntegerToken);
    expect(record["zero"]).toBeInstanceOf(IntegerToken);
    expect(record["e"]).toBe(1000);
  });
  it("rejects a number-like token that is not a valid integer by leaving it as raw JSON",()=>{
    expect(parseLossless('"__stm32_i64__-x"')).toBe("__stm32_i64__-x");
  });
  it("avoids sentinel collision by extending the marker when the text already contains it",()=>{
    const value=parseLossless('{"s":"__stm32_i64__","v":5}');
    const record=value as Record<string,unknown>;
    expect(record["s"]).toBe("__stm32_i64__");
    expect(record["v"]).toBeInstanceOf(IntegerToken);
  });
});

describe("i64",()=>{
  it("converts a valid IntegerToken",()=>{
    expect(i64(new IntegerToken("42"))).toBe(42n);
    expect(i64(new IntegerToken("-7"))).toBe(-7n);
  });
  it("throws when the value is not an IntegerToken",()=>{
    expect(()=>i64(42)).toThrow("expected integer");
  });
  it("throws when the decimal is not a canonical integer",()=>{
    expect(()=>i64(new IntegerToken("1.5"))).toThrow("expected integer");
    expect(()=>i64(new IntegerToken("01"))).toThrow("expected integer");
  });
  it("throws outside the signed-int64 range on both ends",()=>{
    expect(()=>i64(new IntegerToken("9223372036854775808"))).toThrow("outside signed-int64");
    expect(()=>i64(new IntegerToken("-9223372036854775809"))).toThrow("outside signed-int64");
  });
  it("accepts the signed-int64 extremes",()=>{
    expect(i64(new IntegerToken("9223372036854775807"))).toBe(9223372036854775807n);
    expect(i64(new IntegerToken("-9223372036854775808"))).toBe(-9223372036854775808n);
  });
});

describe("encodeJson",()=>{
  it("encodes primitives",()=>{
    expect(encodeJson(null)).toBe("null");
    expect(encodeJson("x")).toBe('"x"');
    expect(encodeJson(true)).toBe("true");
    expect(encodeJson(42)).toBe("42");
  });
  it("encodes bigint without quotes and never rounds",()=>{
    expect(encodeJson(9223372036854775807n)).toBe("9223372036854775807");
    expect(encodeJson(-9223372036854775808n)).toBe("-9223372036854775808");
  });
  it("encodes arrays and objects recursively, skipping undefined-valued keys",()=>{
    expect(encodeJson([1,2n,"three"])).toBe('[1,2,"three"]');
    expect(encodeJson({a:1,b:undefined,c:2n})).toBe('{"a":1,"c":2}');
  });
  it("throws on non-finite numbers",()=>{
    expect(()=>encodeJson(Number.NaN)).toThrow("non-finite JSON number");
    expect(()=>encodeJson(Number.POSITIVE_INFINITY)).toThrow("non-finite JSON number");
  });
  it("throws on unsupported values",()=>{
    expect(()=>encodeJson(undefined)).toThrow("unsupported JSON value");
    expect(()=>encodeJson(Symbol("s"))).toThrow("unsupported JSON value");
    expect(()=>encodeJson(()=>undefined)).toThrow("unsupported JSON value");
  });
});
