import { defineStore } from 'pinia'
import { ref } from 'vue'

const H = { 'Content-Type': 'application/json' }

async function post(path, body) {
  const r = await fetch(path, { method: 'POST', headers: H, body: body ? JSON.stringify(body) : undefined })
  return r.json()
}

export const useConsole = defineStore('console', () => {
  const state = ref({
    connected: false, link: '', mock: false, leader_port: 'COM7', arm_enabled: true,
    car_motion: null, car_estop: false, global_estop: false, positions: {}, wheel_speed: null,
  })
  const logs = ref([])
  const linkSel = ref('tcp')   // tcp | serial
  const serialPort = ref('COM8')
  const leaderPort = ref('COM7')
  const logFilter = ref('all')

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
  async function carEstop() { await post('/api/car/estop'); await refresh() }
  async function globalEstop() { await post('/api/global/estop'); await refresh() }
  async function resume() { await post('/api/resume'); await refresh() }
  async function setArmEnabled(on) { await post('/api/arm/enabled', { enabled: on }); await refresh() }

  return { state, logs, linkSel, serialPort, leaderPort, logFilter,
    refresh, refreshLogs, connect, disconnect, carPress, carRelease, carEstop, globalEstop, resume, setArmEnabled }
})