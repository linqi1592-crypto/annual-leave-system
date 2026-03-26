#!/bin/bash
# 年假查询系统 v1.3 部署环境测试执行脚本
# 使用方式: ./run_v1_3_tests.sh

echo "=========================================="
echo "年假查询系统 v1.3 测试执行"
echo "测试工程师: Ada"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在项目根目录
if [ ! -f "backend/main.py" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

echo ""
echo "[1/5] 检查 Python 环境..."
python3 --version || { echo -e "${RED}错误: 未找到 Python3${NC}"; exit 1; }

echo ""
echo "[2/5] 安装测试依赖..."
pip3 install pytest pyjwt -q || { echo -e "${RED}错误: 安装依赖失败${NC}"; exit 1; }
echo -e "${GREEN}✓ 依赖安装完成${NC}"

echo ""
echo "[3/5] 检查环境变量配置..."
if [ ! -f "backend/.env" ]; then
    echo -e "${YELLOW}警告: backend/.env 不存在，使用示例配置${NC}"
    cp backend/.env.example backend/.env
fi

echo ""
echo "[4/5] 执行 v1.3 功能测试..."
echo "=========================================="

# 执行测试并捕获结果
python3 -m pytest tests/test_v1_3_features.py -v --tb=short 2>&1 | tee v1_3_test_results.txt

TEST_EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=========================================="

if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}[5/5] 测试通过！所有用例执行成功${NC}"
    echo ""
    echo "测试摘要:"
    grep -E "passed|failed|error" v1_3_test_results.txt | tail -1
else
    echo -e "${RED}[5/5] 测试未通过，请检查失败用例${NC}"
    echo ""
    echo "失败用例:"
    grep -E "FAILED|ERROR" v1_3_test_results.txt | head -10
fi

echo ""
echo "=========================================="
echo "执行回归测试 (v1.1 用例)..."
echo "=========================================="

python3 -m pytest tests/test_leave_calculator.py tests/test_timezone.py -v --tb=short 2>&1 | tee v1_1_regression_results.txt

REGRESSION_EXIT_CODE=${PIPESTATUS[0]}

if [ $REGRESSION_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✓ 回归测试通过${NC}"
else
    echo -e "${RED}✗ 回归测试有失败，请检查${NC}"
fi

echo ""
echo "=========================================="
echo "测试报告生成"
echo "=========================================="

# 生成简单报告
cat > v1_3_test_summary.txt << EOF
年假查询系统 v1.3 测试执行报告
================================
执行时间: $(date '+%Y-%m-%d %H:%M:%S')
执行环境: $(python3 --version)

功能测试:
- 测试文件: tests/test_v1_3_features.py
- 用例数量: 37个
- 详细结果: v1_3_test_results.txt

回归测试:
- 测试文件: tests/test_leave_calculator.py, tests/test_timezone.py
- 用例数量: 64个
- 详细结果: v1_1_regression_results.txt

测试结论:
EOF

if [ $TEST_EXIT_CODE -eq 0 ] && [ $REGRESSION_EXIT_CODE -eq 0 ]; then
    echo "✓ 所有测试通过，系统可部署" >> v1_3_test_summary.txt
    echo -e "${GREEN}✓ 测试完成！系统可部署${NC}"
else
    echo "✗ 存在失败用例，请修复后再部署" >> v1_3_test_summary.txt
    echo -e "${RED}✗ 测试未通过，请修复后再部署${NC}"
fi

echo ""
echo "报告文件:"
echo "  - v1_3_test_summary.txt (测试摘要)"
echo "  - v1_3_test_results.txt (详细结果)"
echo "  - v1_1_regression_results.txt (回归测试)"
echo ""

exit $TEST_EXIT_CODE
