<template>
  <n-space vertical :size="10">
    <div class="conn-row">
      <n-radio-group v-model:value="store.linkSel" size="small">
        <n-radio-button value="tcp">WiFi TCP</n-radio-button>
        <n-radio-button value="serial">USB 串口</n-radio-button>
      </n-radio-group>
      <n-input v-if="store.linkSel === 'serial'" v-model:value="store.serialPort" placeholder="COM8" style="width: 90px" size="small" />
      <n-input v-model:value="store.leaderPort" placeholder="主动臂口" style="width: 110px" size="small">
        <template #prefix>臂</template>
      </n-input>
      <n-button v-if="!store.state.connected" type="primary" size="small" :loading="busy" @click="doConnect">连接</n-button>
      <n-button v-else type="warning" secondary size="small" @click="store.disconnect">断开</n-button>
    </div>
    <n-space align="center" size="small">
      <StatusDot :level="level" />
      <span class="hint">{{ hint }}</span>
    </n-space>
    <div class="readouts">
      <span class="ro">链路 <b>{{ store.state.link || '—' }}</b></span>
      <span class="ro">主动臂 <b>{{ store.state.leader_port }}</b></span>
      <span class="ro">轮速 <b>{{ store.state.wheel_speed ?? '—' }}</b></span>
      <span v-if="store.state.positions && Object.keys(store.state.positions).length" class="ro">
        姿态 <b>{{ Object.values(store.state.positions).map(v => v.toFixed(1)).join(' / ') }}</b>
      </span>
    </div>
  </n-space>
</template>
<script setup>
import { computed, ref } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()
const busy = ref(false)
const level = computed(() => store.state.global_estop ? 'danger'
  : store.state.connected ? (store.state.car_estop ? 'warn' : 'ok') : 'off')
const hint = computed(() => {
  if (store.state.mock) return 'mock 离线演示（无硬件）'
  if (!store.state.connected) return '未连接（ESP32：WiFi YuriArm-AP 或 USB 串口）'
  return `已连接 ${store.state.link}` + (store.state.global_estop ? ' · 全局急停中' : '')
})
async function doConnect() {
  busy.value = true
  const r = await store.connect()
  busy.value = false
  if (!r.ok) console.error('connect failed:', r.msg)
}
</script>