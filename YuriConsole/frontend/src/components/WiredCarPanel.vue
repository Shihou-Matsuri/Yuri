<template>
  <n-space vertical :size="8">
    <n-space align="center" size="small">
      <n-select
        v-model:value="store.wiredPort"
        :options="portOptions"
        placeholder="COM21"
        style="width: 130px"
        size="small"
      />
      <n-button size="small" secondary @click="doRefreshPorts">刷新</n-button>
      <n-button v-if="!store.state.wired.connected" type="primary" size="small" :loading="busy" @click="doConnect">
        连接
      </n-button>
      <n-button v-else size="small" secondary @click="store.wiredDisconnect">断开</n-button>
      <StatusDot :level="level" />
      <span class="hint">{{ hintText }}</span>
    </n-space>

    <n-space align="center" size="small">
      <span class="hint">输入源</span>
      <n-radio-group v-model:value="inputMode" size="small">
        <n-radio-button value="keys">键盘</n-radio-button>
        <n-radio-button value="gamepad">手柄</n-radio-button>
      </n-radio-group>
      <n-radio-group v-model:value="store.carMode" size="small" @update:value="store.setCarMode">
        <n-radio-button value="lock">点按锁定</n-radio-button>
        <n-radio-button value="hold">按住移动</n-radio-button>
      </n-radio-group>
      <StatusDot :level="padLevel" />
      <span class="hint">{{ padText }}</span>
    </n-space>

    <div class="pad" :style="{ opacity: inputMode === 'keys' ? 1 : 0.55 }">
      <span />
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('w')" @pointerup="maybeRelease" @pointerleave="maybeRelease" @pointercancel="maybeRelease">前 W</button>
      <span />
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('a')" @pointerup="maybeRelease" @pointerleave="maybeRelease" @pointercancel="maybeRelease">左 A</button>
      <button :disabled="inputMode !== 'keys'" class="stop-btn" @pointerdown="store.wiredRelease">停 空格</button>
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('d')" @pointerup="maybeRelease" @pointerleave="maybeRelease" @pointercancel="maybeRelease">右 D</button>
      <span />
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('s')" @pointerup="maybeRelease" @pointerleave="maybeRelease" @pointercancel="maybeRelease">后 S</button>
      <span />
    </div>
    <div class="pad" style="grid-template-columns:repeat(2,96px)" :style="{ opacity: inputMode === 'keys' ? 1 : 0.55 }">
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('z')" @pointerup="maybeRelease" @pointerleave="maybeRelease" @pointercancel="maybeRelease">左旋 Z</button>
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('x')" @pointerup="maybeRelease" @pointerleave="maybeRelease" @pointercancel="maybeRelease">右旋 X</button>
    </div>

    <n-space align="center" size="small">
      <n-button type="error" size="small" @click="store.wiredEstop">急停（停+扭矩关）</n-button>
      <span class="hint">{{ motionText }}</span>
    </n-space>
    <p class="hint" style="margin:0">
      有线相机小车：USB 直连 Feetech（三轮 ID5/6/4，默认 COM21 @1M），与上方 ESP32 无线链路互相独立。
      操作方式沿用上方选择（点按锁定/按住）。键盘方向作用于无线小车区，本区请用按钮。E 后按方向自动恢复扭矩。
    </p>
  </n-space>
</template>
<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()
const busy = ref(false)
const inputMode = ref('keys')
const padConnected = ref(false)
let padWasConnected = false
let padTimer = null
const isLock = computed(() => store.carMode === 'lock')
const portOptions = computed(() => store.wiredPorts.map((port) => ({ label: port, value: port })))
const CAR_LIMITS = { linear: 0.05, angular: 0.30 }
const DEADZONE = 0.12

function dz(v) { return Math.abs(v) < DEADZONE ? 0 : v }

async function doConnect() {
  busy.value = true
  const r = await store.wiredConnect()
  busy.value = false
  if (!r.ok) console.error('wired connect failed:', r.msg)
}
async function doRefreshPorts() { await store.wiredRefreshPorts() }
function press(key) {
  if (inputMode.value === 'keys' && store.state.wired.connected) store.wiredPress(key)
}
function maybeRelease() {
  if (inputMode.value === 'keys' && store.state.wired.connected && !isLock.value) store.wiredRelease()
}

async function pollGamepad() {
  if (inputMode.value !== 'gamepad' || !store.state.wired.connected) return
  const gp = await store.gamepadState()
  padConnected.value = gp.connected
  if (!gp.connected) {
    if (padWasConnected) store.wiredVel(0, 0, 0)
    padWasConnected = false
    return
  }
  padWasConnected = true
  if (gp.buttons && gp.buttons.b) {
    store.wiredEstop()
    return
  }
  if (gp.buttons && gp.buttons.a) {
    store.wiredRelease()
    return
  }
  const lx = dz(gp.left_x || 0)
  const ly = dz(gp.left_y || 0)
  const rx = dz(gp.right_x || 0)
  const vx = -ly * CAR_LIMITS.linear
  const vy = -lx * CAR_LIMITS.linear
  const omega = -rx * CAR_LIMITS.angular
  store.wiredVel(vx, vy, omega)
}

onMounted(() => {
  store.wiredRefreshPorts()
  padTimer = setInterval(pollGamepad, 33)
})
onBeforeUnmount(() => {
  clearInterval(padTimer)
  if (inputMode.value === 'gamepad') store.wiredVel(0, 0, 0)
})

const level = computed(() => store.state.wired.connected ? (store.state.wired.torque_on ? 'ok' : 'warn') : 'off')
const hintText = computed(() => {
  if (!store.state.wired.connected) return '未连接（有线相机小车）'
  const t = store.state.wired.torque_on ? '扭矩开' : '扭矩关'
  return `${store.state.wired.port} 已连接 · ${t}`
})
const motionText = computed(() => store.state.wired.motion ? `运行: ${store.state.wired.motion}` : '停')
const padLevel = computed(() => (padConnected.value ? 'ok' : 'off'))
const padText = computed(() => padConnected.value
  ? '左摇杆移动 · 右摇杆转向 · A 停 · B 急停'
  : '未检测到手柄：运行窗口内使用手柄模式，前后端会持续读取')
</script>
