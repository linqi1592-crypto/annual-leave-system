<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-icon">🔐</div>
      <h2>请登录</h2>
      <p class="subtitle">使用飞书账号登录查看年假信息</p>
      
      <el-button 
        type="primary" 
        size="large" 
        :loading="loading"
        @click="handleLogin"
      >
        飞书免登登录
      </el-button>
      
      <div class="dev-mode" v-if="!isFeishu">
        <p>开发测试模式</p>
        <el-button @click="devLogin">测试账号登录</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const isFeishu = ref(false)

onMounted(() => {
  // 检查是否在飞书环境
  isFeishu.value = typeof tt !== 'undefined'
})

const handleLogin = async () => {
  if (!isFeishu.value) {
    ElMessage.warning('请在飞书客户端中打开')
    return
  }
  
  loading.value = true
  
  try {
    // 飞书免登
    const authCode = await new Promise((resolve, reject) => {
      tt.requestAuthCode({
        appId: import.meta.env.VITE_FEISHU_APP_ID,
        success: (res) => resolve(res.code),
        fail: (err) => reject(err)
      })
    })
    
    await authStore.loginWithFeishu(authCode)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (error) {
    ElMessage.error('登录失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const devLogin = async () => {
  // 开发测试登录
  localStorage.setItem('token', 'dev_token')
  authStore.user = {
    name: '测试用户',
    is_hr: true,
    employee_id: 'test_001'
  }
  router.push('/')
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.login-card {
  background: white;
  padding: 48px;
  border-radius: 16px;
  text-align: center;
  box-shadow: 0 10px 40px rgba(0,0,0,0.2);
  min-width: 320px;
}

.login-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

h2 {
  margin: 0 0 8px;
  color: #333;
}

.subtitle {
  color: #999;
  margin-bottom: 24px;
}

.dev-mode {
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #eee;
}

.dev-mode p {
  color: #999;
  font-size: 12px;
  margin-bottom: 8px;
}
</style>
