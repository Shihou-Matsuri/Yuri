// MatsuriVoice「花信 / 祭」主题令牌 -> naive-ui themeOverrides（规范见 docs/REMOTE_CONSOLE_REQ.md 4.1）
export const themes = {
  light: {
    key: 'light',
    label: '花信',
    // CSS 变量（body 级，供自定义样式使用）
    css: {
      '--bg': '#F5F5FA', '--card': '#FFFFFF', '--text': '#2A2A38', '--text-2': '#8A8A9E',
      '--border': '#E8E8F0', '--primary': '#7C6FE8', '--primary-soft': 'rgba(124,111,232,0.12)',
      '--gold': '#D9A441', '--ok': '#2F9E77', '--warn': '#D9A441', '--danger': '#E5484D',
      '--off': '#9C9CA8', '--info': '#4C8DF5',
    },
    naive: {
      common: {
        primaryColor: '#7C6FE8', primaryColorHover: '#8E83EC', primaryColorPressed: '#6A5CD6',
        primaryColorSuppl: '#7C6FE8', infoColor: '#4C8DF5', successColor: '#2F9E77',
        warningColor: '#D9A441', errorColor: '#E5484D', borderRadius: '10px',
        bodyColor: '#F5F5FA', cardColor: '#FFFFFF', modalColor: '#FFFFFF',
        textColorBase: '#2A2A38', textColor1: '#2A2A38', textColor2: '#4A4A5A',
        borderColor: '#E8E8F0', dividerColor: '#ECECF2', tableHeaderColor: '#F5F5FA',
      },
    },
  },
  dark: {
    key: 'dark',
    label: '祭',
    css: {
      '--bg': '#1B1512', '--card': '#241C17', '--text': '#F2E8D9', '--text-2': '#A89882',
      '--border': 'rgba(217,164,65,0.20)', '--primary': '#E5484D', '--primary-soft': 'rgba(229,72,77,0.16)',
      '--gold': '#D9A441', '--ok': '#4CC38A', '--warn': '#E4B65B', '--danger': '#F05A5F',
      '--off': '#7A6F63', '--info': '#6FA6F7',
    },
    naive: {
      common: {
        primaryColor: '#E5484D', primaryColorHover: '#F05A5F', primaryColorPressed: '#C93B40',
        primaryColorSuppl: '#E5484D', infoColor: '#6FA6F7', successColor: '#4CC38A',
        warningColor: '#E4B65B', errorColor: '#F05A5F', borderRadius: '10px',
        bodyColor: '#1B1512', cardColor: '#241C17', modalColor: '#241C17',
        textColorBase: '#F2E8D9', textColor1: '#F2E8D9', textColor2: '#A89882',
        borderColor: 'rgba(217,164,65,0.20)', dividerColor: 'rgba(217,164,65,0.12)',
        tableHeaderColor: '#1F1814',
      },
    },
  },
}