#!/usr/bin/env python3
"""엄격 VM 파서로 복구한 어드벤처 숨은 대사 58런을 번역 SSOT에 병합한다.

`adv_extract.py`가 원본 ROM에서 다시 만든 `adventure.json`을 정본으로 삼는다.
기존 번역은 (scene, at) 키로 보존하고, 이 파일에 명시한 누락런만 새로 번역한다.
원문과 raw 바이트는 adventure.json에 남고, adventure_kr.json에는 text_jp와 text_kr를
나란히 보존한다. 제어코드 서명이 원문과 달라지면 병합을 거부한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "assets/translations/adventure.json"
KOREAN = ROOT / "assets/translations/adventure_kr.json"


TRANSLATIONS = {
    (0x7A, 0x002C): """제이
「우와！{wait}
이렇게 되어 있구나！！{wait}""",
    (0x8B, 0x006C): """토우키치
「치이코！
설명하시지요{wait}
왜 레츠 님 인형이
저리 많사옵니까？{wait}{clear}""",
    (0x99, 0x0250): """고
「자　잠깐 카를로{wait}{clear}""",

    (0xA8, 0x006B): """카이조
「실은…{wait}{clear}""",
    (0xA8, 0x0087): """레츠
「아빠 무슨 일이에요？{wait}{clear}""",
    (0xA8, 0x00A1): """카이조
「그게…{wait}
결혼반지를
잃어버렸단다{wait}{clear}""",
    (0xA8, 0x00D2): """고
「에에에〜！！{wait}{clear}""",
    (0xA8, 0x00E3): """카이조
「조용！{wait}
엄마가 들으면 큰일 나！{wait}{clear}""",
    (0xA8, 0x0110): """고
「하긴…
엄마한테 들키면
두들겨 맞겠네！{wait}{clear}""",
    (0xA8, 0x0136): """카이조
「으아아！！{wait}
부　부탁이야！{wait}
엄마한테 들키기 전에
찾고 싶어！{wait}
찾는 걸 도와줘！{wait}{clear}""",
    (0xA8, 0x0182): """레츠
「어디서 잃었는지
감도 안 와요？{wait}{clear}""",
    (0xA8, 0x01A2): """카이조
「어젯밤에 잃어버렸는데…{wait}
많이 취해서
어디서 잃어버렸는지
기억이 안 나…{wait}{clear}""",
    (0xA8, 0x01EA): """고
「그럼　무리네
포기할 수밖에 없어{wait}{clear}""",
    (0xA8, 0x020B): """카이조
「그런 말 말아줘！{wait}
""",
    (0xA8, 0x0223): """아빠는　집 안을 찾을 테니 너희는
밖을 찾아봐줘{wait}{clear}""",
    (0xA8, 0x0259): """레츠
「네 찾아볼게요{wait}{clear}""",
    (0xA8, 0x0270): """카이조
「부탁한다
너희만 믿는다{wait}""",

    (0xBE, 0x0074): """고
「제길　져 버렸어！！{wait}{clear}""",
    (0xBE, 0x0090): """제이
「역시 카이
감만 되찾으면
지금도 빠르구나{wait}{clear}""",
    (0xBE, 0x00B6): """카이
「아뇨　솔직히
식은땀 났어요{wait}{clear}""",
    (0xBE, 0x00D8): """레츠
「이런 주행을 보고 나니
다음 대전 상대가
불쌍해질 정도야{wait}{clear}""",
    (0xBE, 0x010C): """토우키치
「정말이지요{wait}
어느 팀이옵니까？
다음에 사반나 솔져스와
맞붙을 불운한 팀은{wait}{clear}""",
    (0xBE, 0x014A): """카이
「아무튼…{wait}
여기까지
도와주셔서
뭐라 감사드려야 할지{wait}{clear}""",
    (0xBE, 0x017E): """고
「뭐　신경 쓰지 마！{wait}{clear}""",
    (0xBE, 0x0196): """료
「하지만 WGP에선 적이다{wait}
다음엔 봐주지 않겠다{wait}{clear}""",
    (0xBE, 0x01C5): """카이
「물론이죠{wait}
저희도 봐드리지 않겠어요{wait}
그럼 전 이만 돌아갈게요{wait}
팀원들과 다음 레이스
작전을 짜야 해서요 그럼！{wait}{clear}""",
    (0xBE, 0x021C): """료
「그래　잘 가{wait}""",
    (0xBE, 0x023B): """토우키치
「아앗！{wait}""",
    (0xBE, 0x0255): """료
「왜 그래？{wait}""",
    (0xBE, 0x026E): """토우키치
