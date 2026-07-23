#!/usr/bin/env python3
"""퀴즈 70문항·선택지·정답과 표시 조정 원장을 Markdown으로 생성한다."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "assets/translations/worldmap_text.json"
OUTPUT = ROOT / "docs/23-worldmap-quiz-audit.md"


def md_text(text: str) -> str:
    return (
        text.replace("{end}", "")
        .replace("{nl}", "<br>")
        .replace("|", r"\|")
    )


def code_text(text: str) -> str:
    return text.replace("{end}", "").replace("{nl}", " / ")


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    entries = data["entries"]
    fixed = data["fixed_messages"]
    status = data["status_line"]
    if len(entries) != 350:
        raise SystemExit("350개 퀴즈 문자열이 필요")

    lines = [
        "# 23 · 월드맵 퀴즈 전수 검수 — 문항·선택지·정답",
        "",
        "이 문서는 `assets/translations/worldmap_text.json`에서 자동 생성한다. "
        "게임은 네 선택지를 매번 섞지만 `$C0:8E6D`에서 원본 슬롯 값을 "
        "`[1,2,3,4]`로 만든 뒤 `$C0:8F39`의 `DEC/BEQ`로 값 1을 정답 처리한다. "
        "따라서 아래의 **정답은 항상 원본 선택지 1의 내용**이며, 화면의 A/B/X/Y "
        "버튼 위치는 매번 달라질 수 있다.",
        "",
        "## 검수 범위",
        "",
        "- 산수 40문항 + 정보 30문항 = 70문항",
        "- 질문 70 + 선택지 280 = 포인터 DB 350문자열",
        "- 시작 안내 2, 정답 반응 3, 오답 반응 2 = 고정 UI 7문자열",
        "- 남은 문항 수·제한 시간을 표시하는 직접 타일 상태줄 1개",
        "- 질문·선택지는 최대 156px, 시작/반응 메시지는 최대 178px",
        "",
        "## 시작·정답·오답 메시지",
        "",
        "| ID | 원문 | 완역 | 실제 표시 | 원본 주소 |",
        "|---|---|---|---|---|",
    ]
    for message in fixed:
        lines.append(
            f"| `{message['id']}` | {md_text(message['jp'])} | "
            f"{md_text(message['kr_full'])} | {md_text(message['kr'])} | "
            f"`{message['addr']}` |"
        )
    lines.extend([
        "",
        "상태줄은 동적 숫자 칸을 그대로 보존한다.",
        "",
        f"- 원문: `{status['text_jp_full']}`",
        f"- 완역: `{status['text_kr_full']}`",
        f"- 실제 표시: `{status['text_kr']}`",
        f"- 프로그램: `{status['program_addr']}`",
        "",
        "## 70문항과 정답",
        "",
        "| # | 구분 | 질문 | 선택지 1 | 선택지 2 | 선택지 3 | 선택지 4 | 정답 |",
        "|---:|---|---|---|---|---|---|---|",
    ])
    category_names = {
        "math_add_sub": "산수·덧뺄셈",
        "math_mul_div": "산수·곱나눗셈",
        "lore_quiz": "정보",
    }
    for base in range(0, 350, 5):
        group = entries[base:base + 5]
        question = group[0]
        choices = group[1:]
        number = base // 5 + 1
        lines.append(
            f"| {number} | {category_names[question['cluster']]} | "
            f"{md_text(question['kr'])} | "
            + " | ".join(md_text(choice["kr"]) for choice in choices)
            + f" | **{md_text(choices[0]['kr'])}** |"
        )

    adapted = [
        entry for entry in entries if entry.get("abbreviated")
    ]
    adapted_fixed = [
        message for message in fixed if message.get("abbreviated")
    ]
    lines.extend([
        "",
        "## 완역과 실제 표시가 다른 항목",
        "",
        "줄바꿈만 달라져도 위치 보존 검토가 가능하도록 이 표에 남긴다. "
        "목록에 없는 문장은 완역과 실제 표시가 동일하다.",
        "",
        "| 위치 | 완역 | 실제 표시 |",
        "|---|---|---|",
    ])
    for entry in adapted:
        lines.append(
            f"| 문항 {entry['question_index'] + 41} (`#{entry['entry_id']}`) | "
            f"`{code_text(entry['kr_full'])}` | `{code_text(entry['kr'])}` |"
        )
    for message in adapted_fixed:
        lines.append(
            f"| 고정 UI `{message['id']}` | `{code_text(message['kr_full'])}` | "
            f"`{code_text(message['kr'])}` |"
        )
    lines.append(
        f"| 상태줄 `{status['program_addr']}` | `{status['text_kr_full']}` | "
        f"`{status['text_kr']}` |"
    )
    lines.extend([
        "",
        "## 재생성",
        "",
        "```sh",
        "python3 scripts/extract_worldmap_text.py",
        "python3 scripts/generate_worldmap_quiz_audit.py",
        "python3 scripts/test_worldmap_quiz.py",
        "```",
        "",
    ])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"퀴즈 검수 문서 생성: {OUTPUT} ({len(entries) // 5}문항)")


if __name__ == "__main__":
    main()
