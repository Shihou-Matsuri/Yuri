<template>
  <n-config-provider :theme="themeBase" :theme-overrides="themeOverrides">
    <div class="shell" :data-theme="themeKey">
      <!-- 顶栏 56px：连接状态 + 全局安全（急停恒可见）+ 主题切换 -->
      <header class="topbar">
        <div class="brand">
          <span class="logo-dot" />
          <span class="title">Yuri 综合遥控台</span>
          <n-tag v-if="store.state.mock" size="small" type="warning" :bordered="false">mock</n-tag>
          <n-tag v-else-if="store.state.connected" size="small" type="success" :bordered="false">真机</n-tag>
          <n-tag v-else size="small" :bordered="false">未连接</n-tag>
        </div>
        <div class="top-actions">
          <StatusDot :level="topLevel" />
          <span class="hint">{{ topText }}</span>
          <n-button v-if="store.state.connected" size="small" secondary @click="store.disconnect">断开</n-button>
          <n-button type="error" strong secondary size="small" @click="store.globalEstop">全局急停</n-button>
          <n-button size="small" @click="store.resume">恢复</n-button>
          <n-switch v-model:value="dark" size="small">
            <template #checked>祭</template>
            <template #unchecked>花信</template>
          </n-switch>
        </div>
      </header>

      <!-- 五区（A–E）可折叠卡片 -->
      <n-collapse class="zones" :default-expanded-names="['A','B','C','E']" arrow-placement="right">
        <n-collapse-item title="A · 连接与状态" name="A"><ConnectionPanel /></n-collapse-item>
        <n-collapse-item title="B · 机械臂" name="B"><ArmPanel /></n-collapse-item>
        <n-collapse-item title="C · 小车" name="C"><CarPanel /></n-collapse-item>
        <n-collapse-item title="D · 视觉（YuriEye）" name="D"><VisionPanel /></n-collapse-item>
        <n-collapse-item title="E · 安全与日志" name="E"><SafetyLogPanel /></n-collapse-item>
      </n-collapse>
    </div>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { darkTheme } from 'naive-ui'
import { themes } from './theme'
import { useConsole } from './stores/console'
import StatusDot from './components/StatusDot.vue'
import ConnectionPanel from './components/ConnectionPanel.vue'
import ArmPanel from './components/ArmPanel.vue'
import CarPanel from './components/CarPanel.vue'
import VisionPanel from './components/VisionPanel.vue'
import SafetyLogPanel from './components/SafetyLogPanel.vue'

const store = useConsole()
const dark = ref(false)
const themeKey = computed(() => (dark.value ? 'dark' : 'light'))
const themeBase = computed(() => (dark.value ? darkTheme : null))
const themeOverrides = computed(() => themes[themeKey.value].naive)
const topLevel = computed(() => store.state.global_estop ? 'danger'
  : store.state.connected ? (store.state.car_estop ? 'warn' : 'ok') : 'off')
const topText = computed(() => {
  if (store.state.mock) return 'mock 模式'
  if (!store.state.connected) return '未连接'
  return store.state.link + (store.state.global_estop ? ' · 急停' : '')
})

let timer = null
onMounted(() => {
  store.refresh(); store.refreshLogs()
  timer = setInterval(() => { store.refresh(); store.refreshLogs() }, 600)
})
onBeforeUnmount(() => clearInterval(timer))
</script>