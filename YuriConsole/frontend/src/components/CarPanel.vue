<template>
  <n-space vertical :size="8">
    <n-space align="center" size="small">
      <span class="hint">操作方式</span>
      <n-radio-group v-model:value="store.carMode" size="small" @update:value="store.setCarMode">
        <n-radio-button value="lock">点按锁定</n-radio-button>
        <n-radio-button value="hold">按住移动</n-radio-button>
      </n-radio-group>
    </n-space>

    <div class="pad">
      <span />
      <button @pointerdown="press('w')" @pointerup="maybeRelease" @pointerleave="maybeRelease">前 W</button>
      <span />
      <button @pointerdown="press('a')" @pointerup="maybeRelease" @pointerleave="maybeRelease">左 A</button>
      <button class="stop-btn" @pointerdown="doStop">停 空格</button>
      <button @pointerdown="press('d')" @pointerup="maybeRelease" @pointerleave="maybeRelease">右 D</button>
      <span />
      <button @pointerdown="press('s')" @pointerup="maybeRelease" @pointerleave="maybeRelease">后 S</button>
      <span />
    </div>
    <div class="pad" style="grid-template-columns:repeat(2,96px)">
      <button @pointerdown="press('z')" @pointerup="maybeRelease" @pointerleave="maybeRelease">左旋 Z</button>
      <button @pointerdown="press('x')" @pointerup="maybeRelease" @pointerleave="maybeRelease">右旋 X</button>
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
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()

const isLock = computed(() => store.carMode === 'lock')

function press(key) {
  if (store.state.connected) store.carPress(key)
}
/** 按住模式：松开/移出即停；点按锁定模式：不因松手停（用停键/空格/E） */
function maybeRelease() {
  if (store.state.connected && !isLock.value) store.carRelease()
}
function doStop() {
  if (store.state.connected) store.carRelease()
}

function isTyping(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') }
function onKeyDown(e) {
  if (isTyping(e)) return
  const k = e.key.toLowerCase()
  if (['w', 'a', 's', 'd', 'z', 'x'].includes(k)) { e.preventDefault(); press(k) }
  else if (e.key === ' ') { e.preventDefault(); doStop() }
  else if (k === 'e') store.carEstop()
}
function onKeyUp(e) {
  if (isTyping(e)) return
  if (['w', 'a', 's', 'd', 'z', 'x'].includes(e.key.toLowerCase())) maybeRelease()
}
onMounted(() => { window.addEventListener('keydown', onKeyDown); window.addEventListener('keyup', onKeyUp) })
onBeforeUnmount(() => { window.removeEventListener('keydown', onKeyDown); window.removeEventListener('keyup', onKeyUp) })

const carLevel = computed(() => store.state.car_estop ? 'warn' : store.state.car_motion ? 'info' : 'off')
const motionText = computed(() => store.state.car_estop ? '急停中（按方向键自动恢复）'
  : store.state.car_motion ? `运行: ${store.state.car_motion}` : '停')
const hintText = computed(() => isLock.value
  ? '点按一次即持续移动，再按其它方向切换；空格/停键停止；E 只停轮子不动臂（与 CLI 一致）'
  : '按住移动（连续 car_drive 20Hz）、松开立即 0 速；E 只停轮子不动臂')
</script>