#!/usr/bin/env python3
"""
patch_ksu_module.py - 修补 KernelSU 内核模块的未定义符号

模拟 ksuinit 的 load_module() 逻辑：
1. 从 kallsyms.txt 读取内核符号地址
2. 修补 .ko 文件中 SHN_UNDEF 的符号为 SHN_ABS + 真实地址
3. 输出修补后的 .ko 文件

用法: python patch_ksu_module.py <kernelsu.ko> <kallsyms.txt> <output.ko>
"""

import struct
import sys
import os

# ELF64 常量
SHN_UNDEF = 0
SHN_ABS = 0xFFF1
SHT_SYMTAB = 2
SHT_STRTAB = 3

# ELF64 Sym 结构：24 字节
# st_name(4) st_info(1) st_other(1) st_shndx(2) st_value(8) st_size(8)
SYM64_SIZE = 24
SYM64_FMT = '<IBBHQQ'


def parse_kallsyms(filename):
    """解析 kallsyms 文件，返回 {符号名: 地址} 字典"""
    symbols = {}
    with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 3:
                continue
            try:
                addr = int(parts[0], 16)
            except ValueError:
                continue
            name = parts[2]
            # 移除模块名后缀 [module_name]
            if name.startswith('['):
                continue
            # 模仿 ksuinit: 去掉 $ 或 .llvm. 后缀
            dollar_pos = name.find('$')
            llvm_pos = name.find('.llvm.')
            if dollar_pos >= 0:
                name = name[:dollar_pos]
            elif llvm_pos >= 0:
                name = name[:llvm_pos]
            # 只保留第一次出现的（有些符号可能重复）
            if name not in symbols or addr != 0:
                symbols[name] = addr
    return symbols


def read_string(data, offset):
    """从 ELF 数据中读取以 null 结尾的字符串"""
    end = data.index(b'\x00', offset)
    return data[offset:end].decode('ascii', errors='replace')


def patch_module(ko_path, kallsyms, output_path):
    """修补 .ko 文件中的未定义符号"""
    with open(ko_path, 'rb') as f:
        data = bytearray(f.read())

    # 检查 ELF magic
    if data[:4] != b'\x7fELF':
        print("错误：文件不是有效的 ELF 格式")
        return False

    # 检查是 64 位
    if data[4] != 2:
        print("错误：不是 64 位 ELF")
        return False

    # 检查是小端
    is_le = data[5] == 1
    if not is_le:
        print("错误：不是小端 ELF（ARM64 应该是小端）")
        return False

    # 解析 ELF64 头
    e_shoff = struct.unpack_from('<Q', data, 40)[0]
    e_shentsize = struct.unpack_from('<H', data, 58)[0]
    e_shnum = struct.unpack_from('<H', data, 60)[0]
    e_shstrndx = struct.unpack_from('<H', data, 62)[0]

    print(f"ELF64: {e_shnum} 个节头, 节头偏移 0x{e_shoff:x}")

    # 解析节头
    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        sh = struct.unpack_from('<IIQQQQIIQQ', data, off)
        sections.append({
            'sh_name': sh[0],
            'sh_type': sh[1],
            'sh_flags': sh[2],
            'sh_addr': sh[3],
            'sh_offset': sh[4],
            'sh_size': sh[5],
            'sh_link': sh[6],
            'sh_info': sh[7],
            'sh_addralign': sh[8],
            'sh_entsize': sh[9],
        })

    # 获取节名字符串表
    shstrtab = sections[e_shstrndx]
    shstr_off = shstrtab['sh_offset']

    # 查找 .symtab 和 .strtab
    symtab_idx = None
    strtab_idx = None
    for i, sec in enumerate(sections):
        name = read_string(data, shstr_off + sec['sh_name'])
        if name == '.symtab' and sec['sh_type'] == SHT_SYMTAB:
            symtab_idx = i
        elif name == '.strtab' and sec['sh_type'] == SHT_STRTAB:
            strtab_idx = i

    if symtab_idx is None:
        print("错误：找不到 .symtab 节")
        return False
    if strtab_idx is None:
        print("错误：找不到 .strtab 节")
        return False

    symtab = sections[symtab_idx]
    strtab = sections[strtab_idx]

    num_syms = symtab['sh_size'] // SYM64_SIZE
    print(f".symtab: {num_syms} 个符号")
    print(f".strtab 偏移: 0x{strtab['sh_offset']:x}")
    print(f"kallsyms 共 {len(kallsyms)} 个符号")
    print()

    patched_count = 0
    missing = []

    for i in range(1, num_syms):  # 跳过第 0 个空符号
        sym_off = symtab['sh_offset'] + i * SYM64_SIZE
        st_name, st_info, st_other, st_shndx, st_value, st_size = \
            struct.unpack_from(SYM64_FMT, data, sym_off)

        if st_shndx != SHN_UNDEF:
            continue

        # 获取符号名
        sym_name = read_string(data, strtab['sh_offset'] + st_name)
        if not sym_name:
            continue

        if sym_name in kallsyms:
            real_addr = kallsyms[sym_name]
            # 修补：SHN_UNDEF -> SHN_ABS, st_value -> 真实地址
            struct.pack_into(SYM64_FMT, data, sym_off,
                             st_name, st_info, st_other, SHN_ABS,
                             real_addr, st_size)
            patched_count += 1
            print(f"  ✓ {sym_name} -> 0x{real_addr:016x}")
        else:
            missing.append(sym_name)
            print(f"  ✗ 未找到: {sym_name}")

    print(f"\n修补了 {patched_count} 个符号")
    if missing:
        print(f"未找到 {len(missing)} 个符号: {', '.join(missing)}")

    # 写出修补后的文件
    with open(output_path, 'wb') as f:
        f.write(bytes(data))
    print(f"\n修补后的模块已保存到: {output_path}")

    return True


def main():
    if len(sys.argv) != 4:
        print(f"用法: python {sys.argv[0]} <kernelsu.ko> <kallsyms.txt> <output.ko>")
        print(f"示例: python {sys.argv[0]} android15-6.6_kernelsu.ko kallsyms.txt kernelsu_patched.ko")
        sys.exit(1)

    ko_file = sys.argv[1]
    kallsyms_file = sys.argv[2]
    output_file = sys.argv[3]

    if not os.path.exists(ko_file):
        print(f"错误：找不到 {ko_file}")
        sys.exit(1)
    if not os.path.exists(kallsyms_file):
        print(f"错误：找不到 {kallsyms_file}")
        sys.exit(1)

    print(f"读取内核符号: {kallsyms_file}")
    kallsyms = parse_kallsyms(kallsyms_file)
    print(f"加载了 {len(kallsyms)} 个内核符号\n")

    print(f"修补模块: {ko_file}")
    patch_module(ko_file, kallsyms, output_file)


if __name__ == '__main__':
    main()
