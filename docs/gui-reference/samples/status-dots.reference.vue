<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { NSpace, NTooltip } from "naive-ui";
import { useDeployStore } from "../stores/deploy";

const deploy = useDeployStore();
const router = useRouter();

type DotKey = "tts" | "gptsovits" | "sbv2" | "whisperx" | "fakara";
const rows = computed<Array<{ key: DotKey; label: string }>>(() => [
  { key: "tts", label: "IndexTTS" },
  { key: "gptsovits", label: "GPT-SoVITS" },
  { key: "sbv2", label: "Style-Bert-VITS2" },
  { key: "whisperx", label: "WhisperX" },
  { key: "fakara", label: "FA-Kara" },
]);

function dotColor(state?: string): string {
  if (state === "ok") return "#52C41A";
  if (state === "stopped") return "var(--mv-text-2)";
  if (state === "starting" || state === "loading") return "#F2A93B";
  return "#E5484D";
}

onMounted(() => {
  deploy.refresh().catch(() => undefined);
});
</script>

<template>
  <NSpace :size="8" align="center">
    <NTooltip v-for="row in rows" :key="row.key">
      <template #trigger>
        <span
          :style="{
            display: 'inline-block',
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            cursor: 'pointer',
            background: dotColor(deploy.services[row.key].status?.state),
            boxShadow: '0 0 6px ' + dotColor(deploy.services[row.key].status?.state),
          }"
          @click="router.push('/settings/deploy')"
        />
      </template>
      {{ row.label }}：{{ deploy.services[row.key].status?.state ?? "未知" }}（点击到部署）
    </NTooltip>
  </NSpace>
</template>
