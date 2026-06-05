# Branding 文件处理工具调研计划

## 目标

对 `/Volumes/databoard/AI Project/ciosh/Branding/` 下的文件进行分析，调研：
1. 适合 AI Agent 调用的 MCP 插件或工具，用于打开/处理 .ai / .eps 格式文件
2. GitHub 上 Adobe Illustrator 的开源平替软件

---

## 一、现状：文件清单

| 文件 | 大小 | 格式 | 说明 |
|------|------|------|------|
| `CIOSH 2026 SH KV 横版加60_0121.eps` | 59 MB | EPS | Encapsulated PostScript |
| `CIOSH 2026 SH KV 竖版加60_0121.eps` | 25 MB | EPS | Encapsulated PostScript |
| `CIOSH-1966.ai` | 1.6 MB | AI | Adobe Illustrator 原生格式 |
| `In partnership with A+A.ai` | 505 KB | AI | Adobe Illustrator 原生格式 |
| `劳保会IP吉祥物 转曲.ai` | 1.9 MB | AI | Adobe Illustrator 原生格式（已转曲） |

核心问题：.ai 文件是 Adobe 私有二进制格式（部分为 PDF 容器封装）；.eps 是 PostScript 格式，但渲染需要解析器。

---

## 二、AI Agent 可调用的 MCP / CLI 工具

### 2.1 现有 Hermes 能力

- **OpenCLI** 无直接适配 Adobe 文件格式的 adapter
- **browser** 工具只能处理网页内容，无法解析 .ai/.eps 二进制文件
- **vision_analyze** 可配合截屏分析渲染后的图像，但无法直接读取文件内容
- **native-mcp**（Hermes 内置 MCP 客户端）可对接外部 MCP Server

### 2.2 适用于 AI Agent 的 MCP Server

| MCP Server | 适用性 | 说明 |
|------------|--------|------|
| **Figma MCP Server** (github.com/mcp/com.figma.mcp/mcp) | 间接可用 | Figma 可导入 .ai 文件再通过 API 读取，但需要先手动上传 |
| **File System MCP** | 不直接支持 | 只能读写文本文件，无法解析 .ai/.eps 二进制内容 |

**结论**: 目前 MCP 生态中暂无专门处理 Adobe 矢量格式的 MCP Server。

### 2.3 CLI 工具（可被 AI Agent 通过 terminal 调用）

| 工具 | 安装 | 可处理 AI | 可处理 EPS | 输出格式 | 能力 |
|------|------|-----------|-----------|----------|------|
| **Inkscape CLI** | `brew install inkscape` | 有限支持（导入） | 原生支持 | SVG, PNG, PDF | `inkscape --without-gui --export-filename=output.svg input.ai` |
| **Ghostscript (gs)** | `brew install ghostscript` | 不支持 | 原生支持 | PDF, PNG | `gs -dNOPAUSE -dBATCH -sDEVICE=pdfwrite -sOutputFile=out.pdf input.eps` |
| **pstoedit** | `brew install pstoedit` | 不支持 | 原生支持 | SVG, PDF 等 | `pstoedit -f plot-svg input.eps output.svg` |
| **libpostscript + rsvg-convert** | `brew install librsvg` | 不支持 | 有限支持 | SVG, PNG | `rsvg-convert -f svg -o output.svg input.eps` |
| **ImageMagick** | `brew install imagemagick` | 有限（需 ghostscript） | 支持（需 ghostscript） | PNG, PDF | `convert input.eps output.png` |

**推荐路径**: Inkscape CLI + Ghostscript 组合，可以覆盖 .ai 和 .eps 两种格式。

### 2.4 替代方案：文件格式转换后再处理

```
.ai/.eps → [Inkscape CLI] → SVG → Python (svgwrite/svgpathtools/cairosvg) → 提取/修改
```

**Python 库选项**:

