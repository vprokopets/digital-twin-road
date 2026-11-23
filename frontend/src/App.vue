<script setup lang="ts">
import { RouterView } from 'vue-router'
import { useDashboardStore } from './stores/dashboard'

const store = useDashboardStore()
</script>

<template>
  <div id="app" :class="store.theme">
    <RouterView />
  </div>
</template>

<style>
body, html {
  margin: 0;
  padding: 0;
  overflow: hidden;
}

#app {
  width: 100vw;
  height: 100vh;
  transition: background-color 0.5s ease;
}

#app.light {
  background-color: #f8f9fa;
}

#app.dark {
  background-color: #0f172a;
}
</style>
