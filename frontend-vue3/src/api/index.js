import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    const { code, message } = response.data
    
    if (code !== 0) {
      return Promise.reject(new Error(message || '请求失败'))
    }
    
    return response.data
  },
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    
    return Promise.reject(error)
  }
)

// API 方法
export const leaveApi = {
  // 获取年假余额
  getBalance: (employeeId, year) => 
    api.get(`/leave/balance?employee_id=${employeeId}&year=${year}`),
  
  // 获取请假历史
  getHistory: (employeeId, year) =>
    api.get(`/leave/history?employee_id=${employeeId}&year=${year}`),
  
  // 获取计算规则
  getRules: (employeeId) =>
    api.get(`/leave/rules?employee_id=${employeeId}`),
  
  // 获取员工列表
  getEmployees: () => api.get('/employees'),
  
  // 创建调整记录
  createAdjustment: (data) => api.post('/admin/adjustments', data),
  
  // 导出数据
  exportData: (year, format) =>
    api.get(`/admin/export?year=${year}&format=${format}`, {
      responseType: 'blob'
    }),
  
  // 年终清算预览
  getYearEndPreview: (year) =>
    api.get(`/admin/year-end/preview?year=${year}`),
  
  // 确认年终清算
  confirmYearEnd: (year, details) =>
    api.post('/admin/year-end/confirm', { year, details })
}

export default api