「파츠 박스를
돌려받는 걸
잊으셨사옵니다！！{wait}""",
    (0xBE, 0x02BD): """카이
「아　맞다
깜빡했네요{wait}
빌린 파츠 박스를
돌려드려야죠…{wait}""",
    (0xBE, 0x0314): """카이
「또 봐요{wait}""",
    (0xBE, 0x032E): """토우키치
「…파츠를 그대로
들고 가는 줄
알았사옵니다{wait}""",
    (0xBE, 0x036C): """토우키치
「돌아와서
다행이옵니다…{wait}""",

    (0xC5, 0x054D): """츠치야 박사
「이걸로　가변 보디의
작동 불량은 막았지만{wait}
이번엔 이 댐퍼 오일을
사용했을 때의 주행 데이터를
GP칩에 학습시켜야 한다{wait}{clear}""",
    (0xC6, 0x0049): """제이
「좋아　에볼루션！{wait}{clear}""",

    (0xE5, 0x013A): """파이터
「이어서 독일에서 온
강철 군단　아이젠 볼프！{wait}
지난 대회에선 아쉽게 우승을
놓쳤지만　올해는 첫 경기부터
베스트 멤버로 출전{wait}
우승 후보 단연
넘버원이다！{wait}""",
    (0xE5, 0x01D9): """파이터
「오오！
이탈리아의 붉은 야생마
롯소 스트라다 입장이다！{wait}
지난 대회 중 규칙 위반으로
시드를 잃었지만
실력으로 예선을 뚫고
본선에 진출{wait}
스스로 최강이라 믿는
그들의 강함은 진짜다！{wait}""",
    (0xE5, 0x028D): """파이터
「이어서 등장하는 건　설원의
은빛 여우　러시아의
CCP 실버 폭스다！{wait}
견실한 주행과 완벽한 연계
팀워크가 훌륭한 팀이다{wait}
레이서 자신의 능력을
강화한 올해는　작년보다도
우승에 가까운 존재다！{wait}""",
    (0xE5, 0x034A): """파이터
「이어서　중국의 오랜 역사를
등에 지고 찾아온
소사구 주행단 공키！{wait}
하늘을 나는 듯한
경쾌한 레이스 전개가
특기인 그들{wait}
올해도 모두를 깜짝
놀라게 할 재미난 레이스를
보여줄 것 같다！{wait}""",

    (0xE6, 0x00C1): """파이터
「자　드디어 이번 대회 첫 출전
3개 팀 입장이다！{wait}""",
    (0xE6, 0x01BB): """파이터
「이어서　프랑스에서 온
장미꽃 날리는 혁명아
레 방쿠르 입장이다！{wait}
나라의 위신을 걸고
참전했다는 이번 대회{wait}
그들이 관철하는
사랑과 정의는 미니사구계에
혁명의 폭풍을
일으킬 수 있을 것인가！{wait}""",
    (0xE6, 0x0278): """파이터
「마지막은　신비의 나라
이집트에서 온 사자
엔션트 포스다！{wait}
미니사구계에 갑자기
나타난 수수께끼 팀{wait}
예선의 모든 시합을
상대 리타이어로
이기고 올라온
강운의 소유자다！{wait}
아직 베일에 싸인
그들의 진정한 실력은
이번 대회서 밝혀진다！{wait}""",
    (0xE6, 0x0353): """파이터
「그리고 그리고！
여러분 기다리셨죠！{wait}
일본 대표　우리의
TRF 빅토리즈 입장이다！{wait}
두말할 것 없는 영광의
초대 WGP 챔피언 팀{wait}
미니사구 발상지
일본의 저력을 보여주고
V2를 노린다！{wait}""",

    (0xF7, 0x0078): """토우키치
「해냈사옵니다！{wait}
꼴 좋사옵니다！{wait}
스핀 바이퍼가
스트레이트에서도 강하단 걸
증명했사옵니다！{wait}{clear}""",
    (0xF7, 0x00BE): """아무
「후훗{wait}{clear}""",
    (0xF7, 0x00CE): """토우키치
「화났지요{wait}
뭐가 그리
우스운 것이옵니까？{wait}{clear}""",
    (0xF7, 0x00F6): """디아나
「토옷！{wait}""",
    (0xF7, 0x012C): """디아나
「일본 아가씨들이여
작별할 때가 왔다{wait}
우리는 이제
떠나야만 한다{wait}
다시 만날 날까지
부디 계속 아름답기를！{wait}
잘 있어라！{wait}""",
    (0xF7, 0x01BF): """카즈미　＆　후미에
