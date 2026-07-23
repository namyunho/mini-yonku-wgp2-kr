#!/usr/bin/env python3
"""필드 삽입본의 글리프/바이트 수용량 조정과 영구 원장 기록."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path


FIELD = Path("assets/translations/field_kr.json")
LEDGER = Path("assets/translations/field_shortening_ledger.json")

# ID: (완역본에 있어야 할 구절, 삽입본 대체 구절)
# text_kr_full은 절대 수정하지 않는다.
REPLACE = {
    "F0033": ("유럽 선수권도", "유럽 선수 대회도"),
    "F0422": ("회전식 권총이래", "회전식 총이래"),
    "F0434": ("゛N256 발표！！゛", "『N256 발표！！』"),
    "F1118": ("팸플릿으로", "안내 책자로"),
    "F0172": ("귱귱그와오〜！", "규웅규웅그와오〜！"),
    "F1264": ("『진검승부에 관객은 없어』래", "『진검승부엔 둘뿐이야』래"),
    "F1260": ("맨손으로 곰을 쓰러뜨린대", "맨손으로 야수를 이긴대"),
    "F0838": ("얄궂은 일이네", "묘한 일이네"),
    "F1048": ("김나는 여행", "여행"),
    "F0205": ("옷깃 디자인", "칼라 디자인"),
    "F0380": ("30분이나 깎아 만든", "30분이나 줄여 만든"),
    "F0601": ("『깔끔하게 정리돼 있다", "『잘 정리돼 있다"),
    "F0551": ("바깥일이", "외부 일이"),
    "F0943": ("레이스할껴？", "레이스할래유？"),
    "F0849": ("콘택트렌즈를 꼈어요", "콘택트를 하고 왔어요"),
    "F0282": ("꽃이 꽂혀 있다", "꽃이 들어 있다"),
    "F0214": ("즈뀨우우우웅！", "즈큐우우우웅！"),
    "F0463": ("음모의 냄새가 나네", "음모의 향기가 나네"),
    "F0528": ("더 넓은 코스", "더 큰 코스"),
    "F1245": ("속았지？", "당했지？"),
    "F0670": ("녹으니까", "사라지니까"),
    "F0940": ("나도 이제 늙었네", "나도 이제 나이가 들었네"),
    "F0508": ("나도 참 덜렁이라니까", "나도 참 실수했다니까"),
    "F0472": ("그 덥수룩한 수염", "그 무성한 수염"),
    "F0548": ("어딜 쏘다니는 거야", "어디를 돌아다니는 거야"),
    "F0719": ("맡았다니 놀랍군", "맡았다니 대단하군"),
    "F0461": ("구레나룻 멋지지？", "수염 멋지지？"),
    "F0881": ("개발 중이므로", "개발 중이라"),
    "F1295": ("요즘 싱글벙글해", "요즘 늘 웃고 있어"),
    "F1221": ("내게도 봄이", "내게도 좋은 때가"),
    "F0955": ("뵐 낯이", "볼 낯이"),
    "F1278": ("드라마 데뷔작이", "드라마 첫 출연작이"),
    "F0906": ("제게서 빼앗아 보세요", "이겨서 받아 가세요"),
    "F0222": ("기쁨의", "즐거운"),
    "F1008": ("샐러드로", "야채로"),
    "F0329": ("너무 셌나요？", "너무 강했나요？"),
    "F0568": ("자물쇠가 잠겨 있다", "문이 잠겨 있다"),
    "F0477": ("쌌거든", "저렴했거든"),
    "F1148": ("썰렁한 농담은", "시시한 농담은"),
    "F1300": ("벌써 썼네", "벌써 했네"),
    "F0482": ("쏜살같아서", "무척 빨라서"),
    "F0557": ("『드라군 엠블럼』", "『드라군 문장』"),
    "F1292": ("살짝 엿봤어", "몰래 봤어"),
    "F0136": ("쟤　너무", "저 애　너무"),
    "F0793": ("짐작 가는 곳은", "생각나는 곳은"),
    "F1263": ("멀쩡해！", "문제없어！"),
    "F0428": ("항아리와 찻잔", "항아리와 그릇"),
    "F0010": ("첫 승은 우리가 챙긴다！", "첫 승은 우리 거다！"),
    "F0236": ("완전 촌스러〜", "너무 멋없어〜"),
    "F0412": ("엄청 춥잖아", "정말 차갑잖아"),
    "F1262": ("다음 빈칸에", "다음 빈 곳에"),
    "F0257": ("캔디 세이버", "사탕 세이버"),
    "F1155": ("충격이 컸어", "충격이 커"),
    "F0116": ("콤비네이션을", "연계 주행을"),
    "F0559": ("쿵쾅거리는 소리가", "큰 소리가"),
    "F1288": ("도쿄에서 고속도로를 타고", "도시에서 고속도로를 타고"),
}


def main() -> None:
    data = json.loads(FIELD.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in data["entries"]}
    done = []
    for entry_id, (before_part, after_part) in REPLACE.items():
        entry = by_id[entry_id]
        full = entry["text_kr_full"]
        if before_part not in full:
            raise SystemExit(f"{entry_id}: 완역본 기준 구절 없음: {before_part!r}")
        expected = full.replace(before_part, after_part)
        entry["text_kr"] = expected
        done.append(
            {
                "system": "field",
                "entry_id": entry_id,
                "before_kr": full,
                "after_kr": expected,
                "reason": "전역 $CA 글리프 1024슬롯 수용량 조정(완역본 보존)",
                "status": "done",
                "date": date.today().isoformat(),
            }
        )

    data["_stats"]["shortened_existing"] = sum(
        entry["text_kr_full"] != entry["text_kr"] for entry in data["entries"]
    )
    FIELD.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
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
    print(f"필드 수용량 조정 {len(done)}개 / 완역본 보존 / {LEDGER}")


if __name__ == "__main__":
    main()
