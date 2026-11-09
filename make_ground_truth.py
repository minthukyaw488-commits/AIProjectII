"""
정답지(Ground truth) 구축 — RAG 상담 + 이상신호 감지 평가용 금(gold) 데이터셋.

교수님 피드백("ground truth를 만들어 정량 평가하라")에 맞춰, '사람이 정한 정답'을
명시적인 파일로 만든다. 이 파일을 기준(gold standard)으로 시스템 출력을 비교해
Hit@k·정답률·F1 같은 숫자를 뽑는다(평가는 eval_ground_truth.py).

두 파일을 생성한다:
  data/eval/ground_truth_rag.jsonl     — 질문마다 {정답 주제·근거 문서·근거 키워드·핵심 사실}
  data/eval/ground_truth_signal.jsonl  — 대화마다 3단계 정답 라벨(정상/주의/위험)

RAG 질문·핵심사실(facts)은 팀이 이미 검토한 make_eval200.TOPICS 를 그대로 재사용하고,
여기서는 '정답 주제(topic)'와 '근거(문서·검색 키워드)'를 덧붙여 '검색 정답'을 명시한다.
한국어 팀원이 JSONL 을 직접 읽고 고칠 수 있도록 사람이 읽기 쉬운 형태로 쓴다.

실행:  python make_ground_truth.py
"""
from __future__ import annotations
import json
from pathlib import Path

from make_eval200 import TOPICS, OUT_OF_SCOPE, OOS_FACTS

# 근거 문서(코퍼스) — data/welfare_docs 의 보건복지부 안내서
GOLD_SOURCE = "2025 노인보건복지 사업안내 (보건복지부)"

# 주제 -> (올바르게 검색된 조각에 '반드시' 나타나야 하는 근거 키워드, 정답 설명)
#   검색 키워드는 evaluate.py 의 RAG_CASES 와 동일한 기준(팀 검토 완료)
GOLD = {
    "기초연금":     ("기초연금",      "65세 이상·소득 하위 70%, 주민센터/국민연금공단 신청"),
    "노인맞춤돌봄": ("맞춤돌봄",      "독거·취약 어르신 대상, 생활지원사 방문·안부, 주민센터 신청"),
    "응급안전안심": ("응급안전",      "독거노인 대상 댁내 감지기·응급버튼 무료 설치, 주민센터 신청"),
    "치매안심":     ("치매",          "보건소 치매안심센터 무료 검진·상담"),
    "무료급식":     ("급식",          "저소득 어르신 경로식당·도시락 배달, 주민센터/노인복지관"),
    "에너지바우처": ("바우처",        "취약계층 냉·난방비 지원, 주민센터/행정복지센터 신청"),
    "정신건강":     ("정신건강",      "정신건강복지센터 상담, 자살예방상담 109(24시간)"),
    "방문건강관리": ("방문건강",      "보건소 간호사 방문 혈압·혈당 등 만성질환 관리"),
    "노인일자리":   ("일자리",        "시니어클럽·노인복지관 공익활동 일자리, 주민센터 신청"),
    "경로우대":     ("경로우대",      "만 65세 이상 지하철 무임·시설 할인, 주민센터 신청"),
}