「꺄아아아　안녕히〜！{wait}""",
    (0xF7, 0x01E6): """준
「지　지쳤어{wait}""",
    (0xF7, 0x01F7): """카즈미　＆　후미에
「저 높이서 떨어져도 움직여{wait}
멋져〜♥{wait}""",
    (0xF7, 0x0224): """토우키치
「실은 엄청난 자일지도
모르옵니다{wait}{clear}""",
    (0xF7, 0x02D2): """디아나
「…아무{wait}
스핀 바이퍼의
GP칩 데이터는
얻었나？{wait}{clear}""",
    (0xF7, 0x0303): """아무
「물론 슈발리에 드 로즈에서
자료 확보는 끝났다{wait}
다음 시합에 충분히 쓸 수 있다{wait}
하지만 미쿠니 토우키치는
빅토리즈 안에선
수준 낮은 레이서다{wait}
오늘 데이터만으로
빅토리즈의 전부를
파악했다고 생각하면
큰코다칠 거다{wait}{clear}""",
    (0xF7, 0x0397): """디아나
「그런가…{wait}
이젠 실전에서
대응할 수밖에 없군…{wait}{clear}""",
    (0xF7, 0x03BF): """아무
「그래{wait}{clear}""",
    (0xF7, 0x03CD): """디아나
「후훗…{wait}
혁명이 다가온다{wait}{clear}""",
}

# 포화된 글리프 슬롯 때문에 실제 삽입문을 동의 표현으로 바꾼 경우의 완역 원장.
# generate_shortening_comparison.py가 text_kr과 비교해 별도 목록화한다.
FULL_TRANSLATIONS = {
    (0x7A, 0x002C): """치이코가 된 제이
「우와！{wait}
이렇게 되어 있구나！！{wait}""",
    (0x8B, 0x006C): """토우키치
「치이코！
설명해 보시지요{wait}
왜 저렇게나 레츠 님 인형이
많은 것이옵니까？{wait}{clear}""",
    (0xA8, 0x00E3): """카이조
「쉿！{wait}
엄마한테 들리면 큰일이야！{wait}{clear}""",
    (0xA8, 0x0110): """고
「하긴…
엄마한테 들키면
흠씬 두들겨 맞겠네！{wait}{clear}""",
    (0xA8, 0x0182): """레츠
「어디서 잃어버렸는지
짐작 안 가요？{wait}{clear}""",
    (0xA8, 0x01A2): """카이조
「어젯밤에 잃어버렸는데…{wait}
많이 취해 있어서
어디서 잃어버렸는지
기억이 안 나…{wait}{clear}""",
    (0xA8, 0x0259): """레츠
「알았어요
찾아볼게요{wait}{clear}""",
    (0xBE, 0x0090): """제이
「역시 카이 군
감만 되찾으면
지금도 빠르구나{wait}{clear}""",
    (0xBE, 0x0314): """카이
「그럼　또 봐요{wait}""",
    (0xE5, 0x01D9): """파이터
「오오！
이탈리아의 붉은 야생마
롯소 스트라다 입장이다！{wait}
지난 대회 중 규칙 위반으로
시드권을 잃었지만
실력으로 예선을 뚫고
출전권을 획득{wait}
스스로 최강이라 믿는
그들의 강함은 진짜다！{wait}""",
    (0xE5, 0x028D): """파이터
「이어서 등장하는 건　설원의
은빛 여우　러시아의
CCP 실버 폭스다！{wait}
견실한 주행과 완벽한 호흡
팀워크가 훌륭한 팀이다{wait}
레이서 자신의 능력을
강화한 올해는　작년보다도
우승에 가까운 존재다！{wait}""",
    (0xE6, 0x01BB): """파이터
「이어서　프랑스에서 온
장미 흩날리는 혁명아
레 방쿠르 입장이다！{wait}
나라의 위신을 걸고
참전했다는 이번 대회{wait}
그들이 관철하는
사랑과 정의는 미니사구계에
혁명의 폭풍을
일으킬 수 있을 것인가！{wait}""",
    (0xF7, 0x0078): """토우키치
「해냈사옵니다！{wait}
꼴 좋사옵니다！{wait}
스핀 바이퍼가
스트레이트에서도 강하단 걸
증명해 냈사옵니다！{wait}{clear}""",
    (0xF7, 0x00BE): """아무
「후후훗{wait}{clear}""",
    (0xF7, 0x00CE): """토우키치
「울컥했사옵니다{wait}
뭐가 그리
우스운 것이옵니까？{wait}{clear}""",
    (0xF7, 0x01F7): """카즈미　＆　후미에
