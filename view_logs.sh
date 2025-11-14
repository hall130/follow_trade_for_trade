#!/bin/bash
# 查看后端日志的便捷脚本

echo "=== 后端日志查看工具 ==="
echo ""
echo "1. Gunicorn 访问日志"
echo "2. Gunicorn 错误日志"
echo "3. systemd Journal 日志（实时）"
echo "4. systemd Journal 日志（最近 50 条）"
echo "5. 查看所有日志位置"
echo ""

read -p "请选择 (1-5): " choice

case $choice in
    1)
        echo "=== Gunicorn 访问日志 ==="
        tail -f /root/follow_trade_for_trade/logs/gunicorn/gunicorn_access.log
        ;;
    2)
        echo "=== Gunicorn 错误日志 ==="
        tail -f /root/follow_trade_for_trade/logs/gunicorn/gunicorn_error.log
        ;;
    3)
        echo "=== systemd Journal 日志（实时）==="
        sudo journalctl -u follow-trade-api -f
        ;;
    4)
        echo "=== systemd Journal 日志（最近 50 条）==="
        sudo journalctl -u follow-trade-api -n 50 --no-pager
        ;;
    5)
        echo "=== 所有日志位置 ==="
        echo ""
        echo "Gunicorn 访问日志:"
        echo "  /root/follow_trade_for_trade/logs/gunicorn/gunicorn_access.log"
        echo ""
        echo "Gunicorn 错误日志:"
        echo "  /root/follow_trade_for_trade/logs/gunicorn/gunicorn_error.log"
        echo ""
        echo "systemd Journal 日志:"
        echo "  sudo journalctl -u follow-trade-api"
        echo ""
        echo "检查日志文件是否存在:"
        ls -lh /root/follow_trade_for_trade/logs/gunicorn/ 2>/dev/null || echo "日志目录不存在"
        ;;
    *)
        echo "无效选择"
        ;;
esac

