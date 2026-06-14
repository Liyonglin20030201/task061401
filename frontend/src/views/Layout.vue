<template>
  <el-container class="layout-container">
    <el-aside width="220px" class="sidebar">
      <div class="logo">
        <h3>知识库AI助手</h3>
      </div>
      <el-menu :default-active="activeRoute" router>
        <el-menu-item index="/">
          <el-icon><ChatDotRound /></el-icon>
          <span>智能问答</span>
        </el-menu-item>
        <el-menu-item index="/documents">
          <el-icon><Document /></el-icon>
          <span>文档管理</span>
        </el-menu-item>
        <el-menu-item v-if="auth.user?.role === 'admin'" index="/admin">
          <el-icon><Setting /></el-icon>
          <span>系统管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="user-info">{{ auth.user?.username }} ({{ auth.user?.role }})</span>
        <el-button type="text" @click="handleLogout">退出登录</el-button>
      </el-header>
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ChatDotRound, Document, Setting } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeRoute = computed(() => route.path)

onMounted(async () => {
  if (auth.isAuthenticated && !auth.user) {
    await auth.fetchUser()
  }
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.layout-container {
  height: 100vh;
}
.sidebar {
  background: #304156;
  overflow: hidden;
}
.logo {
  padding: 20px;
  text-align: center;
}
.logo h3 {
  color: #fff;
  margin: 0;
}
.sidebar .el-menu {
  border: none;
  background: #304156;
}
.sidebar .el-menu-item {
  color: #bfcbd9;
}
.sidebar .el-menu-item.is-active {
  background: #263445;
  color: #409eff;
}
.header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 16px;
  border-bottom: 1px solid #e6e6e6;
  background: #fff;
}
.user-info {
  color: #606266;
  font-size: 14px;
}
.main-content {
  background: #f5f7fa;
}
</style>
