<template>
  <n-space vertical :size="10">
    <n-space align="center" size="small">
      <n-switch v-model:value="armOn" size="small" :disabled="!store.state.connected" @update:value="store.setArmEnabled" />
      <span>机械臂遥操作（teleop_joints 直写）</span>
      <StatusDot :level="armLevel" />
    </n-space>
    <p class="hint" style="margin:0">手握主动臂 → 从动臂实时跟随；急停/看门狗语义与 CLI 一致。首版不在桥模式下手动步进（保留 leader_remote 单控）。</p>
    <div v-if="Object.keys(store.state.positions || {}).length" class="readouts">
      <span v-for="(v, k) in store.state.positions" :key="k" class="ro">{{ k }} <b>{{ v.toFixed(1) }}</b></span>
    </div>
  </n-space>
</template>
<script setup>
import { computed } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()
const armOn = computed({
  get: () => store.state.arm_enabled,
  set: (v) => store.setArmEnabled(v),
})
const armLevel = computed(() => store.state.global_estop ? 'danger'
  : store.state.arm_enabled && store.state.connected ? 'ok' : 'off')
</script>