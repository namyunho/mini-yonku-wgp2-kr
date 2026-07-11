#!/usr/bin/env python3
"""최소 65816 선형 디스어셈블러 (M/X 플래그 추적 · HiROM 주소 표기).

정적 역공학용. REP/SEP로 M/X 폭을 추적해 즉치 오퍼랜드 길이를 맞춘다.
분기·JSR/JSL 대상 주소를 계산해 주석으로 단다. 정확한 실행 추적이 아니라
루틴을 사람이 읽기 위한 선형 디스어셈블이므로, 데이터/코드 경계는 사람이 판단한다.

사용: python scripts/disasm.py <rom> <file_offset_hex> <count> [--m 0|1] [--x 0|1] [--bank BB]
  --m/--x: 시작 시 A(m)·X/Y(x) 폭. 1=8bit(기본), 0=16bit.
  --bank : 이 코드가 실행되는 PBR(주소 표기용, 기본 파일오프셋>>16 | 0xC0).
"""
import argparse

# opcode -> (mnemonic, mode). mode가 즉치 폭 결정에 쓰임.
# 모드: imp, imm_m(A폭), imm_x(X폭), imm8, rel8, rel16, dp, dp_x, dp_y,
#       abs, abs_x, abs_y, absl(long), absl_x, ind, ind_x, ind_y, indl, indl_y,
#       dpi(dp indirect), sr(stack rel), sriy, blockmove, absind, absindx
OPS = {
0x00:("BRK","imm8"),0x01:("ORA","ind_x"),0x02:("COP","imm8"),0x03:("ORA","sr"),
0x04:("TSB","dp"),0x05:("ORA","dp"),0x06:("ASL","dp"),0x07:("ORA","indl"),
0x08:("PHP","imp"),0x09:("ORA","imm_m"),0x0A:("ASL","imp"),0x0B:("PHD","imp"),
0x0C:("TSB","abs"),0x0D:("ORA","abs"),0x0E:("ASL","abs"),0x0F:("ORA","absl"),
0x10:("BPL","rel8"),0x11:("ORA","ind_y"),0x12:("ORA","dpi"),0x13:("ORA","sriy"),
0x14:("TRB","dp"),0x15:("ORA","dp_x"),0x16:("ASL","dp_x"),0x17:("ORA","indl_y"),
0x18:("CLC","imp"),0x19:("ORA","abs_y"),0x1A:("INC","imp"),0x1B:("TCS","imp"),
0x1C:("TRB","abs"),0x1D:("ORA","abs_x"),0x1E:("ASL","abs_x"),0x1F:("ORA","absl_x"),
0x20:("JSR","abs"),0x21:("AND","ind_x"),0x22:("JSL","absl"),0x23:("AND","sr"),
0x24:("BIT","dp"),0x25:("AND","dp"),0x26:("ROL","dp"),0x27:("AND","indl"),
0x28:("PLP","imp"),0x29:("AND","imm_m"),0x2A:("ROL","imp"),0x2B:("PLD","imp"),
0x2C:("BIT","abs"),0x2D:("AND","abs"),0x2E:("ROL","abs"),0x2F:("AND","absl"),
0x30:("BMI","rel8"),0x31:("AND","ind_y"),0x32:("AND","dpi"),0x33:("AND","sriy"),
0x34:("BIT","dp_x"),0x35:("AND","dp_x"),0x36:("ROL","dp_x"),0x37:("AND","indl_y"),
0x38:("SEC","imp"),0x39:("AND","abs_y"),0x3A:("DEC","imp"),0x3B:("TSC","imp"),
0x3C:("BIT","abs_x"),0x3D:("AND","abs_x"),0x3E:("ROL","abs_x"),0x3F:("AND","absl_x"),
0x40:("RTI","imp"),0x41:("EOR","ind_x"),0x42:("WDM","imm8"),0x43:("EOR","sr"),
0x44:("MVP","blockmove"),0x45:("EOR","dp"),0x46:("LSR","dp"),0x47:("EOR","indl"),
0x48:("PHA","imp"),0x49:("EOR","imm_m"),0x4A:("LSR","imp"),0x4B:("PHK","imp"),
0x4C:("JMP","abs"),0x4D:("EOR","abs"),0x4E:("LSR","abs"),0x4F:("EOR","absl"),
0x50:("BVC","rel8"),0x51:("EOR","ind_y"),0x52:("EOR","dpi"),0x53:("EOR","sriy"),
0x54:("MVN","blockmove"),0x55:("EOR","dp_x"),0x56:("LSR","dp_x"),0x57:("EOR","indl_y"),
0x58:("CLI","imp"),0x59:("EOR","abs_y"),0x5A:("PHY","imp"),0x5B:("TCD","imp"),
0x5C:("JML","absl"),0x5D:("EOR","abs_x"),0x5E:("LSR","abs_x"),0x5F:("EOR","absl_x"),
0x60:("RTS","imp"),0x61:("ADC","ind_x"),0x62:("PER","rel16"),0x63:("ADC","sr"),
0x64:("STZ","dp"),0x65:("ADC","dp"),0x66:("ROR","dp"),0x67:("ADC","indl"),
0x68:("PLA","imp"),0x69:("ADC","imm_m"),0x6A:("ROR","imp"),0x6B:("RTL","imp"),
0x6C:("JMP","absind"),0x6D:("ADC","abs"),0x6E:("ROR","abs"),0x6F:("ADC","absl"),
0x70:("BVS","rel8"),0x71:("ADC","ind_y"),0x72:("ADC","dpi"),0x73:("ADC","sriy"),
0x74:("STZ","dp_x"),0x75:("ADC","dp_x"),0x76:("ROR","dp_x"),0x77:("ADC","indl_y"),
0x78:("SEI","imp"),0x79:("ADC","abs_y"),0x7A:("PLY","imp"),0x7B:("TDC","imp"),
0x7C:("JMP","absindx"),0x7D:("ADC","abs_x"),0x7E:("ROR","abs_x"),0x7F:("ADC","absl_x"),
0x80:("BRA","rel8"),0x81:("STA","ind_x"),0x82:("BRL","rel16"),0x83:("STA","sr"),
0x84:("STY","dp"),0x85:("STA","dp"),0x86:("STX","dp"),0x87:("STA","indl"),
0x88:("DEY","imp"),0x89:("BIT","imm_m"),0x8A:("TXA","imp"),0x8B:("PHB","imp"),
0x8C:("STY","abs"),0x8D:("STA","abs"),0x8E:("STX","abs"),0x8F:("STA","absl"),
0x90:("BCC","rel8"),0x91:("STA","ind_y"),0x92:("STA","dpi"),0x93:("STA","sriy"),
0x94:("STY","dp_x"),0x95:("STA","dp_x"),0x96:("STX","dp_y"),0x97:("STA","indl_y"),
0x98:("TYA","imp"),0x99:("STA","abs_y"),0x9A:("TXS","imp"),0x9B:("TXY","imp"),
0x9C:("STZ","abs"),0x9D:("STA","abs_x"),0x9E:("STZ","abs_x"),0x9F:("STA","absl_x"),
0xA0:("LDY","imm_x"),0xA1:("LDA","ind_x"),0xA2:("LDX","imm_x"),0xA3:("LDA","sr"),
0xA4:("LDY","dp"),0xA5:("LDA","dp"),0xA6:("LDX","dp"),0xA7:("LDA","indl"),
0xA8:("TAY","imp"),0xA9:("LDA","imm_m"),0xAA:("TAX","imp"),0xAB:("PLB","imp"),
0xAC:("LDY","abs"),0xAD:("LDA","abs"),0xAE:("LDX","abs"),0xAF:("LDA","absl"),
0xB0:("BCS","rel8"),0xB1:("LDA","ind_y"),0xB2:("LDA","dpi"),0xB3:("LDA","sriy"),
0xB4:("LDY","dp_x"),0xB5:("LDA","dp_x"),0xB6:("LDX","dp_y"),0xB7:("LDA","indl_y"),
0xB8:("CLV","imp"),0xB9:("LDA","abs_y"),0xBA:("TSX","imp"),0xBB:("TYX","imp"),
0xBC:("LDY","abs_x"),0xBD:("LDA","abs_x"),0xBE:("LDX","abs_y"),0xBF:("LDA","absl_x"),
0xC0:("CPY","imm_x"),0xC1:("CMP","ind_x"),0xC2:("REP","imm8"),0xC3:("CMP","sr"),
0xC4:("CPY","dp"),0xC5:("CMP","dp"),0xC6:("DEC","dp"),0xC7:("CMP","indl"),
0xC8:("INY","imp"),0xC9:("CMP","imm_m"),0xCA:("DEX","imp"),0xCB:("WAI","imp"),
0xCC:("CPY","abs"),0xCD:("CMP","abs"),0xCE:("DEC","abs"),0xCF:("CMP","absl"),
0xD0:("BNE","rel8"),0xD1:("CMP","ind_y"),0xD2:("CMP","dpi"),0xD3:("CMP","sriy"),
0xD4:("PEI","dp"),0xD5:("CMP","dp_x"),0xD6:("DEC","dp_x"),0xD7:("CMP","indl_y"),
0xD8:("CLD","imp"),0xD9:("CMP","abs_y"),0xDA:("PHX","imp"),0xDB:("STP","imp"),
0xDC:("JML","absindl"),0xDD:("CMP","abs_x"),0xDE:("DEC","abs_x"),0xDF:("CMP","absl_x"),
0xE0:("CPX","imm_x"),0xE1:("SBC","ind_x"),0xE2:("SEP","imm8"),0xE3:("SBC","sr"),
0xE4:("CPX","dp"),0xE5:("SBC","dp"),0xE6:("INC","dp"),0xE7:("SBC","indl"),
0xE8:("INX","imp"),0xE9:("SBC","imm_m"),0xEA:("NOP","imp"),0xEB:("XBA","imp"),
0xEC:("CPX","abs"),0xED:("SBC","abs"),0xEE:("INC","abs"),0xEF:("SBC","absl"),
0xF0:("BEQ","rel8"),0xF1:("SBC","ind_y"),0xF2:("SBC","dpi"),0xF3:("SBC","sriy"),
0xF4:("PEA","imm16"),0xF5:("SBC","dp_x"),0xF6:("INC","dp_x"),0xF7:("SBC","indl_y"),
0xF8:("SED","imp"),0xF9:("SBC","abs_y"),0xFA:("PLX","imp"),0xFB:("XCE","imp"),
0xFC:("JSR","absindx"),0xFD:("SBC","abs_x"),0xFE:("INC","abs_x"),0xFF:("SBC","absl_x"),
}

