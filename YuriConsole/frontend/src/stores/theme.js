// 移植自 docs/gui-reference/theme-store.reference.ts：主题切换 + localStorage 持久化
import { defineStore } from 'pinia'
import { applyThemeVars, getTheme } from '../theme'

const STORAGE_KEY = 'mv-theme'

function initialKey() {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'c' ? 'c' : 'a'
  } catch {
    return 'a'
  }
}

export const useThemeStore = defineStore('theme', {
  state: () => ({ themeKey: initialKey() }),
  getters: {
    theme: (state) => getTheme(state.themeKey),
  },
  actions: {
    init() {
      applyThemeVars(this.theme)
    },
    set(key) {
      this.themeKey = key
      try { localStorage.setItem(STORAGE_KEY, key) } catch { /* in-memory */ }
      applyThemeVars(this.theme)
    },
  },
})