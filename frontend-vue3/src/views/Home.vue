<template>
  <div class="home-page">
    <!-- 员工视图 -->
    <template v-if="!isHR">
      <div v-if="loading" class="loading">
        <el-skeleton :rows="6" animated />
      </div>
      
      <div v-else-if="balance" class="employee-view">
        <!-- 余额卡片 -->
        <div class="balance-card">
          <div class="label">剩余年假</div>
          <div class="number" :class="{ negative: isNegative }">
            {{ balance.annual_leave.remaining }}
          </div>
          <div class="sub">{{ isNegative ? '已透支' : '可用天数' }}</div>
        </div>
        
        <!-- 三栏展示 -->
        <div class="stats-grid">
          <div class="stat-item">
            <div class="label">当年额度</div>
            <div class="number">{{ currentYearQuota }}</div>
          </div>
          <div class="stat-item">
            <div class="label">上年结转</div>
            <div class="number">{{ carryoverQuota }}</div>
            <div class="note" v-if="balance.annual_leave.carryover.expire_date">
              {{ balance.annual_leave.carryover.expire_date }} 到期
            </div>
          </div>
          <div class="stat-item">
            <div class="label">已使用</div>
            <div class="number">{{ totalUsed }}</div>
          </div>
        </div>
        
        <!-- 操作菜单 -->
        <div class="menu-list">
          <div class="menu-item" @click="showHistory">
            <div class="menu-icon blue">📋</div>
            <div class="menu-text">
              <div class="title">请假明细</div>
              <div class="desc">查看本年度所有请假记录</div>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </div>
          
          <div class="menu-item" @click="showRules">
            <div class="menu-icon green">📖</div>
            <div class="menu-text">
              <div class="title">计算规则</div>
              <div class="desc">了解年假计算方式</div>
            </div>
            <el-icon><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </template>
    
    <!-- HR 视图 -->
    <template v-else>
      <div class="hr-view">
        <el-alert type="info" :closable="false">
          👋 欢迎，HR管理员！请选择员工查看或管理年假信息。
        </el-alert>
        
        <!-- 员工选择 -->
        <el-select 
          v-model="selectedEmployee" 
          placeholder="请选择员工"
          class="employee-select"
          @change="onEmployeeChange"
          filterable
        >
          <el-option 
            v-for="emp in employees" 
            :key="emp.user_id"
            :label="emp.name + (emp.department ? ` (${emp.department})` : '')"
            :value="emp.user_id"
          />
        </el-select>
        
        <!-- 选中员工详情 -->
        <div v-if="selectedEmployeeData" class="employee-detail">
          <!-- 复用员工视图的展示 -->
          <!-- 这里简化处理，实际可以提取公共组件 -->
          <div class="action-buttons">
            <el-button type="primary" @click="showHistory">请假明细</el-button>
            <el-button @click="showRules">计算规则</el-button>
            <el-button type="success" @click="showAdjustment">调整额度</el-button>
          </div>
        </div>
        
        <!-- 管理工具 -->
        <div class="admin-tools">
          <h3>📊 管理工具</h3>
          
          <div class="menu-list">
            <div class="menu-item" @click="showExport">
              <div class="menu-icon purple">📥</div>
              <div class="menu-text">
                <div class="title">批量导出</div>
                <div class="desc">导出全员年假数据报表</div>
              </div>
              <el-icon><ArrowRight /></el-icon>
            </div>
            
            <div class="menu-item" @click="showYearEnd">
              <div class="menu-icon orange">🔄</div>
              <div class="menu-text">
                <div class="title">年终清算</div>
                <div class="desc">年度结转与清零处理</div>
              </div>
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </template>
    
    <!-- 弹窗 -->
    <DetailDialog 
      v-model:visible="dialogVisible" 
      :type="dialogType"
      :title="dialogTitle"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { leaveApi } from '@/api'
import { ElMessage } from 'element-plus'

const authStore = useAuthStore()

// 状态
const loading = ref(false)
const balance = ref(null)
const employees = ref([])
const selectedEmployee = ref('')
const selectedEmployeeData = ref(null)

// 弹窗
const dialogVisible = ref(false)
const dialogType = ref('')
const dialogTitle = ref('')

