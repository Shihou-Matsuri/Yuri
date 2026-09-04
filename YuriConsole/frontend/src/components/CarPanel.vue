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
        <span class="hint">右摇杆</span>
        <n-radio-group v-model:value="rsRole" size="small">
          <n-radio-button value="turn">小车转向</n-radio-button>
          <n-radio-button value="arm">控制机械臂</n-radio-button>
        </n-radio-group>
      </template>
    </n-space>
    <n-space v-if="inputMode === 'gamepad'" align="center" size="small">
      <StatusDot :level="padLevel" />
      <span class="hint">{{ padText }}</span>
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

// 手柄摇杆上限，同步 YuriChassis/kiwi_drive.py
const CAR_LIMITS = { linear: 0.10, angular: 0.60 }
const DEADZONE = 0.15
const AX = { LX: 0, LY: 1, RX: 2, RY: 3 }
const BTN = { A: 0, B: 1, X: 2, Y: 3, LB: 4, RB: 5, DPAD_UP: 12, DPAD_DOWN: 13 }

const store = useConsole()
const inputMode = ref('keys')
const rsRole = ref('turn')
try { if (localStorage.getItem('mv-rs-role') === 'arm') rsRole.value = 'arm' } catch { /* in-memory */ }
const padConnected = ref(false)
const prevBtn = { A: false, B: false, X: false, Y: false, LB: false, RB: false }
let padWasConnected = false
let padTimer = null

const isLock = computed(() => store.carMode === 'lock')
const padLevel = computed(() => (padConnected.value ? 'ok' : 'off'))
const padText = computed(() => {
  return padConnected.value
    ? '左摇杆移动 · X 顺转 / Y 逆转 · A 恢复 · B 停止 · LB 开夹 / RB 合夹'
    : '未检测到手柄：连接手柄后，在页面上按手柄任意键激活'
})

function dz(v) { return Math.abs(v) < DEADZONE ? 0 : v }
function press(key) { if (store.state.connected) store.carPress(key) }
function maybeRelease() { if (store.state.connected && !isLock.value) store.carRelease() }
function doStop() { if (store.state.connected) store.carRelease() }
function signAxis(v, neg) { // 转方向满速
  if (Math.abs(v) < DEADZONE) return 0
  return (v < 0 ? 1 : -1) * (neg ? -1 : 1)
}

async function pollGamepad() {
  if (inputMode.value !== 'gamepad' || !store.state.connected) return
  const gp = await store.gamepadState()
  padConnected.value = gp.connected
  if (!gp.connected) {
    if (padWasConnected) { store.carVel(0, 0, 0); if (rsRole.value === 'arm') store.armPad(false) }
    padWasConnected = false
    return
  }
  padWasConnected = true
  const lx = dz(gp.left_x || 0), ly = dz(gp.left_y || 0)
  const rx = dz(gp.right_x || 0), ry = dz(gp.right_y || 0)
  const b = (name) => !!(gp.buttons && gp.buttons[name])
  const now = { A: b('a'), B: b('b'), X: b('x'), Y: b('y'), LB: b('lb'), RB: b('rb') }

  // 夹爪：LB 开 / RB 合（边沿）
  if (now.LB && !prevBtn.LB) store.gripper('open')
  if (now.RB && !prevBtn.RB) store.gripper('close')
  // A 恢复 / B 停止（边沿）
  if (now.A && !prevBtn.A) store.resume()
  if (now.B && !prevBtn.B) { locked.value = null; store.carRelease() }
  Object.assign(prevBtn, now)

  // 右摇杆用途
  const armRole = rsRole.value === 'arm'
  if (armRole) {
    // 右摇杆上下 = lift、左右 = pan；十字键上下 = elbow_flex（前后）
    const dpz = (b('dpad_up') ? 1 : 0) + (b('dpad_down') ? -1 : 0)
    store.armPad(true, rx, ry, dpz)
  } else if (rx !== 0 || ry !== 0) { /* 转向走下方 omega */ }

  const spin = (now.X ? -1 : 0) + (now.Y ? 1 : 0)   // X 顺转(负 omega) / Y 逆转
  if (isLock.value) {
    // 点按锁定：输入越界即锁存满速方向，回中保持；B 已清
    const dir = {
      vx: signAxis(-ly, true) * CAR_LIMITS.linear,
      vy: signAxis(-lx, true) * CAR_LIMITS.linear,
      w: 0,
    }
    if (spin !== 0) dir.w = spin * CAR_LIMITS.angular
    else if (!armRole && rx) dir.w = signAxis(rx, false) * CAR_LIMITS.angular * -1
    if (dir.vx || dir.vy || dir.w) locked.value = dir
    if (locked.value) store.carVel(locked.value.vx, locked.value.vy, locked.value.w)
  } else {
    // 按住：实时连续
    let w = 0
    if (spin !== 0) w = spin * CAR_LIMITS.angular
    else if (!armRole && rx) w = -rx * CAR_LIMITS.angular
    store.carVel(-ly * CAR_LIMITS.linear, -lx * CAR_LIMITS.linear, w)
  }
}
const locked = ref(null)  // lock 模式锁存 (vx,vy,w)

watch(inputMode, (v) => {
  if (v !== 'gamepad' && store.state.connected) {
    store.carRelease()
    if (rsRole.value === 'arm') store.armPad(false)
  }
})
watch(rsRole, (v) => {
  try { localStorage.setItem('mv-rs-role', v) } catch { /* ignore */ }
  if (inputMode.value === 'gamepad' && v !== 'arm' && store.state.connected) store.armPad(false)
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
  if (store.state.connected) { store.carVel(0, 0, 0); if (rsRole.value === 'arm') store.armPad(false) }
})

const carLevel = computed(() => store.state.car_estop ? 'warn' : (store.state.car_motion || store.state.car_vel) ? 'info' : 'off')
const motionText = computed(() => {
  if (store.state.car_estop) return '急停中（A / 方向自动恢复）'
  if (store.state.car_vel) return `小车: vx ${store.state.car_vel[0].toFixed(2)} vy ${store.state.car_vel[1].toFixed(2)} ω ${store.state.car_vel[2].toFixed(2)}`
  if (store.state.car_motion) return `小车: ${store.state.car_motion}`
  return '停'
})
const hintText = computed(() => {
  if (inputMode.value === 'gamepad') {
    const arm = rsRole.value === 'arm'
    return arm
      ? '手柄·控制机械臂：右摇杆 ↑↓=shoulder_lift(上下)、←→=shoulder_pan(左右)、十字键 ↑↓=elbow_flex(前后)；接管遥操作；小车左摇杆 + X/Y 旋转'
      : isLock.value
        ? '手柄·点按锁定：推一下即持续该方向，回中保持；X/Y 锁定旋转；B 停止 · A 恢复 · LB/RB 夹爪'
        : '手柄·按住移动：摇杆连续，回中即停；X/Y 按住旋转；A 恢复 · B 停止 · LB/RB 夹爪'
  }
  return isLock.value
    ? '点按一次即持续移动，再按其它方向切换；空格/停键停止；E 只停轮子不动臂（与 CLI 一致）'
    : '按住移动（连续 car_drive 20Hz）、松开立即 0 速；E 只停轮子不动臂'
})
</script>
