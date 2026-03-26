import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api'

export const useAuthStore = defineStore('auth', () => {
  // State
  const token = ref(localStorage.getItem('token'))
  const user = ref(null)
  
  // Getters
  const isAuthenticated = computed(() => !!token.value && !!user.value)
  const isHR = computed(() => user.value?.is_hr || false)
  
  // Actions
  async function loginWithFeishu(authCode) {
    const { data } = await api.post('/auth/login', { auth_code: authCode })
    
    token.value = data.token
    user.value = {
      open_id: data.open_id,
      name: data.name,
      employee_id: data.employee_id,
      employee_name: data.employee_name,
      is_hr: data.is_hr
    }
    
    localStorage.setItem('token', data.token)
    api.defaults.headers.common['Authorization'] = `Bearer ${data.token}`
    
    return data
  }
  
  async function fetchCurrentUser() {
    const { data } = await api.get('/auth/me')
    user.value = data.data
    return data.data
  }
  
  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    delete api.defaults.headers.common['Authorization']
  }
  
  function init() {
    if (token.value) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token.value}`
    }
  }
  
  return {
    token,
    user,
    isAuthenticated,
    isHR,
    loginWithFeishu,
    fetchCurrentUser,
    logout,
    init
  }
})
