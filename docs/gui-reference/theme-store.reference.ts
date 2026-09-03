import { defineStore } from "pinia";
import { applyThemeVars, getTheme, type MvTheme } from "../theme";

const STORAGE_KEY = "mv-theme";
export type ThemeKey = "a" | "c";

function initialKey(): ThemeKey {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "c" ? "c" : "a";
  } catch {
    return "a";
  }
}

export const useThemeStore = defineStore("theme", {
  state: () => ({
    themeKey: initialKey() as ThemeKey,
  }),
  getters: {
    theme(): MvTheme {
      return getTheme(this.themeKey);
    },
  },
  actions: {
    init() {
      applyThemeVars(this.theme);
    },
    set(key: ThemeKey) {
      this.themeKey = key;
      try {
        localStorage.setItem(STORAGE_KEY, key);
      } catch {
        /* keep in-memory */
      }
      applyThemeVars(this.theme);
    },
  },
});
