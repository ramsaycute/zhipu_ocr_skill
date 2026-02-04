---
name: zhipu_ocr_skill
description: 高性能通用 OCR 文档解析 Skill，基于智谱 GLM-OCR 模型，支持 PDF、图片、文件夹并发识别与智能 Markdown 缝合。
---

# 智谱 GLM-OCR 高性能解析技能 (Skill)

本 Skill 用于将图片或 PDF 文档高效转换为结构化的 Markdown 文件。它针对大型文档、医学资料、复杂排版进行了深度优化。

## 🌟 核心能力
1. **全格式支持**: 兼容图片 (PNG, JPG, JPEG, WebP) 及多页 PDF。
2. **高并发加速**: 默认 10 线程并行请求，处理速度相较单线程提升 10 倍。
3. **断点恢复**: 自动在磁盘保留页级缓存，识别中断后可无缝继续，无需重新消耗 API。
4. **智能拼合**: 
   - **PDF 模式**: 自动缝合汉字断行，去除分页符。
   - **文件夹模式**: 显式标注每个图片来源，自动生成标题。
5. **格式清理**: 自动剥离 LaTeX 公式痕迹（如 `$15\mathrm{g}$` 转为 `15g`）。

## 🛠 配置说明
在使用前，请确保在 `zhipu_ocr_skill/` 目录下存在 `config.json`：
```json
{
  "api_key": "你的智谱API_KEY",
  "api_endpoint": "https://open.bigmodel.cn/api/paas/v4/layout_parsing",
  "model_name": "glm-ocr"
}
```

## � 环境与预检 (Pre-checks)
脚本启动时会自动检查以下内容：
1. **依赖库**: 确保已安装 `requests` 和 `PyMuPDF (fitz)`。
2. **写权限**: 检查**当前工作目录 (CWD)** 是否具备写权限，以便存放缓存和结果文件。
3. **配置文件**: 确保脚本目录下存在合法的 `config.json`。

## 📝 输出物与存储逻辑
为了保证工作区简洁，所有生成物都将保存在**用户当前执行命令的工作目录 (Current Working Directory)**：
- **最终结果**: `{文件名}_ocr_result.md` 
- **临时缓存**: `.{文件名}_cache/` (识别成功后可手动删除，或保留以备断点续传)

## 🛡 维护性逻辑
- 脚本中内置了 `clean_markdown_text` 用于清洗幻觉标记。
- 脚本利用缓存机制保护处理进度。
