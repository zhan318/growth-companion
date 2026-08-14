"""MBTI 性格测试模块：32 道题库（4 选项加权计分）+ LLM 职业适配分析

设计要点：
- 每题 4 个选项：2 个指向维度一端、2 个指向另一端；其中各含一个「强」选项（weight=2）和一个「温和」选项（weight=1）
- 选项方向随机化：A 选项不固定指向某一端，避免惯性作答，用户必须认真读题
- 题目顺序随机化：get_questions() 每次返回打乱的题目顺序，同一维度的题不聚在一起，
  防止用户看出维度分组后刻意迎合
- 计分：按选项 dimension 累加 weight，每对维度比较总分
"""

import random

from utils.logger import get_logger

logger = get_logger(__name__)

# ═══════════════════════════════════════
#  题库：32 题，每维度 8 题
#  options 每项: label / text / dimension(指向的字母) / weight(1 温和 / 2 强烈)
# ═══════════════════════════════════════

MBTI_QUESTIONS: list[dict] = [
    # ── E / I 能量来源（8 题）──
    {"id": 1, "dim": "EI", "text": "结束一天忙碌后，你的状态通常更接近：",
     "options": [
        {"label": "A", "text": "迫不及待找人分享今天发生的事", "dimension": "E", "weight": 2},
        {"label": "B", "text": "想先安静待一会儿，缓过劲再说", "dimension": "I", "weight": 1},
        {"label": "C", "text": "需要较长独处时间才能恢复", "dimension": "I", "weight": 2},
        {"label": "D", "text": "愿意和人聊聊，只要不是太累", "dimension": "E", "weight": 1},
     ]},
    {"id": 2, "dim": "EI", "text": "身处满是陌生人的场合，你通常会：",
     "options": [
        {"label": "A", "text": "主动破冰，想认识每一个人", "dimension": "E", "weight": 2},
        {"label": "B", "text": "加入旁边的谈话，但不主动发起", "dimension": "E", "weight": 1},
        {"label": "C", "text": "等别人来找我聊天", "dimension": "I", "weight": 1},
        {"label": "D", "text": "尽快找个安静的角落待着", "dimension": "I", "weight": 2},
     ]},
    {"id": 3, "dim": "EI", "text": "团队讨论时，你的典型表现是：",
     "options": [
        {"label": "A", "text": "边说边理思路，几乎停不下来", "dimension": "E", "weight": 2},
        {"label": "B", "text": "想好了才开口，发言不多但精", "dimension": "I", "weight": 1},
        {"label": "C", "text": "基本只听，被点到名才发言", "dimension": "I", "weight": 2},
        {"label": "D", "text": "发言比较多，偶尔需要停顿思考", "dimension": "E", "weight": 1},
     ]},
    {"id": 4, "dim": "EI", "text": "一个空闲的周末，你更想：",
     "options": [
        {"label": "A", "text": "呼朋唤友出去热闹", "dimension": "E", "weight": 2},
        {"label": "B", "text": "参加一两个小型活动", "dimension": "E", "weight": 1},
        {"label": "C", "text": "在家看书、刷剧或打游戏", "dimension": "I", "weight": 1},
        {"label": "D", "text": "完全一个人待着，不安排任何社交", "dimension": "I", "weight": 2},
     ]},
    {"id": 5, "dim": "EI", "text": "你的「能量值」在什么时刻最高：",
     "options": [
        {"label": "A", "text": "和一群人热热闹闹互动的时候", "dimension": "E", "weight": 2},
        {"label": "B", "text": "独自做一件喜欢的事时", "dimension": "I", "weight": 1},
        {"label": "C", "text": "完全独处的安静时刻", "dimension": "I", "weight": 2},
        {"label": "D", "text": "和一两个合拍的人深聊时", "dimension": "E", "weight": 1},
     ]},
    {"id": 6, "dim": "EI", "text": "朋友临时约你晚上聚餐，你通常会：",
     "options": [
        {"label": "A", "text": "爽快答应，人越多越好", "dimension": "E", "weight": 2},
        {"label": "B", "text": "会去，但希望别拖太晚", "dimension": "E", "weight": 1},
        {"label": "C", "text": "犹豫半天，找理由推掉", "dimension": "I", "weight": 1},
        {"label": "D", "text": "直接拒绝，独处优先", "dimension": "I", "weight": 2},
     ]},
    {"id": 7, "dim": "EI", "text": "学习或做事时，你更喜欢：",
     "options": [
        {"label": "A", "text": "完全独立完成，谢绝打扰", "dimension": "I", "weight": 2},
        {"label": "B", "text": "自己安静地干活", "dimension": "I", "weight": 1},
        {"label": "C", "text": "偶尔和人交流想法", "dimension": "E", "weight": 1},
        {"label": "D", "text": "和同伴讨论着一起推进", "dimension": "E", "weight": 2},
     ]},
    {"id": 8, "dim": "EI", "text": "长途旅行中，你通常会：",
     "options": [
        {"label": "A", "text": "和邻座或同行人聊个不停", "dimension": "E", "weight": 2},
        {"label": "B", "text": "聊一会儿，休息一会儿", "dimension": "E", "weight": 1},
        {"label": "C", "text": "听歌看风景，很少说话", "dimension": "I", "weight": 1},
        {"label": "D", "text": "全程希望没人来打扰", "dimension": "I", "weight": 2},
     ]},

    # ── S / N 信息获取（8 题）──
    {"id": 9, "dim": "SN", "text": "读一篇技术文章时，你更关注：",
     "options": [
        {"label": "A", "text": "具体步骤、代码和数字", "dimension": "S", "weight": 2},
        {"label": "B", "text": "作者想解决的本质问题", "dimension": "N", "weight": 1},
        {"label": "C", "text": "背后的一般原理和抽象规律", "dimension": "N", "weight": 2},
        {"label": "D", "text": "明确的案例和验证过的结果", "dimension": "S", "weight": 1},
     ]},
    {"id": 10, "dim": "SN", "text": "学一项新技能时，你的第一步通常是：",
     "options": [
        {"label": "A", "text": "找教程，一步步跟着做", "dimension": "S", "weight": 2},
        {"label": "B", "text": "先想它有什么用、什么原理", "dimension": "N", "weight": 1},
        {"label": "C", "text": "先搭整体框架，再补细节", "dimension": "N", "weight": 2},
        {"label": "D", "text": "先看别人完整做一遍", "dimension": "S", "weight": 1},
     ]},
    {"id": 11, "dim": "SN", "text": "生活中你更容易注意到：",
     "options": [
        {"label": "A", "text": "眼前正在发生的具体的事", "dimension": "S", "weight": 2},
        {"label": "B", "text": "事情背后可能的走向", "dimension": "N", "weight": 1},
        {"label": "C", "text": "未来的趋势和可能性", "dimension": "N", "weight": 2},
        {"label": "D", "text": "实实在在的数据和细节", "dimension": "S", "weight": 1},
     ]},
    {"id": 12, "dim": "SN", "text": "回忆一件事时，你更容易想起：",
     "options": [
        {"label": "A", "text": "当时的具体画面和细节", "dimension": "S", "weight": 2},
        {"label": "B", "text": "当时的感受和受到的启发", "dimension": "N", "weight": 1},
        {"label": "C", "text": "它说明了什么道理", "dimension": "N", "weight": 2},
        {"label": "D", "text": "事情发生的先后过程", "dimension": "S", "weight": 1},
     ]},
    {"id": 13, "dim": "SN", "text": "评估一个方案时，你更看重：",
     "options": [
        {"label": "A", "text": "它在现实中能不能落地", "dimension": "S", "weight": 2},
        {"label": "B", "text": "它是否足够有新意和想象力", "dimension": "N", "weight": 1},
        {"label": "C", "text": "它有没有长期潜力", "dimension": "N", "weight": 2},
        {"label": "D", "text": "每一步是否清晰可执行", "dimension": "S", "weight": 1},
     ]},
    {"id": 14, "dim": "SN", "text": "面对一款新产品，你先想到的是：",
     "options": [
        {"label": "A", "text": "怎么操作、有哪些功能", "dimension": "S", "weight": 2},
        {"label": "B", "text": "它可能改变什么、带来什么", "dimension": "N", "weight": 1},
        {"label": "C", "text": "它背后的设计理念", "dimension": "N", "weight": 2},
        {"label": "D", "text": "它和现有产品比怎么样", "dimension": "S", "weight": 1},
     ]},
    {"id": 15, "dim": "SN", "text": "你更信任哪类信息：",
     "options": [
        {"label": "A", "text": "亲眼所见、亲身验证的", "dimension": "S", "weight": 2},
        {"label": "B", "text": "逻辑严密推演出来的", "dimension": "N", "weight": 1},
        {"label": "C", "text": "直觉告诉我的判断", "dimension": "N", "weight": 2},
        {"label": "D", "text": "有可靠数据支撑的", "dimension": "S", "weight": 1},
     ]},
    {"id": 16, "dim": "SN", "text": "做计划时，你更关注：",
     "options": [
        {"label": "A", "text": "具体每一步怎么走", "dimension": "S", "weight": 2},
        {"label": "B", "text": "整体目标和方向", "dimension": "N", "weight": 1},
        {"label": "C", "text": "各种可能性和备选路径", "dimension": "N", "weight": 2},
        {"label": "D", "text": "眼前的条件和限制", "dimension": "S", "weight": 1},
     ]},

    # ── T / F 决策方式（8 题）──
    {"id": 17, "dim": "TF", "text": "做重大决定时，你更依赖：",
     "options": [
        {"label": "A", "text": "逻辑分析和客观数据", "dimension": "T", "weight": 2},
        {"label": "B", "text": "这件事对我内心的意义", "dimension": "F", "weight": 1},
        {"label": "C", "text": "它对我关心的人的影响", "dimension": "F", "weight": 2},
        {"label": "D", "text": "利弊得失的理性权衡", "dimension": "T", "weight": 1},
     ]},
    {"id": 18, "dim": "TF", "text": "朋友带着烦恼来找你，你更倾向：",
     "options": [
        {"label": "A", "text": "帮 TA 拆解问题，给出方案", "dimension": "T", "weight": 2},
        {"label": "B", "text": "先让 TA 感觉被理解", "dimension": "F", "weight": 1},
        {"label": "C", "text": "陪着 TA，让 TA 尽情抒发", "dimension": "F", "weight": 2},
        {"label": "D", "text": "问清情况，帮 TA 分析原因", "dimension": "T", "weight": 1},
     ]},
    {"id": 19, "dim": "TF", "text": "你更欣赏的同事是：",
     "options": [
        {"label": "A", "text": "能力强、做事有结果", "dimension": "T", "weight": 2},
        {"label": "B", "text": "热心、愿意帮别人", "dimension": "F", "weight": 1},
        {"label": "C", "text": "体贴、顾全大家感受", "dimension": "F", "weight": 2},
        {"label": "D", "text": "思路清晰、判断准确", "dimension": "T", "weight": 1},
     ]},
    {"id": 20, "dim": "TF", "text": "团队出现分歧时，你更希望：",
     "options": [
        {"label": "A", "text": "摆事实讲道理，辩出对错", "dimension": "T", "weight": 2},
        {"label": "B", "text": "照顾每个人的感受", "dimension": "F", "weight": 1},
        {"label": "C", "text": "维护和气，避免伤感情", "dimension": "F", "weight": 2},
        {"label": "D", "text": "用数据和逻辑说话", "dimension": "T", "weight": 1},
     ]},
    {"id": 21, "dim": "TF", "text": "需要批评别人时，你通常：",
     "options": [
        {"label": "A", "text": "直接指出问题，就事论事", "dimension": "T", "weight": 2},
        {"label": "B", "text": "先肯定再委婉提醒", "dimension": "F", "weight": 1},
        {"label": "C", "text": "尽量不说，怕伤到人", "dimension": "F", "weight": 2},
        {"label": "D", "text": "指出问题并给出改进建议", "dimension": "T", "weight": 1},
     ]},
    {"id": 22, "dim": "TF", "text": "「规则」和「感受」冲突时，你更信：",
     "options": [
        {"label": "A", "text": "规则和标准", "dimension": "T", "weight": 2},
        {"label": "B", "text": "当事人自己的感受", "dimension": "F", "weight": 1},
        {"label": "C", "text": "我的价值观和直觉", "dimension": "F", "weight": 2},
        {"label": "D", "text": "理性分析的结果", "dimension": "T", "weight": 1},
     ]},
    {"id": 23, "dim": "TF", "text": "听到一个不认同的观点，你的第一反应是：",
     "options": [
        {"label": "A", "text": "找逻辑漏洞反驳它", "dimension": "T", "weight": 2},
        {"label": "B", "text": "心里不舒服但不想说", "dimension": "F", "weight": 1},
        {"label": "C", "text": "担心说重了伤和气", "dimension": "F", "weight": 2},
        {"label": "D", "text": "分析它哪里站不住脚", "dimension": "T", "weight": 1},
     ]},
    {"id": 24, "dim": "TF", "text": "你更希望别人这样评价你：",
     "options": [
        {"label": "A", "text": "靠谱、能力强、判断准", "dimension": "T", "weight": 2},
        {"label": "B", "text": "温暖、善良、好相处", "dimension": "F", "weight": 1},
        {"label": "C", "text": "体贴、有人情味", "dimension": "F", "weight": 2},
        {"label": "D", "text": "理性、冷静、有主见", "dimension": "T", "weight": 1},
     ]},

    # ── J / P 生活方式（8 题）──
    {"id": 25, "dim": "JP", "text": "准备一次旅行，你会：",
     "options": [
        {"label": "A", "text": "做详细到小时的行程表", "dimension": "J", "weight": 2},
        {"label": "B", "text": "只定个目的地，其余随机", "dimension": "P", "weight": 1},
        {"label": "C", "text": "完全不计划，到了再说", "dimension": "P", "weight": 2},
        {"label": "D", "text": "订好机票酒店，行程留个大概", "dimension": "J", "weight": 1},
     ]},
    {"id": 26, "dim": "JP", "text": "面对截止日期，你通常是：",
     "options": [
        {"label": "A", "text": "早早完成，留足余量", "dimension": "J", "weight": 2},
        {"label": "B", "text": "临近了才开始抓紧", "dimension": "P", "weight": 1},
        {"label": "C", "text": "最后一刻爆发完成", "dimension": "P", "weight": 2},
        {"label": "D", "text": "提前几天开始，从容收尾", "dimension": "J", "weight": 1},
     ]},
    {"id": 27, "dim": "JP", "text": "你的房间或桌面通常是：",
     "options": [
        {"label": "A", "text": "一切井井有条", "dimension": "J", "weight": 2},
        {"label": "B", "text": "有点乱，但找得到东西", "dimension": "P", "weight": 1},
        {"label": "C", "text": "很乱，只有自己知道在哪", "dimension": "P", "weight": 2},
        {"label": "D", "text": "基本整洁，偶尔会乱", "dimension": "J", "weight": 1},
     ]},
    {"id": 28, "dim": "JP", "text": "计划突然被打乱，你会：",
     "options": [
        {"label": "A", "text": "很不舒服，想办法恢复计划", "dimension": "J", "weight": 2},
        {"label": "B", "text": "无所谓，跟着变", "dimension": "P", "weight": 1},
        {"label": "C", "text": "反而喜欢这种意外", "dimension": "P", "weight": 2},
        {"label": "D", "text": "有点烦，但会重新排一遍", "dimension": "J", "weight": 1},
     ]},
    {"id": 29, "dim": "JP", "text": "你更享受哪种状态：",
     "options": [
        {"label": "A", "text": "一切尽在掌握", "dimension": "J", "weight": 2},
        {"label": "B", "text": "自由安排当下的节奏", "dimension": "P", "weight": 1},
        {"label": "C", "text": "随时可以转向新事物", "dimension": "P", "weight": 2},
        {"label": "D", "text": "有条不紊地推进", "dimension": "J", "weight": 1},
     ]},
    {"id": 30, "dim": "JP", "text": "做决定时你更倾向：",
     "options": [
        {"label": "A", "text": "尽快定下来，不喜欢悬着", "dimension": "J", "weight": 2},
        {"label": "B", "text": "想多留几个选项看看", "dimension": "P", "weight": 1},
        {"label": "C", "text": "保持开放，不急着定", "dimension": "P", "weight": 2},
        {"label": "D", "text": "有个明确方案就安心", "dimension": "J", "weight": 1},
     ]},
    {"id": 31, "dim": "JP", "text": "你的时间观念更接近：",
     "options": [
        {"label": "A", "text": "严格守时，讨厌迟到", "dimension": "J", "weight": 2},
        {"label": "B", "text": "经常卡点", "dimension": "P", "weight": 1},
        {"label": "C", "text": "经常迟到，时间感松散", "dimension": "P", "weight": 2},
        {"label": "D", "text": "习惯提前到", "dimension": "J", "weight": 1},
     ]},
    {"id": 32, "dim": "JP", "text": "任务清单在你的生活里：",
     "options": [
        {"label": "A", "text": "每天必列，逐项打勾", "dimension": "J", "weight": 2},
        {"label": "B", "text": "基本不列，凭感觉来", "dimension": "P", "weight": 1},
        {"label": "C", "text": "从不列，随机应变", "dimension": "P", "weight": 2},
        {"label": "D", "text": "会列，但偶尔不执行", "dimension": "J", "weight": 1},
     ]},
]

