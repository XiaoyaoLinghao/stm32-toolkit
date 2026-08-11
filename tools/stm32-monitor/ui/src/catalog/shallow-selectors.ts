import type {VariableDescriptor,VariableWatch} from "../api/contract";
export const deriveMember=(descriptor:VariableDescriptor,name:string):VariableWatch|null=>descriptor.memberNames.includes(name)?{kind:"variable",expression:`${descriptor.selector}.${name}`} : null;
export const deriveElement=(descriptor:VariableDescriptor,index:number):VariableWatch|null=>Number.isInteger(index)&&index>=0&&descriptor.elementCount!==null&&BigInt(index)<descriptor.elementCount?{kind:"variable",expression:`${descriptor.selector}[${index}]`}:null;
