# Forensics 取证

> 已装：`sleuthkit`(fls/icat/mmls)、`testdisk`/`photorec`、`qemu-img`/`qemu-nbd`、`libewf`(ewfmount/ewfinfo)、`volatility3`(命令 `vol`)
> ⚠️ **mount/losetup/qemu-nbd 需要 sudo**（Agent 无 sudo 会失败）。所以**优先用 sleuthkit 直接读镜像，不需要 root**。

## 磁盘镜像（不需要 root，首选）
```bash
file disk.img
mmls disk.img                        # 列分区表 → 记下分区起始“扇区”偏移
fls disk.img                         # 无分区表时直接列
fls -r -o 2048 disk.img              # 有偏移时：递归列文件（-o 单位=扇区）
icat -o 2048 disk.img <inode> > out.bin      # 导出某 inode 文件
tsk_recover -o 2048 disk.img /tmp/recover    # 批量恢复（含已删除）
```
- `mmls` 给的偏移是**扇区**，直接填进 `fls -o` / `icat -o`。
- Windows 镜像重点找 `Users/*/Desktop`、`Documents`、浏览器历史、回收站 `$Recycle.Bin`。

## 需要挂载时（要 sudo，交给用户执行）
```bash
# raw
sudo losetup -Pf --show disk.img && ls /dev/loop0* && sudo mount -o ro /dev/loop0p1 /mnt
# qcow2/vmdk/vdi
sudo modprobe nbd && sudo qemu-nbd --connect=/dev/nbd0 disk.qcow2 && sudo mount -o ro /dev/nbd0p1 /mnt
```

## E01（EnCase）
```bash
ewfinfo image.E01
ewfmount image.E01 /mnt/ewf          # 挂成 raw（可能需 root），再对 /mnt/ewf/ewf1 用 sleuthkit
```

## 恢复删除文件
```bash
photorec disk.img                    # 交互式 TUI，交用户
```

## 内存镜像 Volatility3（`vol` 已装，无需 root）
```bash
vol -f mem.raw windows.info          # 先判断系统
vol -f mem.raw windows.cmdline       # 命令行（常藏 flag/密码）
vol -f mem.raw windows.pslist        # 进程
vol -f mem.raw windows.filescan
vol -f mem.raw windows.dumpfiles --pid <pid>
vol -f mem.raw linux.bash            # Linux 镜像
```
`.vmsn/.vmss` 快照先用 vmss2core 转成内存转储再分析。

**入口顺序**：cmdline → pslist → filescan/dumpfiles。
