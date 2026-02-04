# Zhipu GLM-OCR 高性能文档解析工具

这是一个基于智谱 AI `glm-ocr` 模型的高性能通用文档解析工具，旨在将 PDF 和图片高效转换为结构化的 Markdown 文件。它特别针对大型文档处理、医学资料及复杂排版进行了深度优化。

## 🌟 核心特性

- **多格式支持**: 完美处理单张图片 (PNG, JPG, JPEG, WebP)、图片文件夹以及多页 PDF。
- **高并发加速**: 采用多线程并行请求架构（默认 10 并发），处理效率提升达 10 倍。
- **可靠的断点续传**: 自动在磁盘保留页级缓存，如遇中断可无缝继续，无需重复消耗 API 额度。
- **智能合并算法**: 
  - **PDF 模式**: 自动处理跨页断行，实现汉字无缝拼接，移除分页杂质。
  - **文件夹模式**: 自动标注来源文件名，并统一生成页面标题。
- **深度格式清理**: 自动剥离 LaTeX 公式痕迹（如将 `$15\mathrm{g}$` 自动还原为 `15g`）。

## 🚀 快速开始

### 1. 安装依赖
```bash
pip install requests pymupdf
```

### 2. 配置 API Key
在项目根目录创建 `config.json`（可参考 `config.json.example`）：
```json
{
  "api_key": "YOUR_ZHIPU_API_KEY",
  "api_endpoint": "https://open.bigmodel.cn/api/paas/v4/layout_parsing",
  "model_name": "glm-ocr",
  "max_concurrency": 10
}
```
> API Key 获取地址: [智谱 AI 开放平台](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)

### 3. 运行识别
```bash
# 处理 PDF
python3 scripts/zhipu_ocr.py "你的文件.pdf"

# 处理包含图片的目录
python3 scripts/zhipu_ocr.py "你的图片目录"

# 处理单张图片
python3 scripts/zhipu_ocr.py "test.png"
```

## 📝 存储与缓存逻辑
为了提高效率并降低成本，工具采用了完善的缓存机制：
- **最终文档**: `{文件名}_ocr_result.md` 生成在你的当前工作目录 (CWD)。
- **智能缓存**: 处理过程中会生成 `.{文件名}_cache/` 目录，存放每一页的识别结果。
- **断点续传**: 下次运行同一文件时，脚本会**自动跳过**已存在于缓存中的页面。这在处理大型 PDF 时非常有用，既节省了时间也省下了 API 费用。
- **⚠️ 重要提醒**: 请**不要随意删除**缓存目录，除非你想完全重新识别整个文档。如果某个页面识别质量不佳或为空导致的报错，保留缓存可以让你只针对特定页码进行排查，而无需重跑。

## 🛠 技术实现
本项目采用 Python 3 编写，核心逻辑位于 `scripts/zhipu_ocr.py`。它集成了环境预检逻辑，会在运行前自动检查依赖库和当前目录的写权限。

---

## 🛡 License
MIT License
