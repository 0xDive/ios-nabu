#!/usr/bin/env python3
"""Offline-only Apple Device Tree draft generator for Xiaomi Pad 5 / SM8150.

The generated ADT is incomplete: it cannot boot XNU or iOS.
Never upload the input DTB or generated device-specific report.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import struct
from dtb_inspect import parse_dtb, parse_ranges, strings
from adt_format import u32, u64, cstr, make_node, pack, unpack

BASE = 0x100000000
SIZE = 0xF0000000
SOC_BASE = 0x01000000


def be32(raw: bytes, field_name: str) -> int:
    if len(raw) != 4:
        raise ValueError(f"{field_name}: expected four bytes")
    return int.from_bytes(raw, "big")


def regs_1_1(node, prop="reg"):
    raw = node.props.get(prop, b"")
    if not raw or len(raw) % 8:
        raise ValueError(f"Unexpected 1/1 reg format: {node.name}")
    return [struct.unpack_from(">II", raw, off) for off in range(0, len(raw), 8)]


def overlap(a, b, c, d):
    return a < d and c < b


def check_dtb(fdt):
    model = strings(fdt.props.get("model"))
    compatible = strings(fdt.props.get("compatible"))
    if "nabu" not in " ".join(model+compatible).lower() or "qcom,sm8150" not in compatible:
        raise ValueError("Not a Xiaomi Pad 5 / SM8150 FDT")
    psci = fdt.get("/psci")
    if (psci is None or strings(psci.props.get("method")) != ["smc"] or
            "arm,psci-1.0" not in strings(psci.props.get("compatible"))):
        raise ValueError("Need PSCI 1.0 / smc in Linux FDT")
    memory = fdt.get("/memory")
    if memory is None:
        raise ValueError("Missing memory node")
    banks = parse_ranges(memory.props.get("reg"), 2, 2)
    if not any(int(b["address"],16) <= BASE and int(b["end_exclusive"],16) >= BASE+SIZE for b in banks):
        raise ValueError("High-memory draft outside advertised DRAM")
    reserved = fdt.get("/reserved-memory")
    fixed, dynamic = [], []
    if reserved:
        for child in reserved.children:
            for bank in parse_ranges(child.props.get("reg"), 2, 2):
                lo, hi = int(bank["address"],16), int(bank["end_exclusive"],16)
                if overlap(BASE, BASE+SIZE, lo, hi):
                    fixed.append((child.name, lo, hi))
            if "size" in child.props and "reg" not in child.props:
                ranges = child.props.get("alloc-ranges")
                if ranges:
                    if any(overlap(BASE, BASE+SIZE, int(r["address"],16),
                                   int(r["end_exclusive"],16))
                           for r in parse_ranges(ranges,2,2)):
                        dynamic.append(child.name)
                else:
                    dynamic.append(child.name)
    if fixed or dynamic:
        raise ValueError(f"Memory draft intersects reservations: {fixed}; dynamic: {dynamic}")
    cpu_node = fdt.get("/cpus")
    if cpu_node is None:
        raise ValueError("Missing CPU nodes")
    cpu_regs = []
    for child in cpu_node.children:
        if child.name.startswith("cpu@"):
            raw = child.props.get("reg", b"")
            if len(raw) != 8:
                raise ValueError("Invalid CPU MPIDR encoding")
            cpu_regs.append((int.from_bytes(raw,"big"),child))
    cpu_regs.sort(key=lambda v:v[0])
    if len(cpu_regs) != 8 or len({v for v,_ in cpu_regs}) != 8:
        raise ValueError("Expected eight unique MPIDRs")
    intr = fdt.get("/soc/interrupt-controller@17a00000")
    if intr is None or "arm,gic-v3" not in strings(intr.props.get("compatible")):
        raise ValueError("Missing GICv3")
    gic = regs_1_1(intr)
    if len(gic) < 2 or gic[0][0] < SOC_BASE or gic[1][0] < SOC_BASE:
        raise ValueError("Unexpected GIC registers")
    timer = fdt.get("/soc/timer")
    if timer is None or "arm,armv8-timer" not in strings(timer.props.get("compatible")):
        raise ValueError("Missing ARM timer")
    frequency = be32(timer.props.get("clock-frequency",b""),"timer frequency")
    interrupts = timer.props.get("interrupts",b"")
    if len(interrupts) % 12:
        raise ValueError("Invalid timer interrupt array")
    specs = [struct.unpack_from(">III", interrupts, off) for off in range(0,len(interrupts),12)]
    vtimer = next((16+num for typ,num,flags in specs if typ == 1 and num == 3),None)
    if vtimer is None:
        raise ValueError("Missing ARM virtual timer PPI 3")
    ufs = fdt.get("/soc/ufshc@1d84000")
    if ufs is None or "qcom,ufshc" not in strings(ufs.props.get("compatible")):
        raise ValueError("Missing UFS controller")
    ufsregs = regs_1_1(ufs)
    if not ufsregs or ufsregs[0][0] != 0x1D84000:
        raise ValueError("Unexpected UFS base")
    splash = fdt.get("/reserved-memory/cont_splash_region")
    splash_regs = parse_ranges(splash.props.get("reg"),2,2) if splash else []
    return {
        "model":model, "compatible":compatible,
        "cpu_mpidr":[v for v,_ in cpu_regs],
        "gic":{"distributor_pa":gic[0][0], "distributor_size":gic[0][1],
               "redistributor_pa":gic[1][0], "redistributor_size":gic[1][1]},
        "timer_frequency_hz":frequency,"vtimer_intid":vtimer,
        "ufs":{"controller_pa":ufsregs[0][0],"controller_size":ufsregs[0][1]},
        "splash_reservation":splash_regs,
        "dram_candidate":{"base":BASE,"size":SIZE,"end_exclusive":BASE+SIZE,
                          "runtime_proven_free":False},
        "boundaries":{"static_reserved_overlap":False,
                      "dynamic_reserved_overlap_per_fdt":False}
    }


def make_adt(info):
    handles = iter(range(1,1000))
    def handle():
        return {"AAPL,phandle":u32(next(handles))}
    chosen = make_node("chosen",dict(handle(),**{
        "dram-base":u64(BASE),
        "dram-size":u64(SIZE),
        "debug-enabled":u32(1),
        "firmware-version":cstr("nabu-stage4-offline")
    }),[make_node("memory-map",handle())])
    cpus = []
    for i,mpidr in enumerate(info["cpu_mpidr"]):
        props = dict(handle(),**{
            "device_type":cstr("cpu"),
            "compatible":cstr("qcom,kryo485")+cstr("qcom,sm8150")+cstr("ARM,v8"),
            "reg":u32(mpidr),
            "cpu-id":u32(i),
            "cluster-id":u32(0),
            "cluster-type":u32(0),
            "die-cluster-id":u32(0),
            "cluster-core-id":u32(i),
            "state":cstr("running" if i == 0 else "stopped"),
            "timebase-frequency":u32(info["timer_frequency_hz"]),
            "fixed-frequency":u32(info["timer_frequency_hz"])
        })
        cpus.append(make_node(f"cpu{i}",props))
    gic=info["gic"]
    gic_node=make_node("gic",dict(handle(),**{
        "compatible":cstr("arm,gic-v3"),
        "interrupt-controller":b"",
        "virtual-timer-intid":u32(info["vtimer_intid"]),
        "reg":u64(gic["distributor_pa"]-SOC_BASE,gic["distributor_size"],
                  gic["redistributor_pa"]-SOC_BASE,gic["redistributor_size"])
    }))
    arm_io=make_node("arm-io",dict(handle(),**{
        "device_type":cstr("nabu-io"),
        "compatible":cstr("nabu-io")+cstr("arm-io"),
        "#address-cells":u32(2),
        "#size-cells":u32(2),
        "ranges":u64(0,SOC_BASE,0x100000000-SOC_BASE)
    }),[gic_node])
    ufs=info["ufs"]
    ufs_node=make_node("nabu-ufs",dict(handle(),**{
        "compatible":cstr("qcom,ufshc"),
        "reg":u64(ufs["controller_pa"],ufs["controller_size"])
    }))
    return make_node("device-tree",dict(handle(),**{
        "compatible":cstr("xiaomi,nabu")+cstr("qcom,sm8150")+cstr("AppleARM"),
        "model":cstr("NABU"),
        "#address-cells":u32(2),"#size-cells":u32(2)
    }),[chosen,make_node("defaults",handle()),
        make_node("cpus",dict(handle(),**{"#address-cells":u32(1),"#size-cells":u32(0)}),cpus),
        arm_io,ufs_node])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dtb",type=pathlib.Path,required=True)
    p.add_argument("--out",type=pathlib.Path,default=pathlib.Path("out/nabu-draft.adt"))
    p.add_argument("--report",type=pathlib.Path,default=pathlib.Path("out/nabu-hw-plan.json"))
    args=p.parse_args()
    try:
        raw=args.dtb.read_bytes()
        info=check_dtb(parse_dtb(raw))
        adt=pack(make_adt(info))
        assert unpack(adt).child("arm-io").child("gic") is not None
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_bytes(adt)
        report={
            "schema":"ios-nabu-stage4-hardware-plan-v1",
            "source_dtb_sha256":hashlib.sha256(raw).hexdigest(),
            "adt_sha256":hashlib.sha256(adt).hexdigest(),
            "adt_bytes":len(adt),
            "status":"OFFLINE PROTOTYPE ONLY; NOT BOOTABLE OR TESTED BY XNU",
            "hardware":info,
            "blockers":["No nabu-specific XNU Mach-O or PlatformExpert",
                        "No ABL-time proven memory placement",
                        "Apple product/iOS service device tree unavailable",
                        "No verified frame buffer or touch driver",
                        "Missing XNU drivers and independent logging"]
        }
        args.report.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("Draft ADT:",args.out,len(adt),"bytes")
        print("Report:",args.report)
        print("NO boot image and NO firmware operations")
    except (OSError,ValueError,AssertionError,struct.error) as exc:
        p.exit(1,"ERROR: "+str(exc)+"\n")

if __name__ == "__main__":
    main()
