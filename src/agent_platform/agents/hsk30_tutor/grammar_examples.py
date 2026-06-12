"""HSK 3.0 语法例句库 — 按等级提供关键语法点的典型例句。

用于 system prompt 注入，让 LLM 有参考模板。
"""
from __future__ import annotations

from typing import Dict, List

# ── 每个等级的核心语法点 + 2-3 个例句 ──────────────────────────

GRAMMAR_EXAMPLES: Dict[str, List[Dict[str, str]]] = {
    "1": [
        {"point": "能愿动词「会/能/想/要/可以」",
         "examples": "我会说中文。| 我能听懂。| 我想去商店。| 你可以坐这儿。"},
        {"point": "疑问代词「什么/谁/哪/怎么」",
         "examples": "你叫什么名字？| 他是谁？| 你去哪里？| 你怎么了？"},
        {"point": "否定副词「不/没(有)」",
         "examples": "我不想去。| 他没有来。| 今天不冷。"},
        {"point": "结构助词「的」",
         "examples": "这是我的书。| 妈妈做的饭很好吃。"},
        {"point": "动态助词「了」",
         "examples": "我吃了饭。| 他去了学校。| 下雨了。"},
        {"point": "语气助词「吗/呢/吧」",
         "examples": "你好吗？| 你呢？| 我们走吧。"},
        {"point": "「在/正在」+ 动词",
         "examples": "我在看书。| 他正在吃饭。"},
    ],
    "2": [
        {"point": "动词重叠 AA/A一A",
         "examples": "你看看这本书。| 我想一想。| 你试试这件衣服。"},
        {"point": "形容词重叠 AA/AABB",
         "examples": "高高兴兴地去上学。| 房间干干净净的。"},
        {"point": "动态助词「过」",
         "examples": "我去过中国。| 你吃过饺子吗？"},
        {"point": "动态助词「着」",
         "examples": "门开着。| 他笑着说话。"},
        {"point": "连词「因为…所以…」「虽然…但是…」",
         "examples": "因为下雨，所以我不去了。| 虽然很贵，但是很好。"},
        {"point": "介词「从/往/给/比/跟」",
         "examples": "我从北京来。| 往前走。| 给我一杯水。| 他比我高。| 跟他说一下。"},
        {"point": "动量词「次」",
         "examples": "我去过两次中国。| 请再说一次。"},
    ],
    "3": [
        {"point": "能愿动词「需要/该/应该/愿意/得」",
         "examples": "你需要多休息。| 我应该早点儿来。| 你得好好学习。"},
        {"point": "疑问代词的非疑问用法（任指/不定指）",
         "examples": "什么都可以。| 谁也不知道。| 我想去哪儿就去哪儿。"},
        {"point": "副词「比较/更/特别/挺」",
         "examples": "今天比较冷。| 这个更好。| 他特别喜欢音乐。| 这个挺好的。"},
        {"point": "「一边…一边…」",
         "examples": "我一边吃饭一边看电视。"},
        {"point": "连词「不但…而且…」「如果…就…」",
         "examples": "他不但会说中文，而且说得很好。| 如果下雨，我就不去了。"},
        {"point": "介词「为了/关于/向」",
         "examples": "为了学中文，他去了中国。| 关于这个问题，我知道得不多。"},
        {"point": "动补短语「V+得/不+结果」",
         "examples": "我听得懂。| 这个字我写不好。| 你做得很好。"},
    ],
    "4": [
        {"point": "能愿动词「敢」",
         "examples": "我不敢一个人去。| 你敢不敢试试？"},
        {"point": "指示代词「各/任何/此」",
         "examples": "各位同学好。| 任何问题都可以问。| 此事很重要。"},
        {"point": "副词「到底/究竟/毕竟」",
         "examples": "你到底想去哪儿？| 他毕竟是个孩子。"},
        {"point": "「比」字句",
         "examples": "他比我高。| 今天比昨天冷。| 这个比那个贵得多。"},
        {"point": "「把」字句",
         "examples": "请把门关上。| 我把书放在桌子上了。"},
        {"point": "「被」字句",
         "examples": "杯子被他打破了。| 我被雨淋了。"},
        {"point": "复句「不是…就是…」「既然…就…」",
         "examples": "他不是中国人就是日本人。| 既然来了，就多玩几天。"},
    ],
    "5": [
        {"point": "指示代词「彼此/如此/本」",
         "examples": "我们彼此了解。| 事情如此简单。| 本人不同意。"},
        {"point": "副词「过于/相当/格外/极其」",
         "examples": "你过于紧张了。| 这个相当好。| 他格外努力。"},
        {"point": "「对/对于」引出对象",
         "examples": "对于这个问题，大家有什么看法？| 对我来说很重要。"},
        {"point": "紧缩复句「越…越…」「非…不可」",
         "examples": "中文越学越有意思。| 我非去不可。"},
        {"point": "「是…的」强调句",
         "examples": "我是昨天到的。| 他是在中国学的中文。"},
    ],
    "6": [
        {"point": "类前缀「超—/多—/反—/无—/准—」",
         "examples": "超级市场 | 多功能 | 反对 | 无线 | 准妈妈"},
        {"point": "类后缀「—化/—式/—型/—性」",
         "examples": "现代化 | 中式 | 新型 | 可能性"},
        {"point": "副词「简直/未免/何必/何尝」",
         "examples": "这简直太好了！| 你未免太着急了。| 何必呢？"},
        {"point": "复句「无论…都…」「只要…就…」",
         "examples": "无论多难，我都要学。| 只要努力，就能成功。"},
    ],
    "7-9": [
        {"point": "类前缀「后—/亲—」",
         "examples": "后代 | 后果 | 亲自 | 亲眼"},
        {"point": "类后缀「—观/—鬼/—界/—然/—坛/—为/—制」",
         "examples": "世界观 | 酒鬼 | 文学界 | 显然 | 体坛 | 行为 | 体制"},
        {"point": "成语/固定搭配",
         "examples": "一举两得 | 无论如何 | 不可思议 | 自言自语"},
        {"point": "书面语关联词「倘若/纵然/乃至」",
         "examples": "倘若明天下雨，活动将取消。| 纵然困难重重，也要坚持。"},
    ],
}


def get_grammar_examples(level: int) -> List[Dict[str, str]]:
    """获取指定等级的语法例句列表。"""
    key = "7-9" if level >= 7 else str(level)
    return GRAMMAR_EXAMPLES.get(key, [])


def get_grammar_examples_text(level: int) -> str:
    """生成语法例句的文本格式（用于 prompt 注入）。"""
    examples = get_grammar_examples(level)
    if not examples:
        return ""
    lines = []
    for item in examples:
        lines.append(f"【{item['point']}】")
        for ex in item["examples"].split("|"):
            ex = ex.strip()
            if ex:
                lines.append(f"  · {ex}")
        lines.append("")
    return "\n".join(lines)
