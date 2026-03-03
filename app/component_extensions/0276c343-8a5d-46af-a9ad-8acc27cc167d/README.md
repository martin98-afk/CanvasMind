# Wan 2.6 文生图组件

## 基本信息

| 属性 | 值 |
|------|-----|
| 组件名称 | Wan 2.6 文生图 |
| 组件ID | com.canvasmind.0276c343-8a5d-46af-a9ad-8acc27cc167d |
| 版本 | 1.0.0 |
| API版本 | 2.0 |
| 分类 | API调用/文生图 |
| 作者 | black |
| 更新时间 | 2026-03-03 14:47:26 |

## 组件描述

调用阿里云 **DashScope Wan 2.6** 模型生成图像的 Workflow GUI 组件。

## 功能特性

- 🎨 调用阿里云 DashScope Wan 2.6 模型生成图像
- 📐 支持多种分辨率：1024×1024、1280×1280、720×1280、1280×720
- 🔄 支持提示词自动扩展
- 💧 支持添加水印
- ✨ 支持多个模型切换

## 支持的模型

| 模型名称 | 说明 |
|----------|------|
| wan2.6-t2i | Wan 2.6 文本转图像（默认） |
| z-image-turbo | 快速图像生成 |
| wanx-v1 | WanX V1 版本 |

## 输入端口

| 端口名称 | 标签 | 类型 | 说明 |
|----------|------|------|------|
| prompt | 正向提示词 | TEXT | 必填，描述想要生成的图像内容 |
| negative_prompt | 反向提示词(可选) | TEXT | 可选，描述不想出现在图像中的元素 |

## 输出端口

| 端口名称 | 标签 | 类型 | 说明 |
|----------|------|------|------|
| output_image | 生成的图像 | IMAGE | 返回生成的 PIL Image 对象 |

## 属性配置

| 属性名 | 标签 | 类型 | 默认值 | 说明 |
|--------|------|------|--------|------|
| api_key | DashScope API Key | TEXT | - | **必填**，阿里云 DashScope API 密钥 |
| model | 模型名称 | CHOICE | wan2.6-t2i | 选择使用的模型 |
| size | 分辨率 | CHOICE | 1024×1024 | 输出图像的分辨率 |
| prompt_extend | 提示词自动扩展 | BOOL | True | 是否启用提示词自动扩展 |
| watermark | 添加水印 | BOOL | False | 是否在图像中添加水印 |

## 使用示例

### 1. 获取 API Key

1. 登录 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/)
2. 在「API-KEY 管理」中创建或查看 API Key
3. 将 API Key 填写到组件的 `api_key` 属性中

### 2. 配置提示词

- 在 `prompt` 输入端口传入正向提示词（如：`一只可爱的橘猫在阳光下玩耍`）
- 可选择在 `negative_prompt` 输入端口传入反向提示词（如：`模糊、变形、低质量`）

### 3. 获取结果

组件将在 `output_image` 输出端口返回生成的 PIL Image 对象，可直接连接到其他图像处理组件。

## 技术实现

- **API 端点**: `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`
- **依赖库**: `requests`, `Pillow`, `numpy`
- **超时设置**: API 请求 60 秒，图片下载 30 秒

## 关联文件

- **源代码**: `components/API调用/文生图/0276c343-8a5d-46af-a9ad-8acc27cc167d.py`
- **配置文件**: `manifest.json`
