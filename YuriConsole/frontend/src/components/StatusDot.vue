<template>
  <span :class="['st-dot', cls]" :title="label" />
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ level: { type: String, default: 'off' } })
const map = { ok: 'st-ok', warn: 'st-warn', danger: 'st-danger', off: 'st-off', info: 'st-info' }
const cls = computed(() => map[props.level] || map.off)
const label = computed(() => ({ ok: '就绪', warn: '警告', danger: '急停/故障', off: '离线', info: '信息' }[props.level] || '离线'))
</script>