| 库 | 用途 |
|----|------|
| `svgpathtools` | 解析 SVG 路径，提取矢量数据 |
| `cairosvg` | SVG 转 PNG/PDF |
| `svgelements` | 解析 SVG 元素结构 |
| `reportlab` | 读取 EPS（有限支持） |
| `ezdxf` | DXF 相关（非本场景） |

---

## 三、GitHub 开源 Illustrator 平替（供人类设计师使用）

| 项目 | Stars | 平台 | 说明 |
|------|-------|------|------|
| **[Inkscape](https://gitlab.com/inkscape/inkscape)** (GitHub mirror: 3.4k ★) | 3.4k+ | Win/Mac/Linux | **#1 开源矢量编辑器**，原生 SVG，支持导入 AI/EPS |
| **[Penpot](https://github.com/penpot/penpot)** | 35k+ ★ | Web | 开源 Figma/Illustrator 替代，矢量设计+原型，可导入 SVG |
| **[Boxy SVG](https://boxy-svg.com/)** (not fully open source) | - | Web/Desktop | 轻量 SVG 编辑器，UI 类似 Illustrator |
| **[macSVG](https://github.com/dsward2/macSVG)** | 1.3k ★ | macOS | 原生 macOS SVG 编辑器，Swift/ObjC 编写 |
| **[SVG-Edit](https://github.com/SVG-Edit/svgedit)** | 6.1k ★ | Web | 纯浏览器 SVG 编辑器，无需后端 |
| **[repath-studio](https://github.com/repath-studio/repath-studio)** | 158 ★ | Web | 结合过程化工具和传统设计工作流的矢量编辑器 |
| **[Gravit Designer](https://www.designer.io/)** | - | Web/Desktop | 免费矢量编辑器，UI 类似 AI |

**最推荐**: **Inkscape** — 功能最接近 Illustrator，支持 .ai 导入和 .eps 原生读写，有 CLI 可被 AI Agent 调用，macOS 可通过 Homebrew 安装。

**次推荐**: **Penpot** — 如果你需要基于 Web 的协作设计工具，开源 Figma 替代品，适合团队使用。

---

## 四、建议实施步骤

### Phase 1: 环境搭建与格式转换
1. 安装 Inkscape CLI：`brew install inkscape`
2. 安装 Ghostscript：`brew install ghostscript`
3. 测试用 Inkscape CLI 将 .ai 文件转换为 SVG
4. 测试用 Ghostscript 将 .eps 文件转换为 PDF/SVG

### Phase 2: AI Agent 集成
1. 将 Inkscape CLI 命令封装为 Hermes Skill，通过 terminal 调用
2. 转换后的 SVG 由 Python 库（svgpathtools）解析，提取矢量内容
3. 如需视觉验证，将 SVG 通过 cairosvg 转为 PNG 后用 vision_analyze 查看

### Phase 3: 人工编辑工具
1. 为设计师安装 Inkscape（macOS GUI 版）
2. 或使用 Penpot 进行在线协作编辑
3. 关键修改后导出回 SVG/AI/EPS 格式

---

## 五、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| Inkscape 导入 AI 文件可能丢失部分效果（渐变、蒙版、文字） | 高 | 请设计师用 Adobe 软件检查关键内容 |
| EPS 文件中的嵌入字体可能不一致 | 中 | 确保矢量文件中文字已转曲（你已有的文件标注"转曲"） |
| 59MB EPS 文件渲染性能 | 中 | 使用 Ghostscript 先做 subset |
| 缺少专用于 Adobe 格式的 MCP Server | 中 | 可考虑自建 MCP server 封装 Inkscape CLI |
| 部分 .ai 文件是新版 Illustrator 格式 | 低 | 需确认文件版本（Inkscape 不支持最新 AI 格式） |

## 六、开放问题

1. 你需要 AI Agent 具体对这些文件做什么？（查看内容、修改、还是生成代码？）
2. 是否需要部署一个专用 MCP Server 把 Inkscape CLI 封装成工具？
3. 设计师团队是否有使用 Inkscape 的意愿，还是坚持 Adobe 生态？
4. 是否需要批量处理脚本？
