#!/usr/bin/env python3
"""미커버 초과 19개 축약 적용 — 슬롯에 맞게 text_kr 교체(의미·톤 보존).
build_patch 재실행하면 제자리에 삽입된다. 최종 문구는 실기 검토 후 재조정 가능."""
import json

# entry_id -> 축약된 text_kr (원본 슬롯에 맞도록)
SHORT = {
    17:  '다음 페이지로 넘겨{end}',
    26:  '「목차」로 돌아가려면{nl}셀렉트{nl}이 모드에서 나가려면{nl}B버튼을 눌러 줘{end}',
    50:  '이 값이 높을수록{nl}최고 속도가 늘어나{end}',
    75:  '테스트 모드야{nl}이걸 본다는 건{nl}게임을 클리어했다는 거네{nl}축하해♥{end}',
    77:  '위아래 키로{nl}얼굴을 골라 줘{end}',
    637: '이대로 괜찮아？{nl}　좋아{nl}　안돼{end}',
    291: '레이스 상황이 이상하다！？{nl}이건 명백히 배틀 레이스가{nl}벌어진다！！{end}',
    292: '레드 플래그가 걸렸는데도{nl}양 팀 다 안 멈춘다！{nl}그대로 파이널에{nl}돌입한다！！{end}',
    396: '저 영감！{end}',
    398: '응원한단 게{nl}그런 뜻이었나…{end}',
    418: '사나이군…{end}',
    430: '지켜봐 줘！{nl}반드시 이긴다！{end}',
    490: 'FOX1{nl}「설마！{end}',
    492: 'FOX3{nl}「빨라！{end}',
    494: '쥴리아나{nl}「설마！{end}',
    495: '사리마{nl}「아직이야！{end}',
    506: '쿠라주{nl}「서두르지 마！{end}',
    508: '샤리테{nl}「설마！{end}',
    590: '슈미트{nl}「너희에겐 미안하지만{nl}이기겠어{end}',
}

P = 'assets/translations/dialogue.json'
D = json.load(open(P, encoding='utf-8'))
n = 0
for x in D['entries']:
    if x['entry_id'] in SHORT:
        # 축약 전 원본 대사 보존(검수·재조정용). 재실행해도 원본은 안 덮어씀.
        if 'text_kr_full' not in x:
            x['text_kr_full'] = x['text_kr']
        x['text_kr'] = SHORT[x['entry_id']]
        n += 1
json.dump(D, open(P, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print(f'축약 적용: {n}개 (원본은 text_kr_full 에 보존)')
