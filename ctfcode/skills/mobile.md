# Mobile 安卓

> 已装：`jadx`、`apktool`、`frida`(venv)、`java`
> 缺：`adb`（装：`sudo pacman -S android-tools`）、`waydroid`/`genymotion`（模拟器，未装）

## 反编译（不需要设备，Agent 可直接做）
```bash
jadx -d out app.apk                       # 反编译 Java 到 out/
grep -rin "flag\|http\|password\|secret" out/ | head
apktool d app.apk -o apkout               # 资源 + smali
apktool b apkout -o repack.apk            # 改完重打包
strings -n 6 app.apk | grep -iE "flag|http"
```

## Frida（需要设备/模拟器 + adb）
```bash
frida-ps -U                               # 列手机进程
frida -U -f com.xxx.app -l hook.js        # 启动并注入
frida -U com.xxx.app -l hook.js           # 附加到已运行
```
`hook.js` 示例（改返回值）：
```javascript
Java.perform(function () {
  var C = Java.use("com.xxx.Check");
  C.verify.implementation = function () { return true; };
});
```

## 模拟器（本机暂缺，需自行准备）
- `sudo pacman -S android-tools` 拿 adb；
- 模拟器用 Android Studio AVD 或 `genymotion`（AUR）；
- MuMu 无 Linux 版。
> 纯静态题目用 jadx/apktool 即可，不需要模拟器。
