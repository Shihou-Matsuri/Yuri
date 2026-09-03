# GUI 风格参考（MatsuriVoice 母版）

> 用途：Yuri 综合遥控台（U2）实现时的官方风格参考。
> 母版仓库：`Shihou-Matsuri/MatsuriVoice`（前端 `frontend/src/`，截至 v0.8.5）。
> 规则：以本目录为参考基线；如与母版冲突，按母版 `frontend/src/theme.ts` 实际值修正。

## 文件

| 文件 | 来源（MatsuriVoice） | 用途 |
|---|---|---|
| `theme.reference.ts` | `frontend/src/theme.ts` | 双主题令牌（花信 A / 祭 C）、情绪 8 色板、CSS 变量 |
| `base.reference.css` | `frontend/src/style.css` | 全局底色/滚动条/通用微交互 |
| `theme-store.reference.ts` | `frontend/src/stores/theme.ts` | 主题切换状态与持久化模式（`localStorage`） |
| `samples/app-shell.reference.vue` | `frontend/src/App.vue` | 顶栏 + 服务状态点 + 主题切换 + 布局骨架 |
| `samples/status-dots.reference.vue` | `frontend/src/components/ServiceDots.vue` | 状态点颜色/辉光/点击跳转写法 |
| `samples/card-grid.reference.vue` | `frontend/src/views/ProjectsView.vue` | 卡片网格 + 空态 + 弹窗按钮样板 |

## 移植注意

- 文件仅作为样式/交互参考；遥控台业务组件不要直接复制母版项目逻辑。
- 主题统一走 `--mv-*` 变量；`NConfigProvider` 的 `theme-overrides` 与 CSS 变量双轨同步。
- 主题切换动作：`applyThemeVars` 写 `document.documentElement` + `document.body.style.background`；
  遥控台实现应提供等价浅/深主题结构。
- 母版字体为 `Segoe UI / PingFang SC / Microsoft YaHei`；遥控台沿用同字体族。
- 遥控台语义色（就绪/警告/危险/离线）见 `REMOTE_CONSOLE_REQ.md` §4.3，不直接照搬 TTS 服务状态色。

