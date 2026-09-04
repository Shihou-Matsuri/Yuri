import { defineStore } from 'pinia'
import { ref } from 'vue'

const H = { 'Content-Type': 'application/json' }

async function post(path, body) {
  const r = await fetch(path, { method: 'POST', headers: H, body: body ? JSON.stringify(body) : undefined })
  return r.json()
}

export const useConsole = defineStore('console', () => {
  const state = ref({
    connected: false, link: '', mock: false, leader_port: 'COM7', arm_enabled: true, arm_pad_enabled: false,
    car_motion: null, car_vel: null, car_estop: false, global_estop: false, positions: {}, wheel_speed: null,
    wired: { connected: false, port: 'COM21', motion: null, torque_on: false, error: null },
  })
  const logs = ref([])
  const gamepad = ref({ connected: false, left_x: 0, left_y: 0, right_x: 0, right_y: 0, buttons: {} })
  const linkSel = ref('tcp')   // tcp | serial
  const serialPort = ref('COM8')
  const leaderPort = ref('COM7')
  const logFilter = ref('all')
  // 小车方向操作模式：lock=点按锁定（按一下持续，空格/停停止）｜hold=按住移动、松手停
  const wiredPorts = ref([])
  const wiredPort = ref('COM21')
  const carMode = ref('lock')
  try { if (localStorage.getItem('mv-car-mode') === 'hold') carMode.value = 'hold' } catch { /* in-memory */ }
  function setCarMode(m) { carMode.value = m; try { localStorage.setItem('mv-car-mode', m) } catch { /* in-memory */ } }

  async function refresh() {
    try {
      const s = await (await fetch('/api/state')).json()
      state.value = s
    } catch { /* 后端未起 */ }
  }
  async function refreshLogs() {
    try {
      const q = logFilter.value === 'all' ? '' : `?level=${logFilter.value}`
      logs.value = await (await fetch('/api/logs' + q)).json()
    } catch { /* ignore */ }
  }
  async function connect() {
    const body = { link: linkSel.value, serial_port: serialPort.value, leader_port: leaderPort.value }
    const r = await post('/api/connect', body)
    await refresh()
    return r
  }
  async function disconnect() { await post('/api/disconnect'); await refresh() }
  async function carPress(key) { await post('/api/car/press', { key }) }
  async function carRelease() { await post('/api/car/release') }
  async function carVel(vx, vy, omega) { await post('/api/car/vel', { vx, vy, omega }) }
  async function armPad(enabled, x, y, z = 0) { await post('/api/arm/pad', { enabled, x, y, z }); await refresh() }
  async function gripper(action) { await post('/api/gripper', { action }) }
  async function carEstop() { await post('/api/car/estop'); await refresh() }
  async function globalEstop() { await post('/api/global/estop'); await refresh() }
  async function resume() { await post('/api/resume'); await refresh() }
  async function setArmEnabled(on) { await post('/api/arm/enabled', { enabled: on }); await refresh() }
  // ---- 有线相机小车（CameraCar，独立 USB 串口）----
  async function wiredConnect() { const r = await post('/api/wired/connect', { port: wiredPort.value }); await refresh(); return r }
  async function wiredRefreshPorts() {
    try {
      const r = await fetch('/api/wired/ports')
      wiredPorts.value = await r.json()
      if (wiredPorts.value.length && !wiredPorts.value.includes(wiredPort.value)) wiredPort.value = wiredPorts.value[0]
    } catch { /* backend not ready */ }
  }
  async function wiredDisconnect() { await post('/api/wired/disconnect'); await refresh() }
  async function wiredPress(key) { await post('/api/wired/press', { key }) }
  async function wiredRelease() { await post('/api/wired/release') }
  async function wiredVel(vx, vy, omega) { await post('/api/wired/vel', { vx, vy, omega }) }
  async function wiredEstop() { await post('/api/wired/estop'); await refresh() }
  async function gamepadState() {
    try {
      const r = await fetch('/api/gamepad/state')
      gamepad.value = await r.json()
      return gamepad.value
    } catch { return { connected: false, left_x: 0, left_y: 0, right_x: 0, right_y: 0, buttons: {} } }
  }

  return { state, logs, gamepad, linkSel, serialPort, leaderPort, logFilter, carMode, setCarMode, wiredPorts, wiredPort,
    refresh, refreshLogs, connect, disconnect, carPress, carRelease, carVel, carEstop, globalEstop, resume, setArmEnabled,
    armPad, gripper,
    wiredConnect, wiredDisconnect, wiredPress, wiredRelease, wiredVel, wiredEstop, gamepadState,
    wiredRefreshPorts }
})
