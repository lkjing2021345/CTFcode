# VM Image 虚拟机镜像

> 已装：`qemu-img qemu-nbd losetup edk2-ovmf sleuthkit`
> Agent 只做**转换/离线读取**；真正**启动 GUI 虚拟机**交人工。

## 格式对照
| 来源 | 后缀 |
|---|---|
| VMware | `.vmdk`(磁盘)、`.vmx`(配置)、`.vmem/.vmsn/.vmss`(内存/快照) |
| VMware 导出包 | `.ova` / `.ovf` |
| VirtualBox | `.vdi` |
| Hyper-V | `.vhd` / `.vhdx` |
| QEMU | `.qcow2` / `.raw` |

## 转换
```bash
qemu-img convert -f vmdk -O qcow2 disk.vmdk disk.qcow2   # VMware
qemu-img convert -f vdi  -O qcow2 disk.vdi  disk.qcow2   # VirtualBox
qemu-img convert -f vhdx -O qcow2 disk.vhdx disk.qcow2   # Hyper-V
qemu-img convert -O qcow2 disk.vmdk disk.qcow2           # 省略 -f 自动探测
qemu-img info disk.qcow2                                  # 看格式/大小
```
`.ova` 是 tar 包：
```bash
tar xvf box.ova            # 解出 *.ovf + *.vmdk
qemu-img convert -f vmdk -O qcow2 disk.vmdk disk.qcow2
```

## 不启动系统、直接看里面的文件（Agent 首选）
qcow2 先转 raw，再用 sleuthkit 读（不需要 root）：
```bash
qemu-img convert -O raw disk.qcow2 disk.raw
mmls disk.raw && fls -r -o <偏移> disk.raw
```

## 启动（GUI，交人工）
```bash
qemu-system-x86_64 -enable-kvm -cpu host -smp 4 -m 4096 \
  -drive file=disk.qcow2,if=virtio -nic user,model=virtio -vga qxl -display gtk
```
或 `virt-manager` → 新建 → **Import existing disk image** → 选 qcow2。

## 排错
- 进不了系统：`if=virtio` 换 `if=ide`。
- UEFI 启动：`-bios /usr/share/edk2/x64/OVMF.fd`（edk2-ovmf 已装）。
- 内存/快照文件（`.vmem/.vmsn`）→ 用 `forensics` skill 的 Volatility3。