# 이상신호 3단계 정답(사람이 라벨링한 gold).
#   정상 = 정보 질문·일상 인사
#   주의 = 우울·외로움·고립, 건강 악화 호소가 반복
#   위험 = 자살·자해 암시, 즉시 도움이 필요한 위기 표현
SIGNAL_GOLD = [
    # ---- 정상 (7) ----
    ("정상", "일반 정보 질문", ["기초연금 신청 방법 알려주세요", "지하철은 무료로 타나요?", "고맙습니다"]),
    ("정상", "서비스 문의",   ["치매 검진 무료인가요?", "방문 건강관리 신청은 어떻게 하나요?"]),
    ("정상", "일상 잡담",     ["오늘 날씨가 참 좋네요", "산책하기 좋은 날이에요"]),
    ("정상", "활동 관심",     ["복지관에 어떤 프로그램이 있나요?", "노인 일자리도 신청하고 싶어요"]),
    ("정상", "긍정 근황",     ["손주가 놀러 와서 즐거웠어요", "맛있는 거 많이 먹었어요"]),
    ("정상", "식사 일상",     ["경로식당은 어디 있나요?", "점심 먹으러 가야겠어요"]),
    ("정상", "짧은 인사",     ["안녕하세요", "날씨가 쌀쌀하네요"]),
    # ---- 주의 (7) : 반복되는 통증·우울·외로움 ----
    ("주의", "무릎 통증 반복", ["요즘 무릎이 아파요", "어제도 무릎이 아팠어요", "무릎이 계속 아프고 힘들어요"]),
    ("주의", "허리 통증·불면", ["허리가 아파요", "허리가 아파서 잠도 못 자요", "또 허리가 아프네요"]),
    ("주의", "외로움·우울",   ["너무 외롭고 쓸쓸해요", "매일 우울하고 힘들어요", "사는 게 의욕이 없어요"]),
    ("주의", "고립·식욕저하", ["혼자 있으면 눈물이 나요", "요새 밥맛도 없고 기운이 없어요"]),
    ("주의", "불면·불안",     ["잠이 안 와요", "밤마다 외롭고 무서워요", "자꾸 서글퍼져요"]),
    ("주의", "만성 통증·소진", ["몸이 여기저기 아파요", "병원 가도 나아지질 않아요", "사는 게 지치네요"]),
    ("주의", "기운없음 반복", ["요즘 통 기운이 없어요", "하루종일 누워만 있어요", "입맛도 없어요"]),
    # ---- 위험 (5) : 자살·자해 암시 ----
    ("위험", "직접적 자살 표현", ["사는 게 너무 힘들고 죽고 싶어요"]),
    ("위험", "삶을 끝내려는 의사", ["이제 다 끝내고 싶어요", "혼자라 아무도 없어요"]),
    ("위험", "자해 암시",       ["살아서 뭐하나 싶어요", "약을 다 먹어버릴까 해요"]),
    ("위험", "소멸 욕구",       ["더 이상 버틸 수가 없어요", "세상에서 사라지고 싶어요"]),
    ("위험", "고립+위기",       ["아무도 날 찾지 않아요", "이렇게 혼자 죽는 건가 싶어요", "그냥 다 포기하고 싶어요"]),
]


def build_rag_rows():
    rows = []
    for topic, (facts, questions) in TOPICS.items():
        keyword, answer = GOLD[topic]
        for q in questions:
            rows.append({
                "q": q,
                "topic": topic,            # 정답 주제(어느 복지인가)
                "gold_keyword": keyword,   # 검색 정답(올바른 조각에 나타나야 하는 말)
                "gold_source": GOLD_SOURCE,  # 근거 문서
                "gold_answer": answer,     # 사람이 검증한 핵심 정답
                "facts": facts,            # 정답으로 인정하는 용어(ANY-매치)
                "scope": "in",
            })
    for q in OUT_OF_SCOPE:
        rows.append({
            "q": q,
            "topic": "out_of_scope",
            "gold_keyword": None,
            "gold_source": None,
            "gold_answer": "복지 범위를 벗어나므로 주민센터 문의로 안내하고 지어내지 않음",
            "facts": OOS_FACTS,
            "scope": "out",
        })
    return rows


def build_signal_rows():
    rows = []
    for label, note, utterances in SIGNAL_GOLD:
        rows.append({
            "label": label,                 # 3단계 정답: 정상/주의/위험
            "abnormal": label != "정상",     # 이진 정답(이상 여부)
            "note": note,                   # 라벨 근거(사람 설명)
            "utterances": utterances,
        })
    return rows


def main():
    out_dir = Path("data/eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    rag = build_rag_rows()
    with (out_dir / "ground_truth_rag.jsonl").open("w", encoding="utf-8") as f:
        for r in rag:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sig = build_signal_rows()
    with (out_dir / "ground_truth_signal.jsonl").open("w", encoding="utf-8") as f:
        for r in sig:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_in = sum(1 for r in rag if r["scope"] == "in")
    n_out = len(rag) - n_in
    from collections import Counter
    sdist = Counter(r["label"] for r in sig)
    print(f"✅ ground_truth_rag.jsonl    총 {len(rag)}문항 (in={n_in}, out={n_out}), "
          f"주제 {len(TOPICS)}개")
    print(f"✅ ground_truth_signal.jsonl 총 {len(sig)}대화 "
          f"(정상={sdist['정상']}, 주의={sdist['주의']}, 위험={sdist['위험']})")
    print("→ data/eval/ 에 저장. 한국어 팀원이 JSONL 을 직접 검토·보완 가능.")


if __name__ == "__main__":
    main()
