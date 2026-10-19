#!/usr/bin/env python3
"""Read-only 64-bit ARM Mach-O kernel format / segment inspection.

Does not decrypt, patch, execute or load Mach-O. This is NOT an XNU port.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import struct

MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
LC_SEGMENT_64 = 0x19
LC_UNIXTHREAD = 0x5
LC_DYLD_CHAINED_FIXUPS = 0x80000034


def inspect(raw: bytes) -> dict:
    if len(raw) < 32:
        raise ValueError('File too small for Mach-O header')
    magic,cpu,subtype,filetype,ncmds,sizeofcmds,flags,reserved=struct.unpack_from('<8I',raw)
    if magic != MAGIC_64:
        raise ValueError('Not a raw 64-bit little-endian Mach-O (not kernelcache IMG4)')
    if cpu != CPU_TYPE_ARM64:
        raise ValueError(f'Unexpected cputype 0x{cpu:08X}; expected ARM64')
    if ncmds < 1 or ncmds > 4096 or sizeofcmds > len(raw)-32:
        raise ValueError('Unreasonable load command count or size')
    commands_end = 32+sizeofcmds
    offset=32
    segments=[]
    entry=None
    chained_fixups=None
    for n in range(ncmds):
        if offset+8 > commands_end:
            raise ValueError('Load command header outside load commands')
        cmd,cmdsize=struct.unpack_from('<II',raw,offset)
        if cmdsize < 8 or cmdsize&7 or offset+cmdsize > commands_end:
            raise ValueError(f'Invalid command size in command {n}')
        if cmd == LC_SEGMENT_64:
            if cmdsize < 72:
                raise ValueError('Short LC_SEGMENT_64')
            name=raw[offset+8:offset+24].split(b'\0',1)[0].decode('ascii','replace')
            vmaddr,vmsize,fileoff,filesize=struct.unpack_from('<QQQQ',raw,offset+24)
            if filesize > vmsize:
                raise ValueError(f'{name}: file size larger than VM size')
            if filesize and (fileoff > len(raw) or filesize > len(raw)-fileoff):
                raise ValueError(f'{name}: data outside Mach-O')
            if vmaddr+vmsize > 1<<64:
                raise ValueError(f'{name}: VM address overflow')
            segments.append({'name':name,'vmaddr':f'0x{vmaddr:016X}',
                             'vmsize':vmsize,'fileoff':fileoff,'filesize':filesize})
        if cmd == LC_UNIXTHREAD:
            if cmdsize < 16+33*8:
                raise ValueError('Short LC_UNIXTHREAD / ARM_THREAD_STATE64')
            flavor,count=struct.unpack_from('<II',raw,offset+8)
            entry,=struct.unpack_from('<Q',raw,offset+16+32*8)
        if cmd == LC_DYLD_CHAINED_FIXUPS:
            if cmdsize < 16:
                raise ValueError('Short LC_DYLD_CHAINED_FIXUPS')
            dataoff,datasize=struct.unpack_from('<II',raw,offset+8)
            if dataoff > len(raw) or datasize > len(raw)-dataoff:
                raise ValueError('Chained fixups out of bounds')
            chained_fixups={'dataoff':dataoff,'datasize':datasize}
        offset+=cmdsize
    if offset != commands_end:
        raise ValueError('Load command size mismatch')
    if not segments:
        raise ValueError('Mach-O has no LC_SEGMENT_64')
    active=sorted(((int(s['vmaddr'],16),int(s['vmaddr'],16)+s['vmsize'],s['name'])
                   for s in segments if s['vmsize']), key=lambda x:x[0])
    for a,b in zip(active,active[1:]):
        if a[1]>b[0]:
            raise ValueError(f'Overlapping VM regions: {a[2]} / {b[2]}')
    entry_in_segment=entry is not None and any(a<=entry<b for a,b,_ in active)
    return {
        'format':'Mach-O 64-bit ARM64',
        'cpu_subtype':f'0x{subtype:08X}',
        'filetype':f'0x{filetype:08X}',
        'file_bytes':len(raw),
        'ncmds':ncmds,
        'segments':segments,
        'entry_va':f'0x{entry:016X}' if entry is not None else None,
        'entry_in_segment':entry_in_segment,
        'chained_fixups':chained_fixups,
        'limitations':['Structure only, not proof of nabu CPU/MMU boot ABI',
                       'Sweet-specific XNU remains SM7150 until patched for SM8150',
                       'Chained fixups not applied',
                       'No XNU execution or iOS installation has occurred']
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kernel',type=Path)
    p.add_argument('--out',type=Path,default=Path('out/macho-report.json'))
    args=p.parse_args()
    try:
        result=inspect(args.kernel.read_bytes())
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print('Kernel inspected:',args.kernel)
        print('ARM64 segments:',len(result['segments']))
        print('Entry VA:',result['entry_va'],'within segment:',result['entry_in_segment'])
        print('Chained fixups:',bool(result['chained_fixups']))
        print('Report:',args.out)
        if not result['entry_in_segment']:
            raise ValueError('Kernel entry VA missing or not in a VM segment')
    except (OSError,ValueError,struct.error) as exc:
        p.exit(1,'ERROR: '+str(exc)+'\n')

if __name__ == '__main__':
    main()
