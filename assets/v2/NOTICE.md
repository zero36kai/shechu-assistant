# 美术来源与许可

源码的 MIT 许可证不授予第三方角色设计、商标或原始美术的权利。八位角色为社区非官方 AI 拟人同人，不代表相关公司或模型的官方形象。

## 来源与署名

实际图生图参考来自 [蓝色大肥鱼档案馆角色页](https://fisharchive.cc/characters)。各参考图的下载地址、尺寸和 SHA-256 见 [sources/manifest.json](sources/manifest.json)。本仓库不包含原始参考图。

档案馆[关于页](https://fisharchive.cc/about)与[项目说明](https://github.com/EDMOK/blue-fish-archive)列出的署名包括：

- 原作：上善无形，https://space.bilibili.com/4456176 。
- DeepSeek 元素二次设计：ZipZipPipe，https://space.bilibili.com/4168597 。
- 档案整理与网站：EDMOK，https://github.com/EDMOK ，https://space.bilibili.com/291892724 。

以上为来源页已明确列出的署名，并不表示三位参与了每一个角色或每一帧的制作。各角色设计的权利仍归相应创作者；请同时保留来源页中适用的作者标注。

另曾参考 [chatgpt-chibi-pets](https://github.com/fywdy/chatgpt-chibi-pets) 和 [ai-girls](https://github.com/shuaizenge/ai-girls) 的表现形式；未复制这两个项目的动画帧。

## 修改与运行素材

2026 年由 zero36kai 的项目使用皮皮智绘 image-1 图生图 API，基于上述八张参考设计重新生成动作图集；随后拆帧、去背景、对齐共同画布与脚底，并编写动画时序。运行目录 `characters/` 包含肖像、动画清单及共 125 张不同像素帧，单帧为 400×480 RGBA。

每位角色包含待机眨眼、挥手、饮水和伸展四种状态。这些是有限帧动画，不是骨骼动画或视频生成。DeepSeek 饮水前三张生成帧存在多手瑕疵，未纳入运行清单；该动作使用正常待机帧和正常饮水帧组成两帧短动作。

`bubble.png` 是同次 API 新生成并去背景的空白气泡。文字与按钮由 Qt 动态绘制，不在图片内。README 及 `docs/evidence/` 中的提醒预览由这些素材和实际控件离屏导出。

## 许可证范围

档案馆声明采用 **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International（CC BY-NC-SA 4.0）**。本仓库在该条件下分发角色衍生素材及包含它们的预览：保留署名、来源和修改说明，仅限非商业使用，改编后以相同许可证共享。气泡也按相同条件提供。

完整文本见 [LICENSES/CC-BY-NC-SA-4.0.txt](../../LICENSES/CC-BY-NC-SA-4.0.txt)，协议页面为 https://creativecommons.org/licenses/by-nc-sa/4.0/ 。上述许可不表示取得商标、肖像或其他独立权利的授权。源码 MIT 与美术 CC BY-NC-SA 4.0 分别适用。
