<template>
  <n-space vertical :size="8">
    <n-space align="center" size="small">
      <span class="hint">输入源</span>
      <n-radio-group v-model:value="inputMode" size="small">
        <n-radio-button value="keys">键盘 / 按钮</n-radio-button>
        <n-radio-button value="gamepad">手柄</n-radio-button>
      </n-radio-group>
      <span class="hint">操作方式</span>
      <n-radio-group v-model:value="store.carMode" size="small" @update:value="store.setCarMode">
        <n-radio-button value="lock">点按锁定</n-radio-button>
        <n-radio-button value="hold">按住移动</n-radio-button>
      </n-radio-group>
      <template v-if="inputMode === 'gamepad'">
        <StatusDot :level="padLevel" />
        <span class="hint">{{ padText }}</span>
      </template>
    </n-space>

    <div class="pad" :style="{ opacity: inputMode === 'keys' ? 1 : 0.45 }">
      <span />
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('w')" @pointerup="maybeRelease" @pointerleave="maybeRelease">前 W</button>
      <span />
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('a')" @pointerup="maybeRelease" @pointerleave="maybeRelease">左 A</button>
      <button class="stop-btn" :disabled="inputMode !== 'keys'" @pointerdown="doStop">停 空格</button>
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('d')" @pointerup="maybeRelease" @pointerleave="maybeRelease">右 D</button>
      <span />
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('s')" @pointerup="maybeRelease" @pointerleave="maybeRelease">后 S</button>
      <span />
    </div>
    <div class="pad" style="grid-template-columns:repeat(2,96px)" :style="{ opacity: inputMode === 'keys' ? 1 : 0.45 }">
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('z')" @pointerup="maybeRelease" @pointerleave="maybeRelease">左旋 Z</button>
      <button :disabled="inputMode !== 'keys'" @pointerdown="press('x')" @pointerup="maybeRelease" @pointerleave="maybeRelease">右旋 X</button>
    </div>

    <n-space align="center" size="small">
      <n-button type="error" size="small" @click="store.carEstop">轮子急停 E</n-button>
      <StatusDot :level="carLevel" />
      <span class="hint">{{ motionText }}</span>
    </n-space>
    <p class="hint" style="margin:0">{{ hintText }}</p>
  </n-space>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'

// 手柄摇杆上限，同步 YuriChassis/kiwi_drive.py 的 LINEAR_SPEED_MPS / ANGULAR_SPEED_RAD_S
const CAR_LIMITS = { linear: 0.10, angular: 0.60 }
const DEADZONE = 0.15
const BTN = { A: 0, B: 1, Y: 3 }

const store = useConsole()
const inputMode = ref('keys')
const padConnected = ref(false)
const prevBtns = { A: false, B: false, Y: false }
let padWasConnected = false
let padTimer = null

const isLock = computed(() => store.carMode === 'lock')
const padLevel = computed(() => (padConnected.value ? 'ok' : 'off'))
const padText = computed(() => {
  if (!('getGamepads' in navigator)) return '浏览器不支持 Gamepad API（建议 Edge/Chrome）'
  return padConnected.value
    ? '手柄已连接：左摇杆移动、右摇杆转向；A 急停 · B 停止 · Y 恢复'
    : '未检测到手柄：连接手柄后，在页面上按手柄任意键激活'
})

function dz(v) { return Math.abs(v) < DEADZONE ? 0 : v }

function press(key) { if (store.state.connected) store.carPress(key) }
function maybeRelease() { if (store.state.connected && !isLock.value) store.carRelease() }
function doStop() { if (store.state.connected) store.carRelease() }

