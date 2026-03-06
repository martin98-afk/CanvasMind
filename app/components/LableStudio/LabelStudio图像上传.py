# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path
base_path = Path(__file__).parent.parent / "base.py" if (Path(__file__).parent.parent / "base.py").exists() else Path(__file__).parent.parent.parent / "base.py"
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


class LabelStudioImageUploadComponent(BaseComponent):
    name = "Label Studio 图像上传"
    category = "LableStudio"
    description = "将图像列表上传到 Label Studio，支持创建项目和图像标注任务"
    requirements = "label_studio_sdk,requests,#generate_distinct_colors"

    inputs = [
        PortDefinition(
            name="image_files", label="图像文件列表",
            type=ArgumentType.ARRAY, connection=ConnectionType.SINGLE
        ),
    ]

    outputs = [
        PortDefinition(name="project_id", label="项目ID",
                       type=ArgumentType.TEXT),
        PortDefinition(name="upload_result", label="上传结果",
                       type=ArgumentType.JSON),
    ]

    properties = {
        "label_studio_url": PropertyDefinition(
            type=PropertyType.TEXT,
            default="http://localhost:9090",
            label="Label Studio URL",
            description="Label Studio 服务器地址",
        ),
        "api_token": PropertyDefinition(
            type=PropertyType.TEXT,
            default="",
            label="API Token",
            description="Label Studio 的 API Token，可在设置页面获取",
        ),
        "project_name": PropertyDefinition(
            type=PropertyType.TEXT,
            default="新标注项目",
            label="项目名称",
            description="要创建或使用的项目名称",
        ),
        "classes": PropertyDefinition(
            type=PropertyType.TEXT,
            default="person,car,dog,cat",
            label="标注类别",
            description="用英文逗号分隔的类别名称，如: person,car,dog",
        ),
        "label_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="RectangleLabels",
            label="标注类型",
            description="选择标注类型：矩形、画笔、多边形、椭圆",
            choices=["RectangleLabels", "BrushLabels",
                     "PolygonLabels", "EllipseLabels"]
        ),
    }

    def run(self, params, inputs=None):
        # 1. 获取参数
        label_studio_url = params.get(
            "label_studio_url", "http://localhost:9090").rstrip("/")
        api_token = params.get("api_token", "")
        project_name = params.get("project_name", "新标注项目")
        classes_str = params.get("classes", "person,car,dog,cat")
        label_type = params.get("label_type", "RectangleLabels")

        if not api_token:
            raise Exception("请在属性栏设置 Label Studio API Token")

        # 解析类别列表
        classes = [c.strip() for c in classes_str.split(",") if c.strip()]
        if not classes:
            raise Exception("请至少设置一个标注类别")

        # 获取输入的图像文件列表
        image_files_raw = inputs.get("image_files", [])

        # 处理各种输入类型：list, numpy array, 单个文件路径, 文件对象
        image_files = []

        if image_files_raw is None:
            image_files = []
        elif isinstance(image_files_raw, (list, tuple)):
            image_files = list(image_files_raw)
        elif hasattr(image_files_raw, '__iter__'):
            # numpy array 等可迭代对象
            image_files = list(image_files_raw)
        elif isinstance(image_files_raw, str):
            # 单个文件路径字符串
            image_files = [image_files_raw]
        elif hasattr(image_files_raw, 'name'):
            # 文件对象
            image_files = [image_files_raw.name]
        else:
            image_files = [image_files_raw]

        # 确保所有元素都是路径字符串
        final_image_files = []
        for f in image_files:
            if hasattr(f, 'name'):
                # 文件对象
                final_image_files.append(f.name)
            elif isinstance(f, (str,)):
                final_image_files.append(f)
            else:
                final_image_files.append(str(f))

        image_files = final_image_files

        self.logger.info(f"准备上传 {len(image_files)} 张图像到 Label Studio")
        self.logger.info(f"项目: {project_name}, 类别: {classes}")

        # 2. 初始化 Label Studio 客户端
        from label_studio_sdk import Client
        ls = Client(url=label_studio_url, api_key=api_token)
        ls.check_connection()
        self.logger.info("✅ Label Studio 连接成功")

        # 3. 创建或获取项目
        project_id = self._create_or_get_project(
            ls, project_name, classes, label_type)
        self.logger.info(f"✅ 项目 ID: {project_id}")

        # 4. 上传图像
        upload_results = []
        success_count = 0
        fail_count = 0

        for img_path in image_files:
            result = self._upload_single_image(
                img_path, label_studio_url, api_token, project_id)
            if result["success"]:
                success_count += 1
            else:
                fail_count += 1
            upload_results.append(result)

        self.logger.info(f"📊 上传完成: 成功 {success_count} 张, 失败 {fail_count} 张")

        return {
            "project_id": str(project_id),
            "upload_result": {
                "total": len(image_files),
                "success": success_count,
                "failed": fail_count,
                "details": upload_results
            }
        }

    def _create_or_get_project(self, ls, project_name, classes, label_type):
        """创建新项目或获取已有项目"""
        from generate_distinct_colors import generate_distinct_colors
        # 检查是否已存在同名项目
        for project in ls.get_projects():
            if project.params['title'] == project_name:
                self.logger.info(f"✅ 项目已存在: {project_name}")
                return project.params["id"]

        # 生成高区分度颜色
        class_colors = generate_distinct_colors(classes)

        # 打印颜色映射
        self.logger.info("🎨 颜色分配：")
        for cls, color in class_colors.items():
            self.logger.info(f"  {cls}: {color}")

        # 根据标注类型生成标签配置
        label_config = self._generate_label_config(
            label_type, classes, class_colors)

        # 创建新项目
        project = ls.start_project(
            title=project_name,
            label_config=label_config
        )

        self.logger.info(f"🎉 创建新项目成功: {project_name}")
        return project.params["id"]

    def _generate_label_config(self, label_type, classes, class_colors):
        """生成 Label Studio 标签配置"""

        # 不同标注类型的模板
        templates = {
            "RectangleLabels": """<View>
  <Image name="image" value="$image"/>

  <RectangleLabels name="label" toName="image">
    {labels}
  </RectangleLabels>
</View>""",
            "BrushLabels": """<View>
  <Image name="image" value="$image"/>

  <BrushLabels name="label" toName="image">
    {labels}
  </BrushLabels>
</View>""",
            "PolygonLabels": """<View>
  <Image name="image" value="$image"/>

  <PolygonLabels name="label" toName="image">
    {labels}
  </PolygonLabels>
</View>""",
            "EllipseLabels": """<View>
  <Image name="image" value="$image"/>

  <EllipseLabels name="label" toName="image">
    {labels}
  </EllipseLabels>
</View>"""
        }

        template = templates.get(label_type, templates["RectangleLabels"])

        # 生成标签
        labels_html = "\n".join([
            f'<Label value="{class_name}" background="{
                class_colors[class_name]}"/>'
            for class_name in classes
        ])

        return template.format(labels=labels_html)

    def _upload_single_image(self, image_path, base_url, token, project_id):
        """上传单个图像到 Label Studio"""
        import os
        import requests
        result = {
            "file": str(image_path),
            "success": False,
            "message": ""
        }

        try:
            # 处理不同的输入类型
            if hasattr(image_path, 'name'):
                # 文件对象
                path_str = image_path.name
            elif isinstance(image_path, (str, os.PathLike)):
                path_str = str(image_path)
            else:
                path_str = str(image_path)

            # 检查文件是否存在
            if not os.path.exists(path_str):
                result["message"] = f"文件不存在: {path_str}"
                self.logger.warning(f"❌ {result['message']}")
                return result

            # 上传接口
            url = f'{base_url}/api/projects/{project_id}/import?commit_to_project=false'
            headers = {'Authorization': f'Token {token}'}

            with open(path_str, 'rb') as f:
                files = {'files': f}
                response = requests.post(
                    url, headers=headers, files=files, timeout=60)

            if response.status_code == 201:
                uploaded_id = response.json()['file_upload_ids']

                # 提交到项目
                url2 = f'{base_url}/api/projects/{project_id}/reimport'
                commit_data = {
                    "file_upload_ids": uploaded_id,
                    "files_as_tasks_list": False
                }

                response2 = requests.post(
                    url2, headers=headers, json=commit_data, timeout=60)

                if response2.status_code == 201:
                    result["success"] = True
                    result["message"] = "上传成功"
                    self.logger.info(f"✅ 上传成功: {os.path.basename(path_str)}")
                else:
                    result["message"] = f"提交失败: {response2.status_code}"
                    self.logger.error(f"❌ {result['message']}")
            else:
                result["message"] = f"上传失败: {
                    response.status_code} - {response.text[:100]}"
                self.logger.error(f"❌ {result['message']}")

        except Exception as e:
            result["message"] = f"异常: {str(e)}"
            self.logger.error(f"❌ 上传异常: {path_str} - {str(e)}")

        return result
