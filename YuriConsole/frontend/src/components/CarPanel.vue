<template>
  <n-space vertical :size="8">
    <div class="pad">
      <span />
      <button @pointerdown="press('w')" @pointerup="release" @pointerleave="release">前 W</button>
      <span />
      <button @pointerdown="press('a')" @pointerup="release" @pointerleave="release">左 A</button>
      <button class="stop-btn" @pointerdown="release">停 空格</button>
      <button @pointerdown="press('d')" @pointerup="release" @pointerleave="release">右 D</button>
      <span />
      <button @pointerdown="press('s')" @pointerup="release" @pointerleave="release">后 S</button>
      <span />
    </div>
    <div class="pad" style="grid-template-columns:repeat(2,96px)">
      <button @pointerdown="press('z')" @pointerup="release" @pointerleave="release">左旋 Z</button>
      <button @pointerdown="press('x')" @pointerup="release" @pointerleave="release">右旋 X</button>
    </div>
    <n-space align="center" size="small">
      <n-button type="error" size="small" @click="store.carEstop">轮子急停 E</n-button>
      <StatusDot :level="carLevel" />
      <span class="hint">{{ motionText }}</span>
    </n-space>
    <p class="hint" style="margin:0">按住移动（连续 car_drive 20Hz）、松开立即 0 速；E 只停轮子不动臂（与 CLI 一致）。反向开关见 camera_car_drive 标定，本区暂不重复。</p>
  </n-space>
</template>
<script setup>
import { computed, onMounted, onBeforeUnmount } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()

function press(key) {
  if (store.state.connected) store.carPress(key)
}
function release() { if (store.state.connected) store.carRelease() }

function isTyping(e) { const t = e.target; return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA') }
function onKeyDown(e) {
  if (isTyping(e)) return
  if (['w','a','s','d','z','x'].includes(e.key.toLowerCase())) { e.preventDefault(); press(e.key.toLowerCase()) }
  else if (e.key === ' ') { e.preventDefault(); release() }
  else if (e.key.toLowerCase() === 'e') store.carEstop()
}
function onKeyUp(e) { if (!isTyping(e) && ['w','a','s','d','z','x'].includes(e.key.toLowerCase())) release() }
onMounted(() => { window.addEventListener('keydown', onKeyDown); window.addEventListener('keyup', onKeyUp) })
onBeforeUnmount(() => { window.removeEventListener('keydown', onKeyDown); window.removeEventListener('keyup', onKeyUp) })

const carLevel = computed(() => store.state.car_estop ? 'warn' : store.state.car_motion ? 'info' : 'off')
const motionText = computed(() => store.state.car_estop ? '急停中（按方向键自动恢复）'
  : store.state.car_motion ? `运行: ${store.state.car_motion}` : '停')
</script>