// 计算属性
const isHR = computed(() => authStore.isHR)
const isNegative = computed(() => balance.value?.annual_leave?.remaining < 0)
const currentYearQuota = computed(() => {
  const cy = balance.value?.annual_leave?.current_year
  return cy?.quota || cy || 0
})
const carryoverQuota = computed(() => {
  const co = balance.value?.annual_leave?.carryover
  return co?.quota || co || 0
})
const totalUsed = computed(() => {
  return balance.value?.annual_leave?.total_used || 
         balance.value?.annual_leave?.used?.net || 0
})

// 加载数据
onMounted(async () => {
  if (isHR.value) {
    await loadEmployees()
  } else {
    await loadBalance()
  }
})

const loadBalance = async () => {
  loading.value = true
  try {
    const { data } = await leaveApi.getBalance(
      authStore.user.employee_id, 
      new Date().getFullYear()
    )
    balance.value = data
  } catch (error) {
    ElMessage.error('加载失败: ' + error.message)
  } finally {
    loading.value = false
  }
}

const loadEmployees = async () => {
  try {
    const { data } = await leaveApi.getEmployees()
    employees.value = data
  } catch (error) {
    ElMessage.error('加载员工列表失败')
  }
}

const onEmployeeChange = async (userId) => {
  selectedEmployeeData.value = employees.value.find(e => e.user_id === userId)
  // 加载该员工的年假数据...
}

// 显示弹窗
const showHistory = () => {
  dialogType.value = 'history'
  dialogTitle.value = '请假明细'
  dialogVisible.value = true
}

const showRules = () => {
  dialogType.value = 'rules'
  dialogTitle.value = '计算规则'
  dialogVisible.value = true
}

const showAdjustment = () => {
  dialogType.value = 'adjustment'
  dialogTitle.value = '调整年假额度'
  dialogVisible.value = true
}

const showExport = () => {
  dialogType.value = 'export'
  dialogTitle.value = '批量导出'
  dialogVisible.value = true
}

const showYearEnd = () => {
  dialogType.value = 'yearEnd'
  dialogTitle.value = '年终清算'
  dialogVisible.value = true
}
</script>

<style scoped>
.loading {
  padding: 24px;
}

.balance-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 32px;
  border-radius: 16px;
  text-align: center;
  margin-bottom: 16px;
}

.balance-card .label {
  font-size: 14px;
  opacity: 0.9;
  margin-bottom: 8px;
}

.balance-card .number {
  font-size: 56px;
  font-weight: bold;
  margin-bottom: 8px;
}

.balance-card .number.negative {
  color: #ff6b6b;
}

.balance-card .sub {
  font-size: 14px;
  opacity: 0.9;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.stat-item {
  background: white;
  border-radius: 12px;
  padding: 16px 8px;
  text-align: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.stat-item .label {
  font-size: 12px;
  color: #999;
  margin-bottom: 8px;
}

.stat-item .number {
  font-size: 28px;
  font-weight: bold;
  color: #333;
}

.stat-item .note {
  font-size: 10px;
  color: #ff6b6b;
  margin-top: 4px;
}

.menu-list {
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.menu-item {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.2s;
}

.menu-item:last-child {
  border-bottom: none;
}

.menu-item:hover {
  background: #f8f8f8;
}

.menu-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 16px;
  font-size: 20px;
}

.menu-icon.blue { background: #e3f2fd; }
.menu-icon.green { background: #e8f5e9; }
.menu-icon.purple { background: #f3e5f5; }
.menu-icon.orange { background: #fff3e0; }

.menu-text {
  flex: 1;
}

.menu-text .title {
  font-size: 16px;
  font-weight: 500;
  color: #333;
}

.menu-text .desc {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}

/* HR 视图 */
.hr-view .employee-select {
  width: 100%;
  margin: 16px 0;
}

.hr-view .action-buttons {
  display: flex;
  gap: 12px;
  margin: 16px 0;
}

.hr-view .admin-tools {
  background: white;
  padding: 24px;
  border-radius: 12px;
  margin-top: 16px;
}

.hr-view .admin-tools h3 {
  margin: 0 0 16px;
}
</style>
