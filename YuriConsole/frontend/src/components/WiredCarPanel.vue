<template>
  <n-space vertical :size="8">
    <n-space align="center" size="small">
      <n-input v-model:value="store.wiredPort" placeholder="COM21" style="width: 100px" size="small">
        <template #prefix>串口</template>
      </n-input>
      <n-button v-if="!store.state.wired.connected" type="primary" size="small" :loading="busy" @click="doConnect">
        连接
      </n-button>
      <n-button v-else size="small" secondary @click="store.wiredDisconnect">断开</n-button>
      <StatusDot :level="level" />
      <span class="hint">{{ hintText }}</span>
    </n-space>

    <div class="pad">
      <span />
      <button @pointerdown="press('w')" @pointerup="maybeRelease" @pointerleave="maybeRelease">前 W</button>
      <span />
      <button @pointerdown="press('a')" @pointerup="maybeRelease" @pointerleave="maybeRelease">左 A</button>
      <button class="stop-btn" @pointerdown="store.wiredRelease">停 空格</button>
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
import { computed, ref } from 'vue'
import { useConsole } from '../stores/console'
import StatusDot from './StatusDot.vue'
const store = useConsole()
const busy = ref(false)
const isLock = computed(() => store.carMode === 'lock')

async function doConnect() {
  busy.value = true
  const r = await store.wiredConnect()
  busy.value = false
  if (!r.ok) console.error('wired connect failed:', r.msg)
}
function press(key) {
  if (store.state.wired.connected) store.wiredPress(key)
}
function maybeRelease() {
  if (store.state.wired.connected && !isLock.value) store.wiredRelease()
}
const level = computed(() => store.state.wired.connected ? (store.state.wired.torque_on ? 'ok' : 'warn') : 'off')
const hintText = computed(() => {
  if (!store.state.wired.connected) return '未连接（有线相机小车）'
  const t = store.state.wired.torque_on ? '扭矩开' : '扭矩关'
  return `${store.state.wired.port} 已连接 · ${t}`
})
const motionText = computed(() => store.state.wired.motion ? `运行: ${store.state.wired.motion}` : '停')
</script>