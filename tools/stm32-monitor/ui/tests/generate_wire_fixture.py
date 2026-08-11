import argparse
import json
from pathlib import Path
from stm32_monitor.models import SampleValue,WatchItem
from stm32_monitor.protocol import success
from stm32_toolkit.debug.model import DebugFirmwareBinding, MemoryRegionBinding

parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--project",type=Path,required=True);args=parser.parse_args()
binding=DebugFirmwareBinding(logical_project_id="project",workspace_id="workspace",observation_session_id="observe",flash_session_id="flash",lease_id="lease",probe_id="probe",target_device="STM32F407VG",debug_target="cortex_m",build_id="0"*64,elf_sha256="1"*64,elf_size=4096,elf_path="build/fw.elf",input_snapshot_sha256="2"*64,git_head="a"*40,git_dirty=False,confirmed_at_utc="2026-08-10T00:00:00.000000Z",memory_regions=(MemoryRegionBinding("FLASH",0x08000000,0x10000,"rx"),),project_root=args.project.resolve(strict=True))
sample=SampleValue(WatchItem.variable("x"),"OK",typed_value={"vendorShape":[1,{"nested":True}]})
connect_json=json.dumps(success("monitor.probe.connect",binding.to_dict()).to_dict(),ensure_ascii=False,separators=(",",":"))
sample_json=json.dumps(sample.to_dict(),ensure_ascii=False,separators=(",",":"))
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text('{"connect":'+connect_json+',"sample":'+sample_json+'}',"utf-8")
