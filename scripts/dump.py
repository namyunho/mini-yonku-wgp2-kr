#!/usr/bin/env python3
"""지정 영역을 hex + Shift-JIS 병렬 덤프 (구조/종결자 파악용). UTF-8 파일 출력."""
import sys

def dump(data, start, end):
    lines = []
    for off in range(start, end, 16):
        row = data[off:off+16]
        hexs = " ".join(f"{b:02X}" for b in row)
        txt = row.decode("shift_jis", errors="replace").replace("\n", "·").replace("\r", "·")
        lines.append(f"{off:06X}  {hexs:<47}  {txt}")
    return "\n".join(lines)

def main():
    path = sys.argv[1]
    data = open(path, "rb").read()
    out = []
    # (start, end, 라벨)
    regions = [
        (0x007180, 0x007260, "메뉴 (はじめから/つづきから 부근)"),
        (0x00F480, 0x00F560, "이름 (せいば レツ/ゴ 부근)"),
        (0x00EB40, 0x00EC00, "카타카나 이름 테이블 (マーキュリー 부근)"),
        (0x01C540, 0x01C620, "UI (Ｘでメニュー 부근)"),
    ]
    for s, e, label in regions:
        out.append(f"=== 0x{s:06X}-0x{e:06X}  {label} ===")
        out.append(dump(data, s, e))
        out.append("")
    open("tmp/dump_report.txt", "w", encoding="utf-8").write("\n".join(out))
    print("wrote tmp/dump_report.txt")

if __name__ == "__main__":
    main()
