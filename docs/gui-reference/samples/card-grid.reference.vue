<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { NButton, NCard, NEmpty, NInput, NModal, NSpace, NTag, NText, useDialog, useMessage } from "naive-ui";
import { useProjectsStore } from "../stores/projects";
import type { ProjectSummary } from "../api/client";

const router = useRouter();
const message = useMessage();
const dialog = useDialog();
const store = useProjectsStore();
const showCreate = ref(false);
const newName = ref("");

const LANG_LABEL: Record<string, string> = {
  original: "原文",
  ZH: "中文",
  ZHEN: "中英混合",
  EN: "英文",
  JA: "日文",
  ES: "西语",
  AR: "阿语",
};

onMounted(() => store.refresh().catch((e) => message.error(e.message)));

function openCreate() {
  newName.value = "";
  showCreate.value = true;
}

async function createProject() {
  const name = newName.value.trim();
  if (!name) {
    message.warning("请输入项目名称");
    return;
  }
  try {
    const p = await store.create(name);
    showCreate.value = false;
    newName.value = "";
    openProject(p.id);
  } catch (e) {
    message.error((e as Error).message);
  }
}

function openProject(id: string) {
  router.push({ path: "/workspace", query: { project: id } });
}

function removeProject(p: ProjectSummary) {
  dialog.warning({
    title: "删除项目",
    content: `「${p.name}」删除后不可恢复，确定继续吗？`,
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await store.remove(p.id);
        message.success("已删除");
      } catch (e) {
        message.error((e as Error).message);
      }
    },
  });
}

function fmtTime(s: string): string {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
</script>

<template>
  <div>
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px">
      <div>
        <NText strong style="font-size: 20px; color: var(--mv-text)">往期项目</NText>
        <NText style="font-size: 12px; color: var(--mv-text-2); margin-left: 8px">共 {{ store.projects.length }} 个</NText>
      </div>
      <NButton type="primary" @click="openCreate">＋ 新建项目</NButton>
    </div>

    <div v-if="!store.projects.length" class="mv-empty">
      <NEmpty description="还没有项目，先新建一个吧" />
      <div style="text-align: center; margin-top: 8px">
        <NButton type="primary" @click="openCreate">新建项目</NButton>
      </div>
    </div>

    <div
      v-else
      style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px"
    >
      <NCard
        v-for="p in store.projects"
        :key="p.id"
        class="mv-card-hover"
        style="cursor: pointer"
        @click="openProject(p.id)"
      >
        <div style="display: flex; justify-content: space-between; align-items: flex-start">
          <NText strong style="font-size: 15px; color: var(--mv-text)">{{ p.name }}</NText>
          <NTag size="small" :bordered="false" style="background: var(--mv-primary-soft); color: var(--mv-primary)">
            {{ LANG_LABEL[p.dub_lang] ?? p.dub_lang ?? "原文" }}
          </NTag>
        </div>
        <div style="font-size: 12px; color: var(--mv-text-2); margin-top: 10px; line-height: 1.8">
          <div>台词 {{ p.line_count }} 条 · 文稿 {{ p.script_len }} 字</div>
          <div>更新于 {{ fmtTime(p.updated_at) }}</div>
        </div>
        <NSpace style="margin-top: 12px" @click.stop>
          <NButton size="small" type="primary" @click="openProject(p.id)">打开</NButton>
          <NButton size="small" type="error" quaternary @click="removeProject(p)">删除</NButton>
        </NSpace>
      </NCard>
    </div>

    <NModal v-model:show="showCreate" preset="card" title="新建项目" style="width: 420px">
      <NInput v-model:value="newName" placeholder="项目名称" @keydown.enter="createProject" />
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showCreate = false">取消</NButton>
          <NButton type="primary" @click="createProject">创建并打开</NButton>
        </NSpace>
      </template>
    </NModal>
  </div>
</template>

<style scoped>
.mv-empty {
  padding: 48px 0;
  background: var(--mv-card);
  border: 1px dashed var(--mv-border);
  border-radius: 12px;
}
</style>
