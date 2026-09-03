// 移植自 docs/gui-reference/theme.reference.ts（MatsuriVoice v0.8.5，官方风格基线）
// 语义色（ok/warn/danger/off/info）按 docs/REMOTE_CONSOLE_REQ.md §4.3
const baseCommon = {
  borderRadius: '10px',
  borderRadiusSmall: '6px',
  fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
}

const THEME_A = {
  key: 'a',
  name: '花信',
  emoji: '🌸',
  dark: false,
  overrides: {
    common: {
      ...baseCommon,
      primaryColor: '#7C6FE8', primaryColorHover: '#9388F2', primaryColorPressed: '#6A5DD9',
      primaryColorSuppl: '#7C6FE8',
      bodyColor: '#F5F5FA', cardColor: '#FFFFFF', modalColor: '#FFFFFF', popoverColor: '#FFFFFF',
      textColorBase: '#2A2A38', textColor1: '#2A2A38', textColor2: '#3D3D4E', textColor3: '#8A8A9E',
      borderColor: '#E8E8F0', dividerColor: '#ECECF4',
      inputColor: '#FFFFFF', tableColor: '#FFFFFF', tableHeaderColor: '#F3F3F9',
    },
    Card: { borderRadius: '12px' },
    Layout: { color: '#F5F5FA', headerColor: '#FFFFFF', siderColor: '#FFFFFF' },
    Menu: {
      itemTextColor: '#3D3D4E', itemColorActive: 'rgba(124,111,232,0.12)',
      itemTextColorActive: '#6A5DD9', itemTextColorHover: '#6A5DD9',
    },
    Button: { borderRadiusTiny: '8px', borderRadiusSmall: '8px', borderRadiusMedium: '10px' },
    Tag: { borderRadiusSmall: '6px' },
  },
  vars: {
    '--mv-bg': '#F5F5FA', '--mv-card': '#FFFFFF', '--mv-text': '#2A2A38', '--mv-text-2': '#8A8A9E',
    '--mv-border': '#E8E8F0', '--mv-primary': '#7C6FE8', '--mv-primary-soft': 'rgba(124,111,232,0.12)',
    '--mv-shadow': '0 4px 16px rgba(42,42,56,0.06)', '--mv-header': '#FFFFFF',
    '--mv-hover': '#F1F1F8', '--mv-gold': '#D9A441',
    '--mv-ok': '#2F9E77', '--mv-warn': '#D9A441', '--mv-danger': '#E5484D',
    '--mv-off': '#9C9CA8', '--mv-info': '#4C8DF5',
  },
}

const THEME_C = {
  key: 'c',
  name: '祭',
  emoji: '🏮',
  dark: true,
  overrides: {
    common: {
      ...baseCommon,
      primaryColor: '#E5484D', primaryColorHover: '#F05A5F', primaryColorPressed: '#D13A3F',
      primaryColorSuppl: '#E5484D',
      bodyColor: '#1B1512', cardColor: '#241C17', modalColor: '#241C17', popoverColor: '#2A211B',
      textColorBase: '#F2E8D9', textColor1: '#F7EFE3', textColor2: '#D9CBB6', textColor3: '#A89882',
      borderColor: 'rgba(217,164,65,0.20)', dividerColor: 'rgba(217,164,65,0.14)',
      inputColor: '#2A211B', tableColor: '#241C17', tableHeaderColor: '#2E251E',
      hoverColor: 'rgba(217,164,65,0.08)',
    },
    Card: { borderRadius: '12px', borderColor: 'rgba(217,164,65,0.18)' },
    Layout: { color: '#1B1512', headerColor: '#1F1814', siderColor: '#1F1814' },
    Menu: {
      itemTextColor: '#D9CBB6', itemColorActive: 'rgba(229,72,77,0.16)',
      itemTextColorActive: '#F05A5F', itemTextColorHover: '#F05A5F',
    },
    Button: { borderRadiusTiny: '8px', borderRadiusSmall: '8px', borderRadiusMedium: '10px' },
    Tag: { borderRadiusSmall: '6px' },
  },
  vars: {
    '--mv-bg': '#1B1512', '--mv-card': '#241C17', '--mv-text': '#F2E8D9', '--mv-text-2': '#A89882',
    '--mv-border': 'rgba(217,164,65,0.20)', '--mv-primary': '#E5484D',
    '--mv-primary-soft': 'rgba(229,72,77,0.16)',
    '--mv-shadow': '0 4px 18px rgba(0,0,0,0.35)', '--mv-header': '#1F1814',
    '--mv-hover': 'rgba(217,164,65,0.08)', '--mv-gold': '#D9A441',
    '--mv-ok': '#4CC38A', '--mv-warn': '#E4B65B', '--mv-danger': '#F05A5F',
    '--mv-off': '#7A6F63', '--mv-info': '#6FA6F7',
  },
}

export const THEMES = [THEME_A, THEME_C]

export function getTheme(key) {
  return THEMES.find((t) => t.key === key) ?? THEMES[0]
}

export function applyThemeVars(theme) {
  const root = document.documentElement
  for (const [k, v] of Object.entries(theme.vars)) root.style.setProperty(k, v)
  document.body.style.background = theme.vars['--mv-bg']
}