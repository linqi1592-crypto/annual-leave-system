
// ==================== HR 功能模块 ====================
const HR = {
    // 员工选择
    async onEmployeeSelect(employeeId) {
        if (!employeeId) {
            document.getElementById('employeeContent').innerHTML = '';
            return;
        }
        await Renderer.renderEmployeeDetail(employeeId);
    },

    // 显示调整弹窗
    showAdjustmentModal() {
        const modal = document.getElementById('detailModal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');
        
        modal.classList.add('active');
        title.textContent = '调整年假额度';
        
        body.innerHTML = `
            <div class="form-group">
                <label class="form-label">员工</label>
                <input type="text" class="form-input" value="${state.currentEmployee.name}" disabled>
            </div>
            <div class="form-group">
                <label class="form-label">调整额度（天）</label>
                <input type="number" class="form-input" id="adjAmount" step="0.5" placeholder="正数增加，负数减少">
                <div style="font-size: 12px; color: #999; margin-top: 4px;">例如：+1.5 或 -0.5</div>
            </div>
            <div class="form-group">
                <label class="form-label">调整原因</label>
                <textarea class="form-textarea" id="adjReason" placeholder="请说明调整原因..."></textarea>
            </div>
            <div class="btn-group">
                <button class="btn btn-primary" onclick="HR.submitAdjustment()">确认调整</button>
                <button class="btn btn-secondary" onclick="UI.closeModal()">取消</button>
            </div>
        `;
    },

    // 提交调整
    async submitAdjustment() {
        const amount = parseFloat(document.getElementById('adjAmount').value);
        const reason = document.getElementById('adjReason').value;
        
        if (isNaN(amount)) {
            alert('请输入有效的调整额度');
            return;
        }
        
        if (!reason.trim()) {
            alert('请输入调整原因');
            return;
        }
        
        try {
            await API.createAdjustment({
                employee_name: state.currentEmployee.name,
                year: new Date().getFullYear(),
                adjust_amount: amount,
                reason: reason
            });
            
            alert('调整成功！');
            UI.closeModal();
            await Renderer.renderEmployeeDetail(state.currentEmployee.id);
        } catch (error) {
            alert('调整失败: ' + error.message);
        }
    },

    // 显示导出弹窗
    showExportModal() {
        const modal = document.getElementById('detailModal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');
        
        modal.classList.add('active');
        title.textContent = '批量导出年假数据';
        
        const currentYear = new Date().getFullYear();
        
        body.innerHTML = `
            <div class="form-group">
                <label class="form-label">导出年份</label>
                <select class="form-select" id="exportYear">
                    <option value="${currentYear}">${currentYear}年</option>
                    <option value="${currentYear - 1}">${currentYear - 1}年</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">导出格式</label>
                <div class="export-buttons">
                    <button class="btn btn-primary" onclick="HR.doExport('csv')">导出 CSV</button>
                    <button class="btn btn-primary" onclick="HR.doExport('xlsx')">导出 Excel</button>
                </div>
            </div>
        `;
    },

    // 执行导出
    async doExport(format) {
        const year = document.getElementById('exportYear').value;
        
        try {
            await API.exportData(year, format);
            UI.closeModal();
        } catch (error) {
            alert('导出失败: ' + error.message);
        }
    },

    // 显示年终清算弹窗
    showYearEndModal() {
        const modal = document.getElementById('detailModal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');
        
        modal.classList.add('active');
        title.textContent = '年终清算';
        
        const currentYear = new Date().getFullYear();
        
        body.innerHTML = `
            <div class="form-group">
                <label class="form-label">清算年份</label>
                <select class="form-select" id="settlementYear">
                    <option value="${currentYear - 1}">${currentYear - 1}年</option>
                    <option value="${currentYear}">${currentYear}年</option>
                </select>
            </div>
            <div class="btn-group">
                <button class="btn btn-primary" onclick="HR.previewYearEnd()">预览清算</button>
                <button class="btn btn-secondary" onclick="UI.closeModal()">取消</button>
            </div>
            <div id="settlementPreview"></div>
        `;
    },

    // 预览年终清算
    async previewYearEnd() {
        const year = parseInt(document.getElementById('settlementYear').value);
        const previewDiv = document.getElementById('settlementPreview');
        
        previewDiv.innerHTML = '<div class="loading">正在计算...</div>';
        
        try {
            const data = await API.getYearEndPreview(year);
            state.yearEndPreviewData = data;
            
            const carryoverEmployees = data.details.filter(d => d.carryover_days > 0);
            
            previewDiv.innerHTML = `
                <div class="settlement-summary" style="margin-top: 16px;">
                    <div class="settlement-summary-row"><span>清算年份</span><span>${data.year}年</span></div>
                    <div class="settlement-summary-row"><span>涉及员工</span><span>${data.total_employees}人</span></div>
                    <div class="settlement-summary-row"><span>应结转天数</span><span style="color: #4caf50;">${data.total_carryover}天</span></div>
                    <div class="settlement-summary-row"><span>应清零天数</span><span style="color: #f44336;">${data.total_cleared}天</span></div>
                </div>
                
                ${carryoverEmployees.length > 0 ? `
                <div style="margin-top: 16px;">
                    <div style="font-weight: 600; margin-bottom: 8px;">结转明细（前5条）</div>
                    ${carryoverEmployees.slice(0, 5).map(e => `
                        <div class="settlement-detail-item">
                            <span>${e.employee_name}</span>
                            <span>年末${e.year_end_balance}天 → 结转${e.carryover_days}天</span>
                        </div>
                    `).join('')}
                </div>
                ` : ''}
                
                <div class="btn-group" style="margin-top: 16px;">
                    <button class="btn btn-danger" onclick="HR.confirmYearEnd()">确认清算</button>
                    <button class="btn btn-secondary" onclick="UI.closeModal()">取消</button>
                </div>
                
                <div class="warning-box" style="margin-top: 16px;">
                    ⚠️ 确认后将自动生成下一年度的结转调整记录，此操作不可撤销！
                </div>
            `;
        } catch (error) {
            previewDiv.innerHTML = `<div class="error">❌ ${error.message}</div>`;
        }
    },

    // 确认年终清算
    async confirmYearEnd() {
        if (!state.yearEndPreviewData) return;
        
        if (!confirm('确定要执行年终清算吗？此操作将生成结转记录并不可撤销。')) {
            return;
        }
        
        try {
            const result = await API.confirmYearEndSettlement(
                state.yearEndPreviewData.year,
                state.yearEndPreviewData.details.map(d => ({
                    employee_name: d.employee_name,
                    year_end_balance: d.year_end_balance,
                    carryover_days: d.carryover_days,
                    cleared_days: d.cleared_days
                }))
            );
            
            alert(`清算完成！\n涉及员工：${result.total_employees}人\n结转天数：${result.total_carryover}天`);
            UI.closeModal();
        } catch (error) {
            alert('清算失败: ' + error.message);
        }
    }
};

