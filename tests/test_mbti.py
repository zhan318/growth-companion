"""测试 MBTI 模块：题库完整性 + 加权计分逻辑"""

from mbti import MBTI_TYPES, compute_mbti, get_questions

_PAIRS = {"EI": 0, "SN": 1, "TF": 2, "JP": 3}


def _answers_for(mbti: str) -> list[int]:
    """为每题选择「期望维度端 + 强烈选项(weight=2)」，构造出目标类型。"""
    answers = []
    for q in get_questions(shuffle=False):
        target_letter = mbti[_PAIRS[q["dim"]]]
        for i, opt in enumerate(q["options"]):
            if opt["dimension"] == target_letter and opt.get("weight", 1) == 2:
                answers.append(i)
                break
    return answers


def test_question_bank_complete():
    qs = get_questions(shuffle=False)
    assert len(qs) == 32
    # 每维度 8 题
    from collections import Counter
    dims = Counter(q["dim"] for q in qs)
    assert dims == {"EI": 8, "SN": 8, "TF": 8, "JP": 8}
    # 每题 4 个选项，覆盖维度两端，且每端各含一个强(2)一个温和(1)选项
    for q in qs:
        assert len(q["options"]) == 4
        letters = {opt["dimension"] for opt in q["options"]}
        assert letters == set(q["dim"]), f"题 {q['id']} 选项未覆盖维度两端"
        for letter in q["dim"]:
            weights = [opt.get("weight", 1) for opt in q["options"] if opt["dimension"] == letter]
            assert weights.count(2) == 1 and weights.count(1) == 1, f"题 {q['id']} 强度分布异常"


def test_direction_is_randomized():
    """方向已打乱：同一维度内，A 选项不应总是指向同一个字母。"""
    for dim in ("EI", "SN", "TF", "JP"):
        first_letters = {q["options"][0]["dimension"] for q in get_questions(shuffle=False) if q["dim"] == dim}
        assert len(first_letters) == 2, f"{dim} 维度 A 选项方向未打乱"


def test_weighted_compute_ESTJ():
    mbti, scores = compute_mbti(_answers_for("ESTJ"))
    assert mbti == "ESTJ"
    # 每题选强项：每维度 8 题 × 2 分 = 16 分
    assert scores["E"] == 16 and scores["I"] == 0


def test_weighted_compute_INFP():
    mbti, scores = compute_mbti(_answers_for("INFP"))
    assert mbti == "INFP"
    assert scores["I"] == 16 and scores["N"] == 16


def test_balanced_dimension_takes_first():
    """维度平局时按 >= 规则取前者（E/S/T/J）。"""
    # 构造平局：每个维度选一半题 A 端强项、一半 B 端强项
    answers = []
    for q in get_questions(shuffle=False):
        letter_a, letter_b = q["dim"][0], q["dim"][1]
        # 第 1/3/5/7 题选 A 端，第 2/4/6/8 题选 B 端 → 两端各 16 分平局
        idx_in_dim = [i for i, x in enumerate(get_questions(shuffle=False)) if x["dim"] == q["dim"]].index(q["id"] - 1)
        target = letter_a if idx_in_dim % 2 == 0 else letter_b
        for i, opt in enumerate(q["options"]):
            if opt["dimension"] == target and opt.get("weight", 1) == 2:
                answers.append(i)
                break
    mbti, _ = compute_mbti(answers)
    assert len(mbti) == 4
    assert mbti == "ESTJ"  # 每维度平局取第一个字母：E+S+T+J


def test_invalid_answers_are_skipped():
    mbti, _ = compute_mbti([])
    assert len(mbti) == 4
    mbti, _ = compute_mbti([99] * 32)
    assert len(mbti) == 4


def test_type_desc_has_all_16():
    assert len(MBTI_TYPES) == 16
    assert MBTI_TYPES["INTJ"]
    assert MBTI_TYPES["ESFP"]
