"""组装 6 组 Prompt。"""

from prompt.module1 import module_1prompt
from prompt.module2 import module_2prompt
from prompt.module3 import module_3prompt
from prompt.module4 import module_4prompt
from prompt.module5 import module_5prompt
from prompt.module6 import module_6prompt
from prompt.utils import count_chinese_chars


def prompt_rule(modules, last_page_num, has_global_image, has_section23_image, has_tech_route_image):
    target_modules = [
        "封面",
        "一、课题项目概览",
        "二、立项依据",
        "三、项目的研究内容、研究目标，以及拟解决的关键科学问题",
        "四、拟采取的研究方案及可行性分析",
        "五、本项目的特色与创新之处",
    ]
    total_text = "\n\n".join(
        f"【{module}】:\n{modules.get(module, '')}"
        for module in target_modules
        if modules.get(module, "")
    )
    content_module3 = modules["三、项目的研究内容、研究目标，以及拟解决的关键科学问题"]
    lenmodules3 = count_chinese_chars(content_module3)
    content_module4 = modules["四、拟采取的研究方案及可行性分析"]
    combined34 = (
        f"【三、项目的研究内容、研究目标，以及拟解决的关键科学问题】\n{content_module3}\n\n"
        f"【四、拟采取的研究方案及可行性分析】\n{content_module4}\n\n"
    )

    content_module5 = modules["五、本项目的特色与创新之处"]
    content_module6 = modules["六、年度研究计划及预期研究结果"]
    combined56 = (
        f"【五、本项目的特色与创新之处】\n{content_module5}\n\n"
        f"【六、年度研究计划及预期研究结果】\n{content_module6}\n\n"
    )

    prompts = [
        module_1prompt(total_text, last_page_num, has_global_image),
        module_2prompt("【一、课题项目概览】\n" + modules["一、课题项目概览"]),
        module_3prompt("【二、立项依据】\n" + modules["二、立项依据"], has_section23_image),
        module_4prompt(combined34, lenmodules3, has_tech_route_image),
        module_5prompt(combined56),
        module_6prompt(
            "【项目概览】\n"
            + modules["一、课题项目概览"]
            + "\n\n"
            + "【七、研究基础与工作条件】\n"
            + modules["七、研究基础与工作条件"]
            + "\n\n"
            + "【八、申请人简介】\n"
            + modules["八、申请人简介"]
            + "\n\n"
            + "【项目预算表】\n"
            + modules["项目预算表"]
        ),
    ]
    return prompts
