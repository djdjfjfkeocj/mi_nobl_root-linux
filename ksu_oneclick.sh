#!/usr/bin/env bash
# ksu_oneclick.sh — KernelSU 一键加载（Linux / Arch Linux 版）
# 将 Windows ksu_oneclick.bat 功能移植到 Linux
# 每次开机后运行此脚本
set -euo pipefail

echo "═══════════════════════════════════════════════"
echo "  KernelSU 一键加载 v2 (Linux/Arch 版)"
echo "  每次开机后运行此脚本"
echo "═══════════════════════════════════════════════"
echo ""

# ─── 定位脚本目录 ───
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KO="$DIR/android15-6.6_kernelsu.ko"
PATCHED="$DIR/kernelsu_patched.ko"
KSUD="$DIR/ksud-aarch64-linux-android"
PATCHER="$DIR/patch_ksu_module.py"
KALLSYMS="$DIR/kallsyms.txt"

# ─── 检查依赖 ───
echo "检查依赖..."

if ! command -v adb &>/dev/null; then
    echo "[X] 未找到 adb，请先安装: sudo pacman -S android-tools"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo "[X] 未找到 python3，请先安装: sudo pacman -S python"
    exit 1
fi

echo "[OK] 依赖检查通过"
echo ""

# ─── 检查 ADB ───
echo "检查 ADB 连接..."
if ! adb get-state &>/dev/null; then
    echo "[X] 没有 ADB 设备，请连接手机并确认 USB 调试已开启"
    exit 1
fi
echo "[OK] ADB 已连接: $(adb get-state)"
echo ""

# ─── 推送脚本 + ksud ───
echo "推送文件到设备..."
adb push "$DIR/ksu_step1.sh"         /data/local/tmp/ksu_step1.sh       >/dev/null
adb push "$DIR/ksu_step2.sh"         /data/local/tmp/ksu_step2.sh       >/dev/null
adb push "$KSUD"                      /data/local/tmp/ksud-aarch64        >/dev/null
# 赋予脚本执行权限（Linux adb push 不保留权限位）
adb shell "chmod 755 /data/local/tmp/ksu_step1.sh /data/local/tmp/ksu_step2.sh /data/local/tmp/ksud-aarch64"
echo "[OK] 文件已推送并赋权"
echo ""

# ═════════════════════════════════════
echo "[1/5] 拉取 kallsyms..."
# ═════════════════════════════════════

# 始终重新拉取（重启后 KASLR 地址变了）
rm -f "$KALLSYMS" "$PATCHED"

adb shell "service call miui.mqsas.IMQSNative 21 i32 1 s16 'sh' i32 1 s16 '/data/local/tmp/ksu_step1.sh' s16 '/storage/emulated/0/ksu_result.txt' i32 60" >/dev/null

echo "等待 kallsyms 拉取 (15秒)..."
sleep 15

# 拉取到 PC
adb pull /data/local/tmp/kallsyms.txt "$KALLSYMS" >/dev/null 2>&1 || true

if [ ! -f "$KALLSYMS" ]; then
    echo "[!] 第一次拉取失败，多等10秒重试..."
    sleep 10
    adb pull /data/local/tmp/kallsyms.txt "$KALLSYMS" >/dev/null 2>&1 || true
fi

if [ ! -f "$KALLSYMS" ]; then
    echo "[X] kallsyms 拉取失败"
    exit 1
fi
echo "[OK] kallsyms 已拉取 ($(wc -l < "$KALLSYMS") 行)"
echo ""

# ═════════════════════════════════════
echo "[2/5] 补丁内核模块 (Python3)..."
# ═════════════════════════════════════

python3 "$PATCHER" "$KO" "$KALLSYMS" "$PATCHED"

if [ ! -f "$PATCHED" ]; then
    echo "[X] 补丁文件未生成"
    exit 1
fi
echo "[OK] 补丁完成"
echo ""

# ═════════════════════════════════════
echo "[3-5/5] 加载模块 + 部署ksud + 触发Manager..."
# ═════════════════════════════════════

# 推送补丁后的 ko
adb push "$PATCHED" /data/local/tmp/kernelsu_patched.ko >/dev/null

# 执行 step2 (insmod + ksud + trigger)
adb shell "service call miui.mqsas.IMQSNative 21 i32 1 s16 'sh' i32 1 s16 '/data/local/tmp/ksu_step2.sh' s16 '/storage/emulated/0/ksu_result.txt' i32 60" >/dev/null

echo "等待加载完成 (25秒)..."
sleep 25

# 显示完整结果
echo ""
echo "══════════ 执行结果 ══════════"
adb shell cat /storage/emulated/0/ksu_result.txt
echo ""

# 检查是否成功
if adb shell cat /storage/emulated/0/ksu_result.txt 2>/dev/null | grep -q "ALL_DONE"; then
    echo "═══════════════════════════════════════════════"
    echo "  加载完成！打开 KernelSU Manager 检查状态"
    echo "  如需修复 LSPosed: 运行 fix_lspd.sh 相关命令"
    echo "═══════════════════════════════════════════════"
else
    echo "═══════════════════════════════════════════════"
    echo "  [!] 可能未完全成功，请检查上面的输出"
    echo "═══════════════════════════════════════════════"
    exit 1
fi