# ═══════════════════════════════════════
#  方向随机化（防惯性作答）
#  对每个维度内第 2/4/6/8 题的选项轮转 [C,D,A,B]，
#  使「选项 A」在不同题里交替指向维度两端，用户必须认真读题。
# ═══════════════════════════════════════

_RAW_QUESTIONS = MBTI_QUESTIONS
_dim_counter: dict[str, int] = {}
MBTI_QUESTIONS = []
for _q in _RAW_QUESTIONS:
    _n = _dim_counter.get(_q["dim"], 0)
    _dim_counter[_q["dim"]] = _n + 1
    _opts = _q["options"]
    if _n % 2 == 1:  # 维度内偶数序号题：轮转，让 A 指向另一端
        _opts = [_opts[2], _opts[3], _opts[0], _opts[1]]
    _opts = [dict(_o, label=lb) for lb, _o in zip("ABCD", _opts, strict=True)]
    MBTI_QUESTIONS.append({**_q, "options": _opts})


# 16 型一句话概括（前端展示 / LLM 分析上下文）
MBTI_TYPES: dict[str, str] = {
    "ISTJ": "务实可靠，讲规则重承诺，天生的执行者",
    "ISFJ": "温和细心，默默守护，照顾他人感受",
    "INFJ": "理想主义，洞察人心，追求深层的意义",
    "INTJ": "独立理性，战略思维，目标感极强的规划者",
    "ISTP": "冷静灵活，动手能力强，喜欢研究事物原理",
    "ISFP": "安静敏感，活在当下，用行动而非言语表达",
    "INFP": "理想化，忠于内心价值观，想象力丰富",
    "INTP": "逻辑严密，好奇钻研，热爱抽象与理论",
    "ESTP": "精力充沛，反应快，享受刺激与实战",
    "ESFP": "热情开朗，活在当下，天生的气氛担当",
    "ENFP": "热情有感染力，充满创意，渴望可能性",
    "ENTP": "机敏善辩，点子多，喜欢挑战常规",
    "ESTJ": "果断高效，组织力强，天生的管理者",
    "ESFJ": "热心尽责，善于协调，重视人际关系和谐",
    "ENFJ": "富有感染力，乐于助人，天生的领导者",
    "ENTJ": "强势果决，远见卓识，天生的统帅",
}