# 모드별 오퍼랜드 바이트 수 (imm_m/imm_x는 폭에 따라 가변)
FIXED_LEN = {
 "imp":0,"imm8":1,"rel8":1,"rel16":2,"dp":1,"dp_x":1,"dp_y":1,"abs":2,"abs_x":2,
 "abs_y":2,"absl":3,"absl_x":3,"ind":2,"ind_x":1,"ind_y":1,"indl":1,"indl_y":1,
 "dpi":1,"sr":1,"sriy":1,"blockmove":2,"absind":2,"absindx":2,"absindl":2,"imm16":2,
}

def fmt_operand(mode, ops, pc, bank, m8, x8):
    if mode in ("imm_m","imm_x"):
        wide = (mode=="imm_m" and not m8) or (mode=="imm_x" and not x8)
        if wide:
            v = ops[0] | (ops[1]<<8); return f"#${v:04X}", 2
        else:
            return f"#${ops[0]:02X}", 1
    n = FIXED_LEN[mode]
    b = ops[:n]
    if mode=="imm8": return f"#${b[0]:02X}", 1
    if mode=="imm16": v=b[0]|(b[1]<<8); return f"#${v:04X}", 2
    if mode=="rel8":
        d=b[0]; d=d-256 if d>=128 else d; tgt=(pc+2+d)&0xFFFF
        return f"${tgt:04X}", 1
    if mode=="rel16":
        v=b[0]|(b[1]<<8); v=v-65536 if v>=32768 else v; tgt=(pc+3+v)&0xFFFF
        return f"${tgt:04X}", 2
    if mode in ("dp","dp_x","dp_y","ind_x","ind_y","indl","indl_y","dpi","sr","sriy"):
        suf={"dp":"","dp_x":",X","dp_y":",Y","ind_x":",X)","ind_y":"),Y","indl":"]","indl_y":"],Y","dpi":")","sr":",S","sriy":",S),Y"}[mode]
        pre="(" if mode in("ind_x","ind_y","dpi") else ("[" if mode in("indl","indl_y") else "")
        return f"{pre}${b[0]:02X}{suf}", 1
    if mode in ("abs","abs_x","abs_y","absind","absindx","absindl"):
        v=b[0]|(b[1]<<8)
        suf={"abs":"","abs_x":",X","abs_y":",Y","absind":")","absindx":",X)","absindl":"]"}[mode]
        pre="(" if mode in("absind","absindx") else ("[" if mode=="absindl" else "")
        return f"{pre}${v:04X}{suf}", 2
    if mode in ("absl","absl_x"):
        v=b[0]|(b[1]<<8)|(b[2]<<16); suf=",X" if mode=="absl_x" else ""
        return f"${v:06X}{suf}", 3
    if mode=="blockmove":
        return f"${b[0]:02X},${b[1]:02X}", 2
    return "?", n

