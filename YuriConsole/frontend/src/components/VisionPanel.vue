<template>
  <n-space vertical :size="8">
    <n-alert type="info" :bordered="false">
      摄像头预览 + YuriEye 检测结果（bbox/类别）叠加将在接入 YuriEye 后显示。本区为占位，不影响 A/B/C/E 区离线演示。
    </n-alert>
    <n-space align="center"><StatusDot level="off" /><span class="hint">YuriEye：未接入（V1 里程碑）</span></n-space>
  </n-space>
</template>
<script setup>
import StatusDot from './StatusDot.vue'
</script>