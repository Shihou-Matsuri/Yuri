<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { darkTheme } from 'naive-ui'
import { useConsole } from './stores/console'
import { useThemeStore } from './stores/theme'
import { THEMES } from './theme'
import StatusDot from './components/StatusDot.vue'
import ConnectionPanel from './components/ConnectionPanel.vue'
import ArmPanel from './components/ArmPanel.vue'
import CarPanel from './components/CarPanel.vue'
import VisionPanel from './components/VisionPanel.vue'
import SafetyLogPanel from './components/SafetyLogPanel.vue'

const consoleStore = useConsole()
const themeStore = useThemeStore()
themeStore.init()

const themeBase = computed(() => (themeStore.theme.dark ? darkTheme : null))
const themeOverrides = computed(() => themeStore.theme.overrides)
const topLevel = computed(() => consoleStore.state.global_estop ? 'danger'
  : consoleStore.state.connected ? (consoleStore.state.car_estop ? 'warn' : 'ok') : 'off')
const topText = computed(() => {
  if (consoleStore.state.mock) return 'mock 模式'
  if (!consoleStore.state.connected) return '未连接'
  return consoleStore.state.link + (consoleStore.state.global_estop ? ' · 急停' : '')
})

let timer = null
onMounted(() => {
  consoleStore.refresh(); consoleStore.refreshLogs()
  timer = setInterval(() => { consoleStore.refresh(); consoleStore.refreshLogs() }, 600)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <n-config-provider :theme="themeBase" :theme-overrides="themeOverrides">
    <n-layout style="height: 100vh">
      <n-layout-header
        bordered
        style="display: flex; align-items: center; padding: 0 20px; height: 52px; background: var(--mv-header)"
      >
        <div style="display: flex; align-items: center; margin-right: 24px; gap: 8px">
          <span style="width: 10px; height: 10px; border-radius: 50%;
            background: var(--mv-primary); box-shadow: 0 0 10px var(--mv-primary)" />
          <span style="font-weight: 700; font-size: 16px; color: var(--mv-text); letter-spacing: 0.5px">
            Yuri 遥控台
          </span>
          <span style="font-size: 11px; color: var(--mv-text-2); margin-top: 2px">机械臂 · 小车 · 视觉</span>
        </div>

        <div style="display: flex; align-items: center; gap: 10px; flex: 1; justify-content: flex-end">
          <n-tag v-if="consoleStore.state.mock" size="small" type="warning" :bordered="false">mock</n-tag>
          <n-tag v-else-if="consoleStore.state.connected" size="small" type="success" :bordered="false">真机</n-tag>
          <StatusDot :level="topLevel" />
          <span class="hint">{{ topText }}</span>
          <n-button v-if="consoleStore.state.connected" size="small" secondary @click="consoleStore.disconnect">
            断开
          </n-button>
          <n-button type="error" strong secondary size="small" @click="consoleStore.globalEstop">全局急停</n-button>
          <n-button size="small" @click="consoleStore.resume">恢复</n-button>
          <n-space :size="4" style="margin-left: 8px">
            <n-button
              v-for="t in THEMES" :key="t.key" size="small" quaternary
              :type="themeStore.themeKey === t.key ? 'primary' : 'default'"
              @click="themeStore.set(t.key)"
            >
              {{ t.emoji }} {{ t.name }}
            </n-button>
          </n-space>
        </div>
      </n-layout-header>

      <n-layout-content content-style="padding: 18px 20px; max-width: 1180px; margin: 0 auto">
        <n-collapse :default-expanded-names="['A','B','C','E']" arrow-placement="right">
          <n-collapse-item title="A · 连接与状态" name="A"><ConnectionPanel /></n-collapse-item>
          <n-collapse-item title="B · 机械臂" name="B"><ArmPanel /></n-collapse-item>
          <n-collapse-item title="C · 小车" name="C"><CarPanel /></n-collapse-item>
          <n-collapse-item title="D · 视觉（YuriEye）" name="D"><VisionPanel /></n-collapse-item>
          <n-collapse-item title="E · 安全与日志" name="E"><SafetyLogPanel /></n-collapse-item>
        </n-collapse>
      </n-layout-content>
    </n-layout>
  </n-config-provider>
</template>