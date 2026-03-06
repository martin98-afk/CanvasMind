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


class LabelStudioExportComponent(BaseComponent):
    name = "Label Studio YOLO 导出"
    category = "LableStudio"
    description = "从 Label Studio 指定项目导出 YOLO 格式数据集（包含图像和标签）"
    requirements = "label_studio_sdk,requests"
    
    inputs = [
        PortDefinition(name="project_id", label="项目ID（可选）", type=ArgumentType.TEXT, connection=ConnectionType.SINGLE),
    ]
    
    outputs = [
        PortDefinition(name="yolo.zip", label="YOLO数据集压缩包", type=ArgumentType.FILE),
        PortDefinition(name="class_names", label="类别名称列表", type=ArgumentType.JSON),
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
            default="",
            label="项目名称",
            description="要导出的项目名称（与项目ID二选一，优先使用项目ID）",
        ),
        "export_type": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="YOLO_WITH_IMAGES",
            label="导出格式",
            description="选择导出格式类型",
            choices=["YOLO_WITH_IMAGES", "YOLO"]
        ),
    }

    def run(self, params, inputs=None):
        import time
        import zipfile
        import os
        import io
        import requests
        
        # 1. 获取参数
        label_studio_url = params.get("label_studio_url", "http://localhost:9090").rstrip("/")
        api_token = params.get("api_token", "")
        project_name = params.get("project_name", "").strip()
        export_type = params.get("export_type", "YOLO_WITH_IMAGES")
        
        if not api_token:
            raise Exception("请在属性栏设置 Label Studio API Token")
        
        # 获取输入的项目ID
        input_project_id = inputs.get("project_id")
        
        # 2. 初始化 Label Studio 客户端
        from label_studio_sdk import Client
        ls = Client(url=label_studio_url, api_key=api_token)
        try:
            ls.check_connection()
        except Exception as e:
            raise RuntimeError(f"❌ 连接 Label Studio 失败: {e}")
        
        self.logger.info("✅ Label Studio 连接成功")
        
        # 3. 确定项目ID
        target_project_id = None
        
        if input_project_id and str(input_project_id).strip():
            # 优先使用输入的 project_id
            target_project_id = str(input_project_id).strip()
            self.logger.info(f"使用输入的项目ID: {target_project_id}")
        elif project_name:
            # 使用项目名称查找
            self.logger.info(f"正在查找项目: {project_name}")
            for project in ls.get_projects():
                if project.params['title'] == project_name:
                    target_project_id = project.params['id']
                    self.logger.info(f"✅ 找到项目: {project_name}, ID: {target_project_id}")
                    break
            
            if not target_project_id:
                raise ValueError(f"❌ 项目 '{project_name}' 不存在")
        else:
            raise Exception("请输入项目ID或项目名称")
        
        # 4. 发起导出请求
        self.logger.info("🔄 正在请求导出 YOLO 数据...")
        
        export_url = f"{label_studio_url}/api/projects/{target_project_id}/export"
        headers = {'Authorization': f'Token {api_token}'}
        params_export = {'exportType': export_type}
        
        response = requests.get(export_url, headers=headers, params=params_export, stream=True, timeout=60)
        
        if response.status_code != 200:
            raise RuntimeError(f"❌ 导出请求失败: {response.status_code} - {response.text[:200]}")
        
        # 5. 检查导出状态
        content_type = response.headers.get('Content-Type', '')
        
        if 'application/json' in content_type:
            # 异步导出，需要轮询等待
            self.logger.info("⏳ 导出任务已创建，等待完成...")
            target_url = self._wait_for_export_completion(label_studio_url, target_project_id, api_token, export_type)
            if not target_url:
                raise RuntimeError("❌ 导出未完成或失败")
            
            # 下载最终文件
            self.logger.info("📥 下载导出文件...")
            response = requests.get(target_url, headers=headers, stream=True, timeout=300)
        elif 'application/zip' in content_type:
            self.logger.info("✅ 导出已完成，直接下载...")
        else:
            raise RuntimeError(f"❌ 未知的响应类型: {content_type}")
        
        # 6. 获取类别名称
        class_names = self._get_project_classes(ls, target_project_id)
        self.logger.info(f"📋 类别列表: {class_names}")
        
        # 7. 将下载的内容转为 bytes
        self.logger.info("📦 打包输出...")
        zip_bytes = response.content
        
        self.logger.info(f"✅ 导出完成！压缩包大小: {len(zip_bytes) / 1024:.1f} KB")
        
        # 8. 返回结果
        return {
            "yolo.zip": zip_bytes,
            "class_names": class_names
        }
    
    def _wait_for_export_completion(self, base_url, project_id, api_token, export_type, timeout=300):
        """轮询导出状态，直到完成"""
        poll_url = f"{base_url}/api/projects/{project_id}/export"
        headers = {'Authorization': f'Token {api_token}'}
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            time.sleep(3)
            response = requests.get(poll_url, headers=headers, params={'exportType': export_type})
            
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'application/zip' in content_type:
                    # 导出完成
                    return f"{poll_url}?exportType={export_type}"
                elif 'application/json' in content_type:
                    # 仍在处理中
                    self.logger.info("⏳ 等待中...")
        
        return None
    
    def _get_project_classes(self, ls, project_id):
        """获取项目的类别名称列表"""
        try:
            # 通过项目获取标签配置
            project = ls.get_project(project_id)
            label_config = project.label_config
            
            # 解析 Label Studio XML 配置获取类别
            import re
            # 匹配 <Label value="xxx" .../>
            label_pattern = r'<Label\s+value="([^"]+)"'
            classes = re.findall(label_pattern, label_config)
            
            if classes:
                return classes
            
            # 如果解析不到，尝试其他方式
            return []
        except Exception as e:
            self.logger.warning(f"⚠️ 获取类别列表失败: {e}")
            return []
