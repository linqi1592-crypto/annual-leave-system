import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/',
    name: 'Home',
    component: () => import('@/views/Home.vue')
  },
  {
    path: '/employee/:id',
    name: 'EmployeeDetail',
    component: () => import('@/views/EmployeeDetail.vue')
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/views/Admin.vue'),
    meta: { requiresHR: true }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// 路由守卫
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  
  // 公开页面直接访问
  if (to.meta.public) {
    next()
    return
  }
  
  // 检查登录状态
  if (!authStore.isAuthenticated) {
    next('/login')
    return
  }
  
  // 检查 HR 权限
  if (to.meta.requiresHR && !authStore.user?.is_hr) {
    next('/')
    return
  }
  
  next()
})

export default router