def get_questions(shuffle: bool = True) -> list[dict]:
    """返回题库。

    Args:
        shuffle: 是否打乱题目顺序（默认 True，防用户看出维度分组）。
                测试或需要固定顺序时传 False。

    Returns:
        题目列表（含 id / dim / text / options）
    """
    questions = list(MBTI_QUESTIONS)
    if shuffle:
        random.shuffle(questions)
    return questions


def compute_mbti(answers: list[int]) -> tuple[str, dict[str, int]]:
    """根据作答索引计算 MBTI 类型（加权计分）。

    Args:
        answers: 长度与题库一致的列表，每项为选项索引（0-3）

    Returns:
        (mbti 四字母, 各字母加权得分 {"E": int, "I": int, ...})
    """
    scores = {letter: 0 for letter in "EISNTFJP"}
    for i, ans in enumerate(answers):
        if i >= len(MBTI_QUESTIONS):
            break
        q = MBTI_QUESTIONS[i]
        try:
            idx = int(ans)
            opt = q["options"][idx]
            scores[opt["dimension"]] += int(opt.get("weight", 1))
        except (IndexError, ValueError, TypeError, KeyError):
            continue  # 跳过无效作答

    mbti = ""
    mbti += "E" if scores["E"] >= scores["I"] else "I"
    mbti += "S" if scores["S"] >= scores["N"] else "N"
    mbti += "T" if scores["T"] >= scores["F"] else "F"
    mbti += "J" if scores["J"] >= scores["P"] else "P"
    return mbti, scores


