# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py"
spec = importlib.util.spec_from_file_location("base", str(base_path))
base_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_module)

# 导入所需项目
BaseComponent = base_module.BaseComponent
PortDefinition = base_module.PortDefinition
PropertyDefinition = base_module.PropertyDefinition
PropertyType = base_module.PropertyType
ArgumentType = base_module.ArgumentType
ConnectionType = base_module.ConnectionType


class Component(BaseComponent):
    name = "lax公式转图像"
    category = "ocr识别"
    description = ""
    requirements = "matplotlib,numpy,Pillow"
    inputs = [
        PortDefinition(name="input1", label="输入lax文本",
                       type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    outputs = [
        PortDefinition(name="output_image", label="输出图像",
                       type=ArgumentType.IMAGE),
    ]
    properties = {
    }

    def latex2img(self, text, size=32, color=(0.1, 0.1, 0.1), out=None, **kwds):
        """
        LaTex数学公式转图片
        text        - 文本字符串，其中数学公式须包含在两个$符号之间
        size        - 字号，整型，默认32
        color       - 颜色，浮点型三元组，值域范围[0,1]，默认深黑色
        out         - 文件名，仅支持后缀名为.png的文件名。若为None，则返回PIL图像对象
        kwds        - 关键字参数
                        dpi         - 输出分辨率（每英寸像素数），默认72
                        family      - 系统支持的字体，None表示当前默认的字体
                        weight      - 笔画轻重，可选项包括：normal（默认）、light和bold
        """
        import numpy as np
        import os
        from io import BytesIO
        from PIL import Image
        import matplotlib.font_manager as mfm
        from matplotlib import mathtext
        text = text.replace("\displaystyle", "")
        assert out is None or os.path.splitext(
            out)[1].lower() == '.png', '仅支持后缀名为.png的文件名'

        for key in kwds:
            if key not in ['dpi', 'family', 'weight']:
                raise KeyError('不支持的关键字参数：%s' % key)

        dpi = kwds.get('dpi', 72)
        family = kwds.get('family', None)
        weight = kwds.get('weight', 'normal')

        bfo = BytesIO()  # 创建二进制的类文件对象
        prop = mfm.FontProperties(family=family, size=size, weight=weight)
        mathtext.math_to_image(text, bfo, prop=prop, dpi=dpi)
        im = Image.open(bfo)

        r, g, b, a = im.split()
        r, g, b = 255-np.array(r), 255-np.array(g), 255-np.array(b)
        a = r/3 + g/3 + b/3
        r, g, b = r*color[0], g*color[1], b*color[2]

        im = np.dstack((r, g, b, a)).astype(np.uint8)
        im = Image.fromarray(im)

        if out is None:
            return im
        else:
            im.save(out)
            print('生成的图片已保存为%s' % out)

    def run(self, params, inputs=None):
        """
        params: 节点属性（来自UI）
        inputs: 上游输入（key=输入端口名）
        return: 输出数据（key=输出端口名）
        """
        formula_latex_data = inputs.input1
        formula_latex_data = '$' + fr"{formula_latex_data}" + '$'
        image_data = self.latex2img(
            formula_latex_data, size=48, color=(0.9, 0.1, 0.1))
        return {
            "output_image": image_data
        }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    model = Component()
    result = model.debug(
        params={"prop1": "test"},
        inputs={"input1": "output"},
        node_id="测试模型",
        show_input_types=True,
        show_output_types=True,
        show_execution_time=True,
        global_vars={}
    )
    print(result)