// ==================== 弹窗模块 ====================
const Modal = {
    async showDetail(type) {
        if (!state.currentEmployee) return;
        
        const modal = document.getElementById('detailModal');
        const title = document.getElementById('modalTitle');
        const body = document.getElementById('modalBody');
        
        modal.classList.add('active');
        body.innerHTML = '<div class="loading">加载中...</div>';
        
        try {
            if (type === 'history') {
                title.textContent = '请假明细';
                const data = await API.queryLeaveHistory(state.currentEmployee.id);
                body.innerHTML = Renderer.renderLeaveHistory(data);
            } else if (type === 'rules') {
                title.textContent = '计算规则';
                const data = await API.queryLeaveRules(state.currentEmployee.id);
                body.innerHTML = Renderer.renderLeaveRules(data);
            } else if (type === 'adjustments') {
                title.textContent = '调整记录';
                body.innerHTML = await Renderer.renderAdjustments(state.currentEmployee.name, new Date().getFullYear());
            }
        } catch (error) {
            body.innerHTML = `<div class="error">❌ ${error.message}</div>`;
        }
    }
};

// ==================== 认证模块 ====================
const Auth = {
    // 执行飞书登录
    async doLogin() {
        document.getElementById('content').innerHTML = '<div class="loading">正在获取授权...</div>';
        
        try {
            if (typeof tt === 'undefined') {
                document.getElementById('content').innerHTML = `
                    <div class="error">请在飞书客户端中打开此应用</div>
                    <div style="margin-top: 16px; padding: 16px; background: #f5f5f5; border-radius: 8px;">
                        <p style="font-size: 14px; color: #666;">开发测试模式：</p>
                        <button class="btn btn-secondary" onclick="Auth.devLogin()" style="margin-top: 8px;">开发测试登录</button>
                    </div>
                `;
                return;
            }
            
            tt.requestAuthCode({
                appId: CONFIG.FEISHU_APP_ID,
                success: async (res) => {
                    try {
                        document.getElementById('content').innerHTML = '<div class="loading">正在登录...</div>';
                        await API.loginWithFeishu(res.code);
                        await App.init();
                    } catch (error) {
                        UI.showError('登录失败: ' + error.message);
                    }
                },
                fail: (err) => {
                    UI.showError('获取授权码失败: ' + JSON.stringify(err));
                }
            });
        } catch (error) {
            UI.showError('登录初始化失败: ' + error.message);
        }
    },

    // 开发测试登录
    async devLogin() {
        state.authToken = 'dev_token_' + Date.now();
        localStorage.setItem('leave_auth_token', state.authToken);
        state.currentUser = {
            name: '测试用户',
            is_hr: true,
            employee_id: 'test_001'
        };
        await App.init();
    }
};

// ==================== 应用初始化 ====================
const App = {
    async init() {
        document.getElementById('content').innerHTML = '<div class="loading">加载中...</div>';
        
        try {
            if (!state.currentUser) {
                state.currentUser = await API.getCurrentUser();
            }
            
            if (state.currentUser.is_hr) {
                await Renderer.renderHRView();
            } else if (state.currentUser.employee_id) {
                state.currentEmployee = {
                    id: state.currentUser.employee_id,
                    name: state.currentUser.employee_name || state.currentUser.name
                };
                const data = await API.queryLeaveBalance(state.currentUser.employee_id);
                Renderer.renderEmployeeView(data);
            } else {
                document.getElementById('content').innerHTML = `
                    <div class="error">未找到您的员工信息，请联系 HR 补充「飞书Open ID」字段</div>
                `;
            }
        } catch (error) {
            if (error.message.includes('登录已过期')) return;
            UI.showError('初始化失败: ' + error.message);
        }
    },

    async checkLogin() {
        if (state.authToken) {
            await this.init();
        } else {
            UI.showLoginScreen();
        }
    }
};

// ==================== 启动 ====================
// 点击弹窗外部关闭
document.getElementById('detailModal').addEventListener('click', (e) => {
    if (e.target.id === 'detailModal') {
        UI.closeModal();
    }
});

// 启动应用
App.checkLogin();
