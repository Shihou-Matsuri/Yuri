<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  darkTheme,
  NButton,
  NConfigProvider,
  NDialogProvider,
  NLayout,
  NLayoutContent,
  NLayoutHeader,
  NMenu,
  NMessageProvider,
  NSpace,
} from "naive-ui";
import { useThemeStore } from "./stores/theme";
import ServiceDots from "./components/ServiceDots.vue";
import { THEMES } from "./theme";

const route = useRoute();
const router = useRouter();
const themeStore = useThemeStore();
themeStore.init();

const SETTING_KEYS = ["general", "voices", "pronunciation", "emotions", "deploy"];
const POSTPROCESS_KEY = "postprocess";
const activeKey = computed(() => {
  if (route.path === "/" || route.path.startsWith("/workspace")) return "projects";
  const seg = route.path.split("/").filter(Boolean)[1] ?? "";
  if (seg === POSTPROCESS_KEY) return POSTPROCESS_KEY;
  return SETTING_KEYS.includes(seg) ? seg : "projects";
});
const menuOptions = [
  { label: "项目", key: "projects" },
  { label: "通用", key: "general" },
  { label: "语音库", key: "voices" },
  { label: "发音词典", key: "pronunciation" },
  { label: "情绪模板", key: "emotions" },
  { label: "部署", key: "deploy" },
  { label: "后期集成", key: "postprocess" },
];
</script>

<template>
  <NConfigProvider
    :theme="themeStore.theme.dark ? darkTheme : null"
    :theme-overrides="themeStore.theme.overrides"
  >
    <NMessageProvider>
      <NDialogProvider>
        <NLayout style="height: 100%">
          <NLayoutHeader
            bordered
            style="display: flex; align-items: center; padding: 0 20px; height: 52px; background: var(--mv-header)"
          >
            <div style="display: flex; align-items: center; margin-right: 24px; gap: 8px">
              <span
                style="
                  width: 10px;
                  height: 10px;
                  border-radius: 50%;
                  background: var(--mv-primary);
                  box-shadow: 0 0 10px var(--mv-primary);
                "
              />
              <span style="font-weight: 700; font-size: 16px; color: var(--mv-text); letter-spacing: 0.5px">
                MatsuriVoice
              </span>
              <span style="font-size: 11px; color: var(--mv-text-2); margin-top: 2px">配音工作台</span>
            </div>
            <NMenu
              mode="horizontal"
              :options="menuOptions"
              :value="activeKey"
              style="flex: 1"
              @update:value="(k: string) => router.push(k === 'projects' ? '/' : k === POSTPROCESS_KEY ? '/postprocess' : `/settings/${k}`)"
            />
            <ServiceDots />
            <NSpace :size="4" style="margin-left: 16px">
              <NButton
                v-for="t in THEMES"
                :key="t.key"
                size="small"
                :type="themeStore.themeKey === t.key ? 'primary' : 'default'"
                quaternary
                @click="themeStore.set(t.key)"
              >
                {{ t.emoji }} {{ t.name }}
              </NButton>
            </NSpace>
          </NLayoutHeader>
          <NLayoutContent content-style="padding: 20px; max-width: 1180px; margin: 0 auto">
            <router-view v-slot="{ Component }">
              <transition name="fade" mode="out-in">
                <component :is="Component" />
              </transition>
            </router-view>
          </NLayoutContent>
        </NLayout>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>