def disasm(rom, off, count, bank, m8, x8):
    pc = off & 0xFFFF
    end = off + count
    out=[]
    while off < end:
        opc = rom[off]
        mn, mode = OPS[opc]
        operand, olen = fmt_operand(mode, rom[off+1:off+6], pc, bank, m8, x8)
        raw = " ".join(f"{rom[off+k]:02X}" for k in range(1+olen))
        line = f"{bank:02X}:{pc:04X}  {raw:<12}  {mn} {operand}".rstrip()
        out.append(line)
        # 플래그 추적
        if opc==0xC2:  # REP
            v=rom[off+1]
            if v&0x20: m8=False
            if v&0x10: x8=False
        elif opc==0xE2:  # SEP
            v=rom[off+1]
            if v&0x20: m8=True
            if v&0x10: x8=True
        off += 1+olen; pc=(pc+1+olen)&0xFFFF
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("rom"); ap.add_argument("off",type=lambda s:int(s,0))
    ap.add_argument("count",type=lambda s:int(s,0))
    ap.add_argument("--m",type=int,default=1); ap.add_argument("--x",type=int,default=1)
    ap.add_argument("--bank",type=lambda s:int(s,0),default=None)
    a=ap.parse_args()
    rom=open(a.rom,"rb").read()
    bank=a.bank if a.bank is not None else (0xC0|(a.off>>16))
    for l in disasm(rom,a.off,a.count,bank,a.m==1,a.x==1):
        print(l)

if __name__=="__main__":
    main()
