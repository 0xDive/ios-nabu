/*
 * Strictly read-only FDT survey. No MMIO, no RAM writes, no allocations.
 * Personal device FDT is not distributed. This is not a free-memory proof.
 */
#include "survey.h"
#define MAGIC 0xd00dfeedU
#define NODE 1U
#define ENDNODE 2U
#define PROP 3U
#define NOP 4U
#define END 9U
#define MAX_DTB 4194304U
#define MAX_TOKENS 120000U
#define MAX_DEPTH 64U
static uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}
static uint64_t be64(const uint8_t *p) { return ((uint64_t)be32(p)<<32)|be32(p+4); }
static int eq(const uint8_t *p, uint32_t len, const char *lit) {
    uint32_t n=0; while(lit[n]) n++;
    if(n+1 > len || p[n]) return 0;
    for(uint32_t i=0;i<n;i++) if(p[i] != (uint8_t)lit[i]) return 0;
    return 1;
}
static int pref(const uint8_t *p,uint32_t len,const char *lit) {
    uint32_t n=0; while(lit[n]) n++;
    if(n>len) return 0;
    for(uint32_t i=0;i<n;i++) if(p[i]!=(uint8_t)lit[i]) return 0;
    return 1;
}
static int overlap(uint64_t a,uint64_t b,uint64_t c,uint64_t d) {
    return a < d && c < b;
}
static uint32_t align4(uint32_t x) { return (x+3U)&~3U; }
static int check_reg(const uint8_t *p,uint32_t n,uint64_t lo,uint64_t hi,
                     uint8_t *collision,uint8_t *contains) {
    if(!n || n%16U) return 0;
    for(uint32_t k=0;k<n;k+=16U) {
        uint64_t start=be64(p+k),size=be64(p+k+8U);
        if(!size || size > UINT64_MAX-start) return 0;
        uint64_t end=start+size;
        if(overlap(lo,hi,start,end) && collision) *collision=1;
        if(start<=lo && end>=hi && contains) *contains=1;
    }
    return 1;
}
struct survey_result survey_fdt(const void *dtb,uint64_t lo,uint64_t hi) {
    struct survey_result r={0};
    if(!dtb || ((uintptr_t)dtb&7U) || hi<=lo) return r;
    const uint8_t *f=(const uint8_t *)dtb;
    if(be32(f)!=MAGIC) return r;
    uint32_t total=be32(f+4U),ss=be32(f+8U),st=be32(f+12U);
    uint32_t rs=be32(f+16U),ns=be32(f+32U),sz=be32(f+36U);
    if(total<64U || total>MAX_DTB || ss<40U || st<40U || rs<40U ||
       ss>total || st>total || rs>total || sz>total-ss || ns>total-st) return r;
    if((uintptr_t)dtb > UINT64_MAX-total) return r;
    r.fdt_self_overlap=(uint8_t)overlap(lo,hi,(uint64_t)(uintptr_t)dtb,
        (uint64_t)(uintptr_t)dtb+total);
    /* Honor the memreserve table as well as /reserved-memory nodes. */
    uint32_t at=rs;
    int terminator=0;
    for(uint32_t i=0;i<1024U;i++) {
        if(at>total || total-at<16U) return r;
        uint64_t start=be64(f+at),size=be64(f+at+8U);
        at+=16U;
        if(!start && !size) {terminator=1;break;}
        if(!size || size>UINT64_MAX-start) return r;
        if(overlap(lo,hi,start,start+size)) r.reserve_table_overlap=1;
        r.reserve_entries++;
    }
    if(!terminator) return r;
    r.reserve_table_valid=1;
    int depth=0,mem_depth=-1,reserved_depth=-1,chosen_depth=-1;
    int child_depth=-1,child_has_reg=0,child_has_size=0,finished=0;
    int root_addr=0,root_size=0,res_addr=0,res_size=0,res_present=0;
    uint8_t seen_start=0,seen_end=0;
    uint64_t initrd_start=0,initrd_end=0;
    const uint8_t *strings=f+st;
    uint32_t pos=ss,end_struct=ss+sz;
    for(uint32_t n=0;n<MAX_TOKENS && pos<=end_struct && end_struct-pos>=4U;n++) {
        uint32_t token=be32(f+pos);pos+=4U;
        if(token==NODE) {
            uint32_t start=pos;
            while(pos<end_struct && f[pos]) pos++;
            if(pos>=end_struct || depth>=(int)MAX_DEPTH) return r;
            uint32_t name_length=pos-start+1U;
            depth++;
            if(depth==2) {
                if(eq(f+start,name_length,"memory") || pref(f+start,name_length,"memory@")) mem_depth=2;
                if(eq(f+start,name_length,"reserved-memory")) { reserved_depth=2;res_present=1; }
                if(eq(f+start,name_length,"chosen")) chosen_depth=2;
            } else if(depth==3 && reserved_depth==2) {
                child_depth=3;child_has_reg=0;child_has_size=0;
            }
            pos=align4(pos+1U);
            if(pos>end_struct) return r;
        } else if(token==ENDNODE) {
            if(depth<=0) return r;
            if(depth==child_depth) {
                if(child_has_size && !child_has_reg) {
                    r.dynamic_nodes++;
                    r.dynamic_unresolved=1;
                }
                child_depth=-1;
            }
            if(depth==mem_depth) mem_depth=-1;
            if(depth==reserved_depth) reserved_depth=-1;
            if(depth==chosen_depth) chosen_depth=-1;
            depth--;
        } else if(token==PROP) {
            if(end_struct-pos<8U) return r;
            uint32_t len=be32(f+pos),nameoff=be32(f+pos+4U);pos+=8U;
            if(len>end_struct-pos || nameoff>=ns) return r;
            uint32_t kn=0;
            while(kn<ns-nameoff && strings[nameoff+kn]) kn++;
            if(kn==ns-nameoff) return r;
            const uint8_t *key=strings+nameoff,*val=f+pos;
            uint32_t key_len=kn+1U;
            if(depth==1 && eq(key,key_len,"#address-cells")) {
                if(len!=4U) return r;
                root_addr=(int)be32(val);
            }
            if(depth==1 && eq(key,key_len,"#size-cells")) {
                if(len!=4U) return r;
                root_size=(int)be32(val);
            }
            if(depth==mem_depth && eq(key,key_len,"reg")) {
                if(!check_reg(val,len,lo,hi,0,&r.candidate_inside_dram)) return r;
            }
            if(depth==reserved_depth && eq(key,key_len,"#address-cells")) {
                if(len!=4U) return r;
                res_addr=(int)be32(val);
            }
            if(depth==reserved_depth && eq(key,key_len,"#size-cells")) {
                if(len!=4U) return r;
                res_size=(int)be32(val);
            }
            if(depth==child_depth && eq(key,key_len,"reg")) {
                child_has_reg=1;
                if(!check_reg(val,len,lo,hi,&r.fixed_overlap,0)) return r;
            }
            if(depth==child_depth && eq(key,key_len,"size")) child_has_size=1;
            if(depth==chosen_depth && (eq(key,key_len,"linux,initrd-start") ||
                                      eq(key,key_len,"linux,initrd-end"))) {
                if(len!=4U && len!=8U) return r;
                uint64_t v=len==4U?be32(val):be64(val);
                if(eq(key,key_len,"linux,initrd-start")) {initrd_start=v;seen_start=1;}
                else {initrd_end=v;seen_end=1;}
            }
            pos=align4(pos+len);
            if(pos>end_struct) return r;
        } else if(token==NOP) {
        } else if(token==END) { finished=(depth==0);break; }
        else return r;
    }
    r.root_cells_2_2=(uint8_t)(root_addr==2 && root_size==2);
    r.reserved_cells_2_2=(uint8_t)(res_present && res_addr==2 && res_size==2);
    if(seen_start!=seen_end || (seen_start && (initrd_start>=initrd_end ||
       overlap(lo,hi,initrd_start,initrd_end)))) {
        r.ramdisk_overlap=1;
    }
    r.ramdisk_present=(uint8_t)(seen_start && seen_end);
    r.fdt_valid=(uint8_t)(finished && r.root_cells_2_2 && r.reserved_cells_2_2 &&
                           r.reserve_table_valid);
    return r;
}
