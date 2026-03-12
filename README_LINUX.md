通过claude实现的archlinux脚本
原项目地址：https://github.com/xunchahaha/mi_nobl_root

我是archlinux，所以
adb和fastboot的安装为：paru -S android-sdk-platform-tools
python的安装为：sudo pacman -S python

运行指令如下：
chmod +x selinux_permissive.sh
./selinux_permissive.sh
chmod +x ksu_oneclick.sh
./ksu_oneclick.sh


关于修复Lsposed：
刷入lsposed后，重启获取完root后
将文件夹中的fix_lspd.sh放入手机
给MT管理器root权限
用mt管理器使用root权限，系统环境运行
tips:
不知道为什么，我不能按照mi_nobl_root的第二步来修复
会导致变砖（给我干进recovry里了，差点没了）
