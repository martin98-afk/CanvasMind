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


class LabelStudioPreannotationImportComponent(BaseComponent):
    """
    Label Studio 预标注导入组件
    
    将 YOLO/COCO 格式的模型预测结果批量导入到 Label Studio 项目中作为预标注，
    标注员可以在此基础上快速校正，提高标注效率。
    """
    name = "Label Studio 预标注导入"
    category = "LableStudio"
    description = "将 YOLO/COCO 格式的模型预测结果导入到 Label Studio 项目中作为预标注"
    requirements = "label_studio_sdk,requests,Pillow"

    inputs = [
        PortDefinition(
            name="project_id", label="项目ID（可选）",
            type=ArgumentType.TEXT, connection=ConnectionType.SINGLE,
            description="目标 Label Studio 项目ID"
        ),
    ]

    outputs = [
        PortDefinition(name="import_result", label="导入结果",
                       type=ArgumentType.JSON),
        PortDefinition(name="annotated_count", label="已标注任务数",
                       type=ArgumentType.INT),
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
            description="目标项目名称（与项目ID二选一，优先使用项目ID）",
        ),
        "annotation_format": PropertyDefinition(
            type=PropertyType.CHOICE,
            default="YOLO",
            label="标注格式",
            description="选择模型预测结果的格式",
            choices=["YOLO", "COCO"]
        ),
        "images_dir": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="图像目录",
            description="图像文件所在目录（YOLO格式需要）",
            filter="Directory (*)"
        ),
        "labels_dir": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="标注目录",
            description="YOLO 标签文件(.txt)所在目录",
            filter="Directory (*)"
        ),
        "coco_json": PropertyDefinition(
            type=PropertyType.FILE,
            default="",
            label="COCO JSON文件",
            description="COCO 格式的标注文件路径 (annotation.json)",
            filter="JSON (*.json)"
        ),
        "confidence_threshold": PropertyDefinition(
            type=PropertyType.FLOAT,
            default=0.3,
            label="置信度阈值",
            description="只导入置信度高于此值的检测框（仅部分格式支持）",
        ),
        "overwrite_existing": PropertyDefinition(
            type=PropertyType.BOOL,
            default=False,
            label="覆盖已有标注",
            description="是否覆盖任务中已有的标注结果",
        ),
    }

    def run(self, params, inputs=None):
        import os
        import json
        import requests
        import time
        from PIL import Image

        # 1. 获取参数
        label_studio_url = params.get("label_studio_url", "http://localhost:9090").rstrip("/")
        api_token = params.get("api_token", "")
        project_name = params.get("project_name", "").strip()
        annotation_format = params.get("annotation_format", "YOLO")
        images_dir = params.get("images_dir", "").strip()
        labels_dir = params.get("labels_dir", "").strip()
        coco_json = params.get("coco_json", "").strip()
        confidence_threshold = params.get("confidence_threshold", 0.3)
        overwrite_existing = params.get("overwrite_existing", False)

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
            target_project_id = str(input_project_id).strip()
            self.logger.info(f"使用输入的项目ID: {target_project_id}")
        elif project_name:
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

        # 4. 获取项目的类别信息
        project = ls.get_project(target_project_id)
        label_config = project.label_config
        classes = self._parse_label_config(label_config)
        
        if not classes:
            raise ValueError("❌ 无法从项目中解析出标注类别，请检查项目标签配置")
        
        self.logger.info(f"📋 项目类别: {classes}")

        # 5. 根据格式导入预标注
        if annotation_format == "YOLO":
            if not images_dir or not labels_dir:
                raise Exception("❌ YOLO 格式需要设置图像目录和标注目录")
            
            if not os.path.isdir(images_dir):
                raise Exception(f"❌ 图像目录不存在: {images_dir}")
            if not os.path.isdir(labels_dir):
                raise Exception(f"❌ 标注目录不存在: {labels_dir}")
            
            result = self._import_yolo_annotations(
                label_studio_url, api_token, target_project_id,
                images_dir, labels_dir, classes, confidence_threshold, overwrite_existing
            )
        else:  # COCO
            if not coco_json:
                raise Exception("❌ COCO 格式需要设置 COCO JSON 文件路径")
            
            if not os.path.isfile(coco_json):
                raise Exception(f"❌ COCO JSON 文件不存在: {coco_json}")
            
            result = self._import_coco_annotations(
                label_studio_url, api_token, target_project_id,
                coco_json, classes, confidence_threshold, overwrite_existing
            )

        self.logger.info(f"✅ 预标注导入完成: {result}")
        
        return {
            "import_result": result,
            "annotated_count": result.get("annotated_count", 0)
        }

    def _parse_label_config(self, label_config):
        """从 Label Studio XML 配置中解析类别名称"""
        import re
        # 匹配 <Label value="xxx" .../>
        label_pattern = r'<Label\s+value="([^"]+)"'
        classes = re.findall(label_pattern, label_config)
        return classes

    def _import_yolo_annotations(self, base_url, api_token, project_id,
                                 images_dir, labels_dir, classes,
                                 confidence_threshold, overwrite):
        """导入 YOLO 格式的预标注"""
        import os
        import glob
        
        headers = {'Authorization': f'Token {api_token}'}
        
        # 获取项目中的任务列表
        tasks_url = f"{base_url}/api/projects/{project_id}/tasks"
        response = requests.get(tasks_url, headers=headers, params={"limit": 10000})
        
        if response.status_code != 200:
            raise RuntimeError(f"❌ 获取任务列表失败: {response.status_code}")
        
        tasks = response.json()
        
        # 构建 filename -> task_id 映射
        task_map = {}
        for task in tasks:
            # 获取文件存储名
            storage_name = task.get("data", {}).get("image", "")
            if storage_name:
                filename = os.path.basename(storage_name)
                task_map[filename] = task["id"]
        
        self.logger.info(f"📂 项目中共有 {len(task_map)} 个任务")
        
        # 获取所有标注文件
        label_files = glob.glob(os.path.join(labels_dir, "*.txt"))
        
        annotated_count = 0
        failed_count = 0
        skipped_count = 0
        results = []

        for label_file in label_files:
            base_name = os.path.splitext(os.path.basename(label_file))[0]
            
            # 尝试匹配图像文件
            image_exts = ['.jpg', '.jpeg', '.png', '.bmp']
            image_path = None
            for ext in image_exts:
                potential_path = os.path.join(images_dir, base_name + ext)
                if os.path.exists(potential_path):
                    image_path = potential_path
                    break
            
            if not image_path:
                self.logger.warning(f"⚠️ 找不到对应的图像文件: {base_name}")
                skipped_count += 1
                continue
            
            image_filename = os.path.basename(image_path)
            
            # 检查任务是否存在
            task_id = task_map.get(image_filename)
            if not task_id:
                # 尝试不带扩展名的匹配
                for fn, tid in task_map.items():
                    if os.path.splitext(fn)[0] == base_name:
                        task_id = tid
                        break
            
            if not task_id:
                self.logger.warning(f"⚠️ 项目中找不到任务: {image_filename}")
                skipped_count += 1
                continue
            
            # 解析 YOLO 标注
            annotations = self._parse_yolo_file(label_file, classes, confidence_threshold)
            
            if not annotations:
                self.logger.info(f"⏭️ 跳过无标注文件: {label_file}")
                skipped_count += 1
                continue
            
            # 构建预标注数据
            preannotations = self._build_preannotations(annotations, classes, image_path)
            
            # 导入预标注
            success = self._import_preannotation_to_task(
                base_url, api_token, project_id, task_id,
                preannotations, overwrite
            )
            
            if success:
                annotated_count += 1
                results.append({"task_id": task_id, "filename": image_filename, "boxes": len(annotations)})
            else:
                failed_count += 1

        return {
            "total_label_files": len(label_files),
            "annotated_count": annotated_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "details": results
        }

    def _parse_yolo_file(self, label_file, classes, confidence_threshold):
        """解析 YOLO 标注文件"""
        annotations = []
        
        try:
            with open(label_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    parts = line.split()
                    if len(parts) < 5:
                        continue
                    
                    class_id = int(parts[0])
                    
                    # 处理带置信度和不带置信度的格式
                    if len(parts) >= 6:
                        # 格式: class_id x_center y_center width height confidence
                        try:
                            confidence = float(parts[5])
                            if confidence < confidence_threshold:
                                continue
                        except (ValueError, IndexError):
                            confidence = 1.0
                    else:
                        confidence = 1.0
                    
                    if class_id >= len(classes):
                        self.logger.warning(f"⚠️ 类别ID {class_id} 超出范围: {label_file}")
                        continue
                    
                    # YOLO 格式是归一化的中心点坐标和宽高
                    x_center = float(parts[1])
                    y_center = float(parts[2])
                    width = float(parts[3])
                    height = float(parts[4])
                    
                    # 转换为左上右下坐标（归一化）
                    x_min = (x_center - width / 2) * 100  # 转为百分比
                    y_min = (y_center - height / 2) * 100
                    x_max = (x_center + width / 2) * 100
                    y_max = (y_center + height / 2) * 100
                    
                    annotations.append({
                        "class_id": class_id,
                        "class_name": classes[class_id],
                        "x_min": x_min,
                        "y_min": y_min,
                        "x_max": x_max,
                        "y_max": y_max,
                        "confidence": confidence
                    })
        except Exception as e:
            self.logger.error(f"❌ 解析 YOLO 文件失败: {label_file}, {e}")
        
        return annotations

    def _build_preannotations(self, annotations, classes, image_path):
        """构建 Label Studio 格式的预标注"""
        from PIL import Image
        
        # 获取图像尺寸
        try:
            with Image.open(image_path) as img:
                img_width, img_height = img.size
        except Exception as e:
            self.logger.warning(f"⚠️ 无法读取图像尺寸，使用默认值: {e}")
            img_width, img_height = 100, 100
        
        # 构建预测结果
        predictions = []
        
        for ann in annotations:
            # 将归一化坐标转换为像素坐标
            x = ann["x_min"] / 100 * img_width
            y = ann["y_min"] / 100 * img_height
            w = (ann["x_max"] - ann["x_min"]) / 100 * img_width
            h = (ann["y_max"] - ann["y_min"]) / 100 * img_height
            
            predictions.append({
                "original_width": img_width,
                "original_height": img_height,
                "image_rotation": 0,
                "value": {
                    "x": ann["x_min"],
                    "y": ann["y_min"],
                    "width": ann["x_max"] - ann["x_min"],
                    "height": ann["y_max"] - ann["y_min"],
                    "rotation": 0,
                    "rectanglelabels": [ann["class_name"]]
                },
                "id": f"pred_{ann['class_id']}_{int(ann.get('confidence', 1) * 1000)}",
                "from_name": "label",
                "to_name": "image",
                "type": "rectanglelabels",
                "origin": "manual"
            })
        
        return predictions

    def _import_coco_annotations(self, base_url, api_token, project_id,
                                  coco_json, classes, confidence_threshold, overwrite):
        """导入 COCO 格式的预标注"""
        import os
        import json
        
        headers = {'Authorization': f'Token {api_token}'}
        
        # 读取 COCO JSON
        with open(coco_json, 'r') as f:
            coco_data = json.load(f)
        
        # 获取图像信息
        images = {img["id"]: img for img in coco_data.get("images", [])}
        
        # 获取类别映射
        coco_categories = {cat["id"]: cat["name"] for cat in coco_data.get("categories", [])}
        
        # 构建 filename -> task_id 映射
        tasks_url = f"{base_url}/api/projects/{project_id}/tasks"
        response = requests.get(tasks_url, headers=headers, params={"limit": 10000})
        tasks = response.json()
        
        task_map = {}
        for task in tasks:
            storage_name = task.get("data", {}).get("image", "")
            if storage_name:
                filename = os.path.basename(storage_name)
                image_info = None
                for img in coco_data.get("images", []):
                    if os.path.basename(img.get("file_name", "")) == filename:
                        image_info = img
                        break
                if image_info:
                    task_map[image_info["id"]] = task["id"]
        
        self.logger.info(f"📂 项目中共有 {len(task_map)} 个任务")
        
        # 按图像分组标注
        annotations_by_image = {}
        for ann in coco_data.get("annotations", []):
            image_id = ann["image_id"]
            if image_id not in annotations_by_image:
                annotations_by_image[image_id] = []
            annotations_by_image[image_id].append(ann)
        
        annotated_count = 0
        failed_count = 0
        skipped_count = 0
        results = []

        for image_id, image_anns in annotations_by_image.items():
            # 获取图像信息
            image_info = images.get(image_id)
            if not image_info:
                continue
            
            # 查找对应的任务
            task_id = task_map.get(image_id)
            if not task_id:
                skipped_count += 1
                continue
            
            # 解析标注
            coco_annotations = []
            for ann in image_anns:
                category_id = ann.get("category_id")
                class_name = coco_categories.get(category_id)
                
                if class_name not in classes:
                    continue
                
                # COCO bbox: [x, y, width, height]
                bbox = ann.get("bbox", [])
                if len(bbox) < 4:
                    continue
                
                x, y, w, h = bbox
                
                # 转换为 Label Studio 格式（百分比）
                img_width = image_info.get("width", 1)
                img_height = image_info.get("height", 1)
                
                x_percent = (x / img_width) * 100
                y_percent = (y / img_height) * 100
                w_percent = (w / img_width) * 100
                h_percent = (h / img_height) * 100
                
                coco_annotations.append({
                    "class_name": class_name,
                    "x_min": x_percent,
                    "y_min": y_percent,
                    "x_max": x_percent + w_percent,
                    "y_max": y_percent + h_percent,
                    "confidence": ann.get("score", 1.0)
                })
            
            if not coco_annotations:
                skipped_count += 1
                continue
            
            # 过滤低置信度
            coco_annotations = [a for a in coco_annotations 
                               if a["confidence"] >= confidence_threshold]
            
            if not coco_annotations:
                skipped_count += 1
                continue
            
            # 构建预标注
            image_path = image_info.get("file_name", "")
            preannotations = self._build_preannotations(coco_annotations, classes, image_path)
            
            # 导入
            success = self._import_preannotation_to_task(
                base_url, api_token, project_id, task_id,
                preannotations, overwrite
            )
            
            if success:
                annotated_count += 1
                results.append({"task_id": task_id, "image_id": image_id, "boxes": len(coco_annotations)})
            else:
                failed_count += 1

        return {
            "total_images": len(annotations_by_image),
            "annotated_count": annotated_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "details": results
        }

    def _import_preannotation_to_task(self, base_url, api_token, project_id,
                                        task_id, preannotations, overwrite):
        """将预标注导入到指定任务"""
        import requests
        
        headers = {'Authorization': f'Token {api_token}'}
        
        # 如果需要覆盖，先删除已有标注
        if overwrite:
            # 获取当前标注
            annotations_url = f"{base_url}/api/tasks/{task_id}/annotations"
            response = requests.get(annotations_url, headers=headers)
            
            if response.status_code == 200:
                existing = response.json()
                if existing:
                    # 删除所有标注
                    for ann in existing:
                        delete_url = f"{annotations_url}/{ann['id']}"
                        requests.delete(delete_url, headers=headers)
        
        # 导入新标注
        import_url = f"{base_url}/api/tasks/{task_id}/predictions"
        
        # 使用 predictions 端点（这是 ML Backend 预标注的标准方式）
        payload = {
            "model_version": "preannotation",
            "result": preannotations,
            "score": sum(p.get("score", 1.0) for p in preannotations) / len(preannotations) if preannotations else 0
        }
        
        response = requests.post(import_url, headers=headers, json=payload)
        
        if response.status_code in [200, 201]:
            self.logger.info(f"✅ 任务 {task_id} 预标注导入成功 ({len(preannotations)} 个框)")
            return True
        else:
            # 尝试使用 annotations 端点
            annotations_url = f"{base_url}/api/tasks/{task_id}/annotations"
            payload = {"lead_time": 0, "result": preannotations}
            
            response = requests.post(annotations_url, headers=headers, json=payload)
            
            if response.status_code in [200, 201]:
                self.logger.info(f"✅ 任务 {task_id} 标注导入成功 ({len(preannotations)} 个框)")
                return True
            else:
                self.logger.error(f"❌ 任务 {task_id} 导入失败: {response.status_code} - {response.text[:200]}")
                return False
