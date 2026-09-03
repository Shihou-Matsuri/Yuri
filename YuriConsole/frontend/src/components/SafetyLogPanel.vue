<template>
  <n-space vertical :size="8">
    <n-space align="center" size="small">
      <n-button type="error" size="small" @click="store.globalEstop">全局急停</n-button>
      <n-button size="small" @click="store.resume">恢复 resume</n-button>
      <StatusDot :level="stLevel" />
      <span class="hint">{{ stText }}</span>
    </n-space>
    <n-radio-group v-model:value="store.logFilter" size="small" @update:value="store.refreshLogs">
      <n-radio-button value="all">全部</n-radio-button>
      <n-radio-button value="info">连接/指令</n-radio-button>
      <n-radio-button value="warn">警告</n-radio-button>
      <n-radio-button value="error">错误</n-radio-button>
    </n-radio-group>
    <div class="loglist">
      <div v-for="(lg, i) in store.logs" :key="i" class="logline" :class="'lv-' + lg.level">
        [{{ lg.t }}] {{ lg.level.toUpperCase() }} {{ lg.msg }}
      </div>
      <div v-if="!store.logs.length" class="hint">暂无日志</div>
    </div>
  </n-space>
</template>
<script setup>
import { computed } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()
const stLevel = computed(() => store.state.global_estop ? 'danger'
  : store.state.connected ? (store.state.car_estop ? 'warn' : 'ok') : 'off')
const stText = computed(() => {
  if (store.state.global_estop) return '全局急停生效中'
  if (!store.state.connected) return '未连接'
  return '链路正常 · 心跳由 20Hz 主循环喂狗'
})
</script>