「저 높이서 떨어지고도 걷고 있어{wait}
멋져〜♥{wait}""",
    (0xF7, 0x012C): """디아나
「일본의 마드모아젤들이여
작별할 때가 왔다{wait}
우리는 이제
떠나야만 한다{wait}
다시 만날 날까지
부디 지금처럼 아름답기를！{wait}
잘 있어라！{wait}""",
    (0xF7, 0x02D2): """디아나
「…아무{wait}
스핀 바이퍼의
GP칩 데이터는
해킹했나？{wait}{clear}""",
    (0xF7, 0x0303): """아무
「물론
슈발리에 드 로즈에서
해킹은 완료했다{wait}
다음 시합에 충분히 쓸 수 있다{wait}
하지만 미쿠니 토우키치는
빅토리즈 안에선
수준 낮은 레이서다{wait}
오늘 데이터만으로
빅토리즈의 전부를
파악했다고 생각하면
큰코다칠 거다{wait}{clear}""",
    (0xF7, 0x0397): """디아나
「그런가…{wait}
나머진 실전에서
대응할 수밖에 없군…{wait}{clear}""",
    (0xF7, 0x03CD): """디아나
「후훗…{wait}
혁명의 날이 가까웠다{wait}{clear}""",
}


def controls(text: str) -> list[str]:
    return re.findall(r"\{[^}]+\}", text)


def main() -> None:
    source_scenes = json.loads(SOURCE.read_text(encoding="utf-8"))
    korean_doc = json.loads(KOREAN.read_text(encoding="utf-8"))
    old_scenes = {scene["scene"]: scene for scene in korean_doc["scenes"]}
    old_runs = {
        (scene["scene"], run["at"]): run
        for scene in korean_doc["scenes"]
        for run in scene["runs"]
    }
    source_runs = {
        (scene["scene"], run["at"]): run
        for scene in source_scenes
        for run in scene["runs"]
    }

    missing_targets = set(TRANSLATIONS) - set(source_runs)
    if missing_targets:
        raise SystemExit(f"원본 카탈로그에 복구 대상이 없음: {sorted(missing_targets)}")

    already_translated = {
        key for key, run in old_runs.items() if run.get("text_kr")
    }
    discovered = set(source_runs) - already_translated
    false_non_dialogue = {
        key for key in discovered
        if key not in TRANSLATIONS
        and source_runs[key]["cmd"] == 0x20
    }
    unexpected = discovered - set(TRANSLATIONS) - false_non_dialogue
    if unexpected:
        raise SystemExit(f"번역표에 없는 실제 누락런: {sorted(unexpected)}")

    new_scenes = []
    for source_scene in source_scenes:
        sid = source_scene["scene"]
        old_scene = old_scenes.get(sid, {})
        new_scene = {
            "scene": sid,
            "src": source_scene["src"],
            "clean": source_scene["clean"],
            "runs": [],
        }
        for source_run in source_scene["runs"]:
            key = (sid, source_run["at"])
            old = old_runs.get(key, {})
            out = {
                "at": source_run["at"],
                "cmd": source_run["cmd"],
                "text_jp": source_run["text_jp"],
                "text_kr": (
                    TRANSLATIONS[key]
                    if key in TRANSLATIONS
                    else old.get("text_kr", "")
                ),
            }
            if key in FULL_TRANSLATIONS:
                out["text_kr_full"] = FULL_TRANSLATIONS[key]
            elif "text_kr_full" in old:
                out["text_kr_full"] = old["text_kr_full"]
            if key in TRANSLATIONS:
                if controls(source_run["text_jp"]) != controls(out["text_kr"]):
                    raise SystemExit(
                        f"제어코드 서명 불일치 {sid:02X}:{source_run['at']:04X}: "
                        f"{controls(source_run['text_jp'])} != {controls(out['text_kr'])}"
                    )
            new_scene["runs"].append(out)
        # 원래 KR 문서가 의도적으로 생략한 빈 씬까지 불필요하게 늘리지는 않는다.
        if new_scene["runs"] or old_scene:
            new_scenes.append(new_scene)

    korean_doc["scenes"] = new_scenes
    KOREAN.write_text(
        json.dumps(korean_doc, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    translated = sum(
        bool(run.get("text_kr"))
        for scene in new_scenes
        for run in scene["runs"]
    )
    print(
        f"숨은 대사 {len(TRANSLATIONS)}런 병합 완료: "
        f"번역 {translated} / 원본 카탈로그 {len(source_runs)}, "
        f"비대사 cmd0x20 {len(false_non_dialogue)}런 보존"
    )


if __name__ == "__main__":
    main()
