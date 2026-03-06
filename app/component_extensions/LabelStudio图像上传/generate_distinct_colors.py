def generate_distinct_colors(classes):
    """
    为多个类别生成视觉上易区分的颜色
    使用 HSL 模型，均匀分布色相，固定饱和度和亮度
    """
    n = len(classes)
    colors = {}
    
    # 如果类别少，用预定义鲜艳颜色
    predefined = [
        "#e6194b", "#3cb44b", "#ffe119", "#0082c8", "#f58231",
        "#911eb4", "#46f0f0", "#f032e6", "#d2f53c", "#fabebe"
    ]
    
    if n <= 10:
        color_pool = predefined
    else:
        # 多类别：均匀分布在 0~360 色相环上
        color_pool = []
        for i in range(n):
            hue = int((i * 360 / n) % 360)  # 均匀分布
            saturation = 75  # 高饱和，但不过曝
            lightness = 60   # 适中偏亮，避免太暗
            
            # HSL to RGB
            h = hue / 360
            s = saturation / 100
            l = lightness / 100

            c = (1 - abs(2 * l - 1)) * s
            x = c * (1 - abs((h * 6) % 2 - 1))
            m = l - c / 2

            if 0 <= h < 1/6:
                r, g, b = c, x, 0
            elif 1/6 <= h < 2/6:
                r, g, b = x, c, 0
            elif 2/6 <= h < 3/6:
                r, g, b = 0, c, x
            elif 3/6 <= h < 4/6:
                r, g, b = 0, x, c
            elif 4/6 <= h < 5/6:
                r, g, b = x, 0, c
            else:
                r, g, b = c, 0, x

            r = int((r + m) * 255)
            g = int((g + m) * 255)
            b = int((b + m) * 255)

            color = "#{:02x}{:02x}{:02x}".format(r, g, b)
            color_pool.append(color)
    
    # 分配颜色
    for i, class_name in enumerate(classes):
        colors[class_name] = color_pool[i % len(color_pool)]
    
    return colors