def analyze_fit(mbti: str, ideal_role: str, provider: str = "deepseek") -> str:
    """调用 LLM 分析：测出的 MBTI 与理想岗位的匹配度与差异。

    失败时返回降级文本（不阻塞接口）。
    """
    from chatbot.chatbot import chat

    prompt = _build_fit_prompt(mbti, ideal_role)
    try:
        resp = chat([{"role": "user", "content": prompt}], provider=provider)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("MBTI 适配分析调用失败: %s", e)
        return _fit_fallback(mbti, ideal_role, e)


def _build_fit_prompt(mbti: str, ideal_role: str) -> str:
    """构造 MBTI 适配分析提示词（同步/异步共用）"""
    type_desc = MBTI_TYPES.get(mbti, "类型特点")
    return (
        "你是一位 MBTI 职业适配分析师。\n"
        f"用户的 MBTI 类型是 {mbti}（{type_desc}），理想岗位是「{ideal_role}」。\n"
        "请用中文、分点输出（150 字以内）：\n"
        "1. 这个类型的核心性格特质（一句）\n"
        "2. 与理想岗位的匹配点\n"
        "3. 可能的差异或需要补足的地方\n"
        "4. 一句针对性建议\n"
        "直接输出分析内容，不要客套话。"
    )


def _fit_fallback(mbti: str, ideal_role: str, e: Exception) -> str:
    """降级文本（同步/异步共用）"""
    type_desc = MBTI_TYPES.get(mbti, "类型特点")
    return (
        f"你的 MBTI 类型是 **{mbti}**（{type_desc}）。\n"
        f"（适配分析服务暂时不可用：{e}）\n"
        "建议结合自身情况，对照理想岗位「" + ideal_role + "」的日常职责做进一步判断。"
    )


async def analyze_fit_async(mbti: str, ideal_role: str, provider: str = "deepseek") -> str:
    """异步版：调用 LLM 分析 MBTI 与理想岗位的匹配度（不阻塞事件循环）。

    失败时返回降级文本（不阻塞接口）。
    """
    from chatbot.chatbot import achat

    prompt = _build_fit_prompt(mbti, ideal_role)
    try:
        resp = await achat([{"role": "user", "content": prompt}], provider=provider)
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.warning("MBTI 适配分析异步调用失败: %s", e)
        return _fit_fallback(mbti, ideal_role, e)
