<template>
  <div class="app-container">
    <!-- 顶部导航 -->
    <nav class="navbar">
      <div class="nav-brand">
        <span class="logo">🏖️</span>
        <span class="title">年假查询系统</span>
      </div>
      
      <div class="nav-user" v-if="authStore.user">
        <span class="user-name">{{ authStore.user.name }}</span>
        <el-tag v-if="authStore.user.is_hr" type="warning" size="small">HR</el-tag>
        <span class="logout" @click="logout">退出</span>
      </div>
    </nav>
    
    <!-- 主内容区 -->
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const authStore = useAuthStore()
const router = useRouter()

const logout = () => {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background: #f5f5f5;
}

.navbar {
  background: #fff;
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  position: sticky;
  top: 0;
  z-index: 100;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo {
  font-size: 24px;
}

.title {
  font-size: 18px;
  font-weight: 600;
  color: #333;
}

.nav-user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  color: #666;
}

.logout {
  color: #f56c6c;
  cursor: pointer;
  font-size: 14px;
}

.logout:hover {
  text-decoration: underline;
}

.main-content {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}
</style>
