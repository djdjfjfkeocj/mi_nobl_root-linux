#!/bin/bash
# SELinux 设置为宽容模式（permissive）
# 适用于Linux平台

set -e

echo ">>> 重启进入 bootloader..."
adb reboot bootloader

echo ">>> 等待手机重启进入 fastboot，请确认手机屏幕显示 FASTBOOT 后按回车继续..."
read -r

echo ">>> 设置 SELinux 为宽容模式..."
fastboot oem set-gpu-preemption 0 androidboot.selinux=permissive

echo ">>> 继续启动..."
fastboot continue

echo ">>> 完成！"