function pollGamepad() {
  if (inputMode.value !== 'gamepad' || !store.state.connected) return
  const pads = navigator.getGamepads ? navigator.getGamepads() : []
  const gp = pads.find((p) => p && p.connected)
  padConnected.value = !!gp
  if (!gp) {
    if (padWasConnected) store.carVel(0, 0, 0)  // 断开瞬间 0 速一次
    padWasConnected = false
    return
  }
  padWasConnected = true
  const axes = gp.axes
  const lx = dz(axes[0] || 0), ly = dz(axes[1] || 0), rx = dz(axes[2] || 0)
  if (isLock.value) {
    // 点按锁定：摇杆越过死区 -> 锁存该方向满速持续；回中保持；B 停止
    if (lx || ly || rx) {
      store.carVel(
        (ly < 0 ? 1 : ly > 0 ? -1 : 0) * CAR_LIMITS.linear,
        (lx < 0 ? 1 : lx > 0 ? -1 : 0) * CAR_LIMITS.linear,
        (rx < 0 ? 1 : rx > 0 ? -1 : 0) * CAR_LIMITS.angular,
      )
    }
    // 回中不发：后端保持上一锁定速度
  } else {
    store.carVel(
      -ly * CAR_LIMITS.linear,
      -lx * CAR_LIMITS.linear,
      -rx * CAR_LIMITS.angular,
    )
  }
  const b = (i) => !!(gp.buttons[i] && gp.buttons[i].pressed)
  const nowA = b(BTN.A), nowB = b(BTN.B), nowY = b(BTN.Y)
  if (nowA && !prevBtns.A) store.carEstop()
  if (nowB && !prevBtns.B) doStop()
  if (nowY && !prevBtns.Y) store.resume()
  prevBtns.A = nowA; prevBtns.B = nowB; prevBtns.Y = nowY
}

// 切回键盘/按钮：确保手柄连续速度被清（否则后端残留旧速度继续跑）
watch(inputMode, (v) => {
  if (v !== 'gamepad' && store.state.connected) store.carRelease()
})

function isTyping(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') }
function onKeyDown(e) {
  if (inputMode.value !== 'keys' || isTyping(e)) return
  const k = e.key.toLowerCase()
  if (['w', 'a', 's', 'd', 'z', 'x'].includes(k)) { e.preventDefault(); press(k) }
  else if (e.key === ' ') { e.preventDefault(); doStop() }
  else if (k === 'e') store.carEstop()
}
function onKeyUp(e) {
  if (inputMode.value !== 'keys' || isTyping(e)) return
  if (['w', 'a', 's', 'd', 'z', 'x'].includes(e.key.toLowerCase())) maybeRelease()
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('gamepadconnected', () => { padConnected.value = true })
  window.addEventListener('gamepaddisconnected', () => { padConnected.value = false })
  padTimer = setInterval(pollGamepad, 33)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  clearInterval(padTimer)
  if (store.state.connected) store.carVel(0, 0, 0)
})

const carLevel = computed(() => store.state.car_estop ? 'warn' : (store.state.car_motion || store.state.car_vel) ? 'info' : 'off')
const motionText = computed(() => {
  if (store.state.car_estop) return '急停中（方向 / 手柄 A 自动恢复）'
  if (store.state.car_vel) return `运行: vx ${store.state.car_vel[0].toFixed(2)} vy ${store.state.car_vel[1].toFixed(2)} ω ${store.state.car_vel[2].toFixed(2)}`
  if (store.state.car_motion) return `运行: ${store.state.car_motion}`
  return '停'
})
const hintText = computed(() => {
  if (inputMode.value === 'gamepad') {
    return isLock.value
      ? '手柄·点按锁定：推摇杆一下即持续该方向（满速），回中保持；换向再推；B 停止 · A 急停 · Y 恢复'
      : '手柄·按住移动：摇杆连续控制，回中即停；A 急停 · B 停止 · Y 恢复'
  }
  return isLock.value
    ? '点按一次即持续移动，再按其它方向切换；空格/停键停止；E 只停轮子不动臂（与 CLI 一致）'
    : '按住移动（连续 car_drive 20Hz）、松开立即 0 速；E 只停轮子不动臂'
})
</script>