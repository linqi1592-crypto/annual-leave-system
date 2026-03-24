#!/bin/bash

# 年假查询系统启动脚本

echo "🚀 启动年假查询系统..."

# 检查 .env 文件
if [ ! -f .env ]; then
    echo "⚠️  警告: 未找到 .env 文件，使用 .env.example 作为模板"
    echo "请复制 .env.example 为 .env 并填入正确的 App Secret"
    cp .env.example .env
fi

# 加载环境变量
export $(grep -v '^#' .env | xargs)

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi

# 安装依赖
echo "📦 安装依赖..."
pip3 install -r requirements.txt -q

# 创建数据目录
mkdir -p data

# 启动服务
echo "🌐 启动 API 服务..."
echo "访问地址: http://localhost:8000"
echo "API 文档: http://localhost:8000/docs"
echo ""
python3 main.py
