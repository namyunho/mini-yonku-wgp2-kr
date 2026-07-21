#!/usr/bin/env python3
"""필드 위치보존 바이트 상한에 맞춰 삽입본만 압축하고 원장을 갱신한다."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, "scripts")
from build_adv import encode_text  # noqa: E402


FIELD = Path("assets/translations/field_kr.json")
GLYPH = Path("out/glyph_map.json")
LEDGER = Path("assets/translations/field_shortening_ledger.json")

# 공백만 줄여서는 상한에 들지 않는 짧은 런. 제어마커와 줄 수는 원문 그대로 둔다.
MANUAL = {
    "F0365": "제이\n「왔죠？{wait}{clear}",
    "F0180": "벌써\n근질근질하다구{wait}{clear}",
    "F1238": "쿠라주\n「원숭이！{wait}\n이 원한은 생명의 불꽃이\n다 타도 안 잊겠다！",
    "F0717": "료\n「역시군　카이{wait}\n하지만 기뻐할 건 모두를\n이긴 뒤로 미뤄라{wait}",
    "F0237": "루미코\n「싫어〜{wait}\n안경녀의 세이로쿠를\n못 따돌리겠어！",
    "F1228": "마코토\n「확실한 정보예요",
    "F0066": "카를로\n「왔냐 꼬맹이{wait}\n시작할까？{wait}{clear}",
    "F0281": "마키\n「폐를 끼쳐 미안해요…",
    "F0187": "제이\n「왜 그래？{wait}{clear}",
    "F0319": "마코토\n「안녕　여러분",
    "F0003": "프랑스 팀의 약점？\n글쎄　아직은…{wait}\n그런데 왜 물어？",
    "F0509": "『머리 위…？{c8:07}\n　　알린다\n　　안 알린다{c8:00}",
    "F1244": "디아나\n「오　아름다운 센강！{wait}\n파리 불빛은 붉게 탄다…{wait}\n털썩",
    "F0157": "『뭐라고 할까？{c8:07}\n　　잘 어울려\n　　아니야{c8:00}",
    "F0282": "『아름다운 꽃 든 꽃병이다",
    "F0647": "이벤트 아이템\n『대단한 안경』 획득",
    "F1051": "『어떻게 할까？{c8:07}\n　　준다\n　　안 준다{c8:00}",
    "F1334": "레이스 아이템\n『뜨거운 응원』 획득！",
    "F0712": "제이\n「대단해{wait}\n금세 이렇게까지\n실력이 늘었구나{wait}",
    "F0940": "나도 나이가 들었네…{wait}",
    "F1218": "마키에게 부탁하면\n될지도\n모르겠사옵니다{wait}{clear}",
    "F0279": "치이코\n「{c7:0A}개 남았어〜",
    "F0654": "『맛난 생선이다{wait}",
    "F0655": "『산나물 전골이다{wait}",
    "F0803": "3초 뒤",
    "F0804": "2초 뒤",
    "F0805": "1초 뒤",
    "F0618": "카이\n「레이스할까요？{wait}{clear}",
    "F0725": "토우키치\n「완패옵니다{wait}",
    "F0767": "츠치야 박사\n「이런　일찍 왔구나{wait}\n아직 다 안 모였단다{wait}",
    "F0047": "소녀\n「아아　르존 님\n이 두근거림은 뭐지…？{wait}",
    "F0079": "하지만　레이스는 별개\n친분은 접어 두죠",
    "F0650": "고\n「이 녀석　토우키치 말버릇을\n따라 해{wait}{clear}",
    "F0029": "시합은 별개다\n봐주지 않겠어",
    "F0109": "이벤트 아이템\n『러시아 선물』 획득",
    "F0168": "파이터\n「생각해 보니\n커플룩이잖아\n데헤헤♥{wait}{clear}",
    "F0514": "야요이\n「나랑 같은 짓을 하네…",
    "F0663": "레츠\n「앗　그때 그 녀석！{wait}{clear}",
    "F0686": "레츠\n「대체 뭐지…{wait}{clear}",
    "F0936": "{c8:02}쯧쯧쯧{wait}{c8:00}\n그 주행은 아직 멀었어{wait}",
    "F1008": "토우키치\n「오늘은 건강하게\n크루아상과\n야채를 먹었지요{wait}\n",
    "F0051": "후미에\n「간질여 줘어〜♥",
    "F0071": "박살！",
    "F0084": "쥴리아나\n「코치는\n고맙게 생각해",
    "F0117": "아무\n「거슬린다　꺼져라",
    "F0236": "루미코\n「정말〜　멋없어〜",
    "F0593": "하하하！　부끄러워 마！",
    "F0782": "아름다운 연구원\n「안경 없네{wait}\n후후…",
    "F0796": "제이\n「그래\n찾을 수밖에 없어{wait}",
    "F1046": "『멋진 장식이다",
    "F0007": "『J 컴퓨터다",
    "F0598": "제이\n「그래서 여기…{wait}{clear}",
    "F0694": "텟신\n「각오됐느냐？{wait}{clear}",
    "F0747": "루미코\n「뭐야〜　실망！{wait}",
    "F0993": "치이코\n「레츠 님！{wait}",
    "F0798": "키시카와\n「안경 없네{wait}\n후후…",
    "F1044": "『토우키치 컴퓨터다",
    "F1331": "마코토\n「그럼 시작해요！{wait}",
    "F0069": "{c8:02}꼬마야♥{c8:00}",
    "F0301": "레츠\n「헤",
    "F0431": "있다…",
    "F0661": "그러니…{wait}{clear}",
    "F1023": "J",
}


def compact_spaces(text: str, capacity: int, ch2idx: dict[str, int], where: str) -> str:
    def size(value: str) -> int:
        return len(encode_text(value, ch2idx, where))

    if size(text) <= capacity:
        return text
    # 한국어 반각 띄어쓰기부터 뒤에서 최소 개수만 제거한다.
    for index in range(len(text) - 1, -1, -1):
        if text[index] == " ":
            text = text[:index] + text[index + 1 :]
            if size(text) <= capacity:
                return text
    # 선택지 행 첫머리의 들여쓰기는 보존하고, 문장 중 전각공백만 최소 제거한다.
    for index in range(len(text) - 1, -1, -1):
        if text[index] == "　" and index > 0 and text[index - 1] != "\n":
            text = text[:index] + text[index + 1 :]
            if size(text) <= capacity:
                return text
    return text


def main() -> None:
    data = json.loads(FIELD.read_text(encoding="utf-8"))
    ch2idx = json.loads(GLYPH.read_text(encoding="utf-8"))["char2idx"]
    bad = []
    for entry in data["entries"]:
        text = MANUAL.get(entry["id"], entry["text_kr"])
        text = compact_spaces(text, entry["orig_len"] - 1, ch2idx, entry["id"])
        size = len(encode_text(text, ch2idx, entry["id"]))
        if size > entry["orig_len"] - 1:
            bad.append((entry["id"], size, entry["orig_len"] - 1, text))
        entry["text_kr"] = text

    if bad:
        for item in bad:
            print(item)
        raise SystemExit(f"필드 바이트 상한 미해결 {len(bad)}개")

    changed = [entry for entry in data["entries"] if entry["text_kr_full"] != entry["text_kr"]]
    data["_stats"]["shortened_existing"] = len(changed)
    FIELD.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    done = [
        {
            "system": "field",
            "entry_id": entry["id"],
            "before_kr": entry["text_kr_full"],
            "after_kr": entry["text_kr"],
            "orig_bytes": entry["orig_len"] - 1,
            "after_bytes": len(encode_text(entry["text_kr"], ch2idx, entry["id"])),
            "reason": "전역 글리프 수용량 및 필드 런 위치보존 바이트 상한 조정",
            "status": "done",
            "date": date.today().isoformat(),
        }
        for entry in changed
    ]
    LEDGER.write_text(
        json.dumps(
            {
                "note": "필드/NPC 완역본(text_kr_full)을 보존한 삽입본(text_kr) 수용량 조정 원장.",
                "done_count": len(done),
                "pending_count": 0,
                "done": done,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"필드 바이트 상한 조정 완료: 삽입본 변경 {len(done)}개 / 미해결 0")


if __name__ == "__main__":
    main()
