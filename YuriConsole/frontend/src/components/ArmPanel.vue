<template>
  <n-space vertical :size="10">
    <n-space align="center" size="small">
      <n-switch v-model:value="armOn" size="small" :disabled="!store.state.connected" @update:value="store.setArmEnabled" />
      <span>机械臂遥操作（teleop_joints 直写）</span>
      <StatusDot :level="armLevel" />
      <n-tag v-if="store.state.arm_pad_enabled" type="warning" size="small" :bordered="false">手柄控臂中（leader 已暂停）</n-tag>
    </n-space>
    <p class="hint" style="margin:0">手握主动臂 → 从动臂实时跟随；或切到 C 区手柄、把右摇杆设为“控制机械臂”以手柄直控（shoulder_pan/lift，速率模式，自动暂停 leader）。</p>
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