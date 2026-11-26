# SCMCU IDE for VS Code（SC8 系列单片机）

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.10-orange.svg)](https://github.com/2blaowang/SCMCU_IDE-VSCODE-Plugin/releases)

**仓库地址（国内建议走 Gitee）：**

| 平台 | 地址 |
|---|---|
| GitHub | https://github.com/2blaowang/SCMCU_IDE-VSCODE-Plugin |
| Gitee（国内镜像） | https://gitee.com/wangzhengyangsb/zhongweiscmcuidevscodecha |

在 VS Code 中编译 SC8F/SC8P 系列单片机工程（基于 SCMCU_IDE 的 MPLAB XC8/PICC 工具链），
支持芯片设置、芯片切换、编译器自动检测、错误跳转，生成与官方烧录器**校验值完全一致**的 `.scx` 烧录文件。
另内置 **SCMCU 编程器识别**（底栏实时显示型号）、**一键编译下载**、**只下载（不编译）**（两者均已实烧闭环验证，覆盖 Writer 烧录器与 CMS-ICE6 仿真器两条通道）。

## 功能

| 命令 | 说明 |
|---|---|
| `SCMCU: 编译` | 编译工程（自动读 .scw 的 Device/源文件顺序/配置字），生成 `.hex` + `.scx`，输出 **CfgCRC/CfgSum** |
| `SCMCU: 一键编译下载` | 编译成功后自动连接编程器烧录（Writer 烧录器走 `.scx`，CMS-ICE6 走 `.hex`，见「一键编译下载」） |
| `SCMCU: 只下载（不编译）` | **跳过编译**，直接烧写 `build/` 下上一次的固件（改了硬件选项、只想重烧时用，省一次编译） |
| `SCMCU: 芯片设置` | 图形化配置 WDT/PROTECT/LVR_SEL/FCPU_DIV 等硬件选项，写回 .scw **并同步写入已有 .scx 配置字区**（单例窗口） |
| `SCMCU: 选择芯片型号` | 从 IDE 芯片库选择型号，更新 .scw 的 Device= |
| `SCMCU: 源文件管理` | 图形化列出/添加/移除/排序 `.scw` 的 `SourceFile=`（按钮或**拖拽**均可，顺序即编译顺序），即时写回工程文件 |
| `SCMCU: 配置编译器目录` | 手动指定 SCMCU_IDE 安装目录 |
| `SCMCU: 自动检测编译器` | 自动扫描常见安装路径/盘符/环境变量 `SCMCU_IDE_HOME` |
| `SCMCU: 设置芯片型号 / 设置配置字 (脱离 .scw)` | 输入框直接写工作区设置（scw-less 模式用） |
| `SCMCU: 启动` | 手动触发加载——找不到 .scw 时若弹窗选了「不加载」，之后用本命令启用 |
| `SCMCU: 规范化配置字` | 修复 scw-less 模式下配置字高位「串芯片」错误（一般加载后自动执行一次，见「配置字规范化」） |

**状态栏**：

- 底部**左侧**按钮组（点击即用）：`$(chip)` 型号(点击切换) ・ `$(settings-gear)` 芯片设置 ・ `$(debug-start)` 编译 ・ `$(cloud-download)` 只下载 ・ `$(zap)` 编译下载 ・ `$(files)` 源文件
- 底部**右侧**：编程器识别（`$(circuit-board) WRITER8 LITE` / `CMS-ICE6 (仿真器)`；点击立即刷新，窗口聚焦时 5s 自动轮询，见「编程器识别」）
- 找不到 `.scw` 时右下角弹「加载」通知（仅一个按钮，约 20s 无操作自动消失 = 本次不加载；`scmcu.noScwBehavior` 可改为直接加载 / 永不加载）
## 使用

1. 用 VS Code 打开包含 `.scw` 工程文件的文件夹
2. 首次使用执行 `SCMCU: 自动检测编译器`（或 `SCMCU: 配置编译器目录`）
3. 执行 `SCMCU: 编译` —— 产物在 `build/` 下：
   - `<输出名>.hex`：Intel HEX 程序文件
   - `<输出名>.scx`：烧录文件（含配置字 + 程序，可直接用 SCMCU_Writer 烧录）
4. 改硬件选项（LVR 电压、WDT 等）→ `SCMCU: 芯片设置` → 选择 → 保存
5. 芯片切换 → 点击状态栏芯片型号 → 选择
6. 管理要编译的源文件 → 点击状态栏「源文件」或执行 `SCMCU: 源文件管理` → 添加 / 移除 / 上移下移（顺序即编译顺序，不可随意打乱）

## 脱离 .scw 编译（无工程文件模式）

适用于手上只有一堆 `.c/.asm/.s` 源码、没有官方 `.scw` 工程文件的场景。插件**不再强依赖 `.scw`**，改为从设置读取芯片型号与配置字、自动扫描源文件。

前提（设置 `settings.json` / 扩展设置页「SCMCU」，**或**用命令面板直接填）：

- `scmcu.device`（**必填**）：芯片型号，如 `"SC8F052A04"`。留空则编译报错提示先配置。
- `scmcu.configWords`（**建议填**）：4 个配置字（十六进制字符串数组），如 `["0x1FFF","0x3FFF","0x3FFF","0x3FFF"]`。
  **留空则用芯片默认未编程值**，编译时给出 ⚠️ 警告——烧录前务必核对硬件选项（振荡器/看门狗/LVR 等），否则固件可能不工作。
- `scmcu.sourceFiles`（**可选**）：源文件清单（相对工程根目录，顺序敏感）。`[]`（默认）= 自动扫描工程下所有 `.c/.asm/.s`；非空 = 按数组顺序编译。**优先于自动扫描**。可通过状态栏「源文件」/ 命令面板的「源文件管理」面板维护。

> 若扩展设置页里找不到这些条目（多为装了旧版 / 装完没重载窗口），可直接用命令面板：
> - `SCMCU: 设置芯片型号 (脱离 .scw)` —— 输入框填型号，写入「工作区设置」
> - `SCMCU: 设置配置字 (脱离 .scw)` —— 输入框填 4 个配置字（逗号分隔），写入「工作区设置」

行为：

- 打开含源码的文件夹后，只要设置了 `scmcu.device`，状态栏即出现「**芯片型号**（点击改型号 / scw 模式下切库）」+「**芯片设置**」+「**构建**」+「**源文件**」四个按钮。`.scw` 存在时面板写回 `.scw`；不存在时写回对应工作区设置。
- 源文件 = 若 `scmcu.sourceFiles` 非空，按其顺序编译；否则自动扫描工程下全部 `.c/.asm/.s`（排除 `build/`、`node_modules/`、`.git/` 等），按字母序。
  **注意**：XC8 的 psect 分配依赖编译顺序，若默认字母序导致链接异常，**用「源文件管理」面板维护一个有序清单写入 `scmcu.sourceFiles`**，或继续用 `.scw` 的 `SourceFile=` 精确控制顺序。
- 产物同样是 `build/<name>.hex` + `build/<name>.scx`，编译参数与 CfgCRC/CfgSum 输出与 `.scw` 模式一致。

## 配置字规范化（防串芯片）

14-bit 芯片（SC8F052 等，未编程值 `0x3FFF`）的工程，若工作区 `scmcu.configWords` 是从 16-bit 芯片
（SC8F072 等，`0xFFFF`）工程整体复制过来的，会出现**高位错误**（典型：`FFFB,FAEF,FFFF,FFFF`，
应为 `3FFB,3FEF,3FFF,3FFF`），烧进芯片后硬件选项错乱。插件内置两层防护：

- **自动**：加载工程时若同时满足「无 `.scw` + 已设 `scmcu.device` + 已手填 `scmcu.configWords`」，
  自动执行一次规范化——**有变化**才写回 `scmcu.configWords`（并尽力同步 build 目录 .scx）+ 提示
  before → after；已正确 / 未编程工程**静默跳过**。同一工作区只自动执行一次，想再跑用下面的命令。
- **手动**：`SCMCU: 规范化配置字`。

规则（核心 `normalizeConfigWordsCore`，src/chip.ts）：

- 芯片配置模板 `mcu/config/<chip>.cfg` **已定义**的位（硬件选项覆盖位）→ 保留基底当前值
- **未定义**的固定位 → 按芯片位宽复位到未编程值（**幂等**：重复执行结果不变）
- 末尾统一按芯片位宽清高位（`& hexmcu`）
- 纯 16-bit 芯片（hexmcu=`0xFFFF`）**只做位宽 mask、不重置未定义位** → SC8F072 的 `FAEF`
  （bit4/8/10=0 的隐藏位）不会被误改成全 1

芯片位宽来源：优先 `.ini` 的 `HEXMCU`；缺省时按型号兜底（`resolveHexmcu`：SC8F05x/SC8F070 等
14-bit → `0x3FFF`；SC8F072+、FC*/SC8P* → `0xFFFF`）。

## 构建输出示例

```
[SCMCU] 芯片: SC8P052B  ROM: 1024 word
[SCMCU] 源文件(8): main.c interrupt.c motor.c key.c LED.c battery.c CMP.c sleep.c
[SCMCU] include: src | inc | data/include
[SCMCU] 配置字: 3FF3,3FAB,3FFF,FFFF
[SCMCU] 硬件选项: WDT=DISABLE  PROTECT=ENABLE  LVR_SEL=2.0V  FCPU_DIV=4T  ICSPPORT_SEL=NORMAL  EXT_RESET=DISABLE
[SCMCU] 烧录文件: ...\build\SCMCU_Project.scx (2304 字节)
[SCMCU] CfgCRC(Hex) -- 0x9202  CfgSum(Hex) -- 0x156D
[SCMCU] ✅ 构建成功
```

> **配置字不用再靠人脑翻译十六进制**：紧跟配置字那一行的「硬件选项」就是把 4 个配置字
> 按芯片模板 `mcu/config/<芯片>.cfg`（IDE 芯片设置面板的同一份定义）反查出来的可读状态，
> 顺序与 IDE 面板一致（WDT / PROTECT / LVR_SEL / FCPU_DIV / ICSPPORT_SEL / EXT_RESET …），
> 某个节的所有位都对不上时显示 `= ?`。模板缺失或芯片名不在 IDE 里时该行自动省略。

## 与烧录器校验值完全一致（CfgSum / CfgCRC）

插件生成的 `.scx`，用官方烧录器 SCMCU_Writer 打开显示的 **CfgSum / CfgCRC 与插件计算完全一致**。
算法直接对应烧录器核心库 `Writer.Core.dll` 反编译出的 **`GetCheckSum` / `GetDataCRC16`** 两个函数：

```csharp
// GetDataCRC16:  GetCRC16L_1021_FFFF_0000(0xFFFF, romDatas + bootRom + GetConfigByteDatas())
// GetCheckSum:   num2 += ConfigDatas[i] & 0xFF;  if (McuType==CMSCore) num2 += ConfigDatas[i] >> 8;
```

```
CfgSum = (Σ 程序区字节 [0x100,end) + Σ 前 N 个配置字 [低字节 + (CMSCore ? 高字节 : 0)]) & 0xFFFF
CfgCRC = CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF, xorout=0)，对 [程序区字节 + 前 N 个配置字槽低+高字节] 计算
N      = 该芯片的配置字数量（参与校验和的槽数）
```

> `.scx` 配置区**定长 4 槽**（buildScx 写死 8 字节），但烧录器按**芯片数据库的配置字数量**只取前 N 槽：
> SC8F052 = 2 槽、SC8F072 = 4 槽。**N 以 `CFG_WORD_COUNT` 实测表为准**，不能看 `.scw` 列了几个——`.scw` 的
> `config=` 会用 `FFFF` 补齐到 4 个（如 SC8F052 的 `3FFB,3FEF,FFFF,FFFF` 实际只有 2 个字）。未收录芯片
> 由 build 从芯片配置模板 `mcu/config/<chip>.cfg` 推导（最大 word 索引 + 1）兜底，最后默认 4。
> 早期「只计连续非 0xFFFF 槽」的算法对 SC8F072（槽 0=FFFF）数成 0 槽算错；硬编码 4 槽又让 SC8F052 算错。

实测样本（已用官方烧录器 SCMCU_Writer 显示值逐位核对）：

| 工程 | 芯片 | 配置字 | N | CfgSum | CfgCRC |
|---|---|---|---|---|---|
| test1 | SC8F052 | 3FFB,3FEF | 2 | A5AE | 20CD | ✓ 与烧录器一致（2 槽） |
| test2 | SC8F052 | 7FFF,FFEF | 2 | AA75 | 9665 | 旧算法样本（同为 2 槽，规则一致） |
| test3 | SC8F072 | FFFF,FAEF,FFFF,FFFF | 4 | 4619 | EC0D | ✓ 与烧录器一致（4 槽） |

> 新芯片接入：若某芯片烧录器显示的 CfgSum/CfgCRC 与插件不符，先确认该芯片的配置字数量与是否 CMSCore
> （非 CMS 内核只加配置字低字节），把芯片名补进 `src/scx.ts` 的 `CFG_WORD_COUNT` / `NON_CMS_CORE` 即可。

## 编程器识别（底栏右侧）

识别 Windows 下已连接的 SCMCU 设备，底栏右侧实时显示型号。分两类：

**Writer 烧录器**（USB HID，**VID 0x1209**；来自 `Writer.Core.dll` 反编译设备表），区分正常 / 升级(bootloader) 模式：

| 型号 | 正常 PID | 升级(bootloader) PID |
|---|---|---|
| WRITER8 LITE | 0x0201 | 0x0101 |
| WRITER V8 | 0x0032 | 0x0011 |
| WRITER V8 PRO | 0x0023 | 0x0021 |
| ICE8 PRO | 0x1502 | 0x1102 |

**ICE 仿真器**（另一 VID）：

| 型号 | VID | PID | 说明 |
|---|---|---|---|
| CMS-ICE6 | 0x0925 | 0x0283 | 厂商串 `CMS ICE`，系统里伪装成「USB 输入设备」；状态栏显示 `CMS-ICE6 (仿真器)` |

> ✅ CMS-ICE6 是**仿真器**（VID 0x0925），走 SCMCU IDE 的私有下载通道。**本插件的「一键编译下载」与「只下载」都已支持它**：通过逐字节复刻官方 IDE V2.00.17 真实下载会话（Frida hook `WriteFile` 抓取，2026-11-26）实现，脚本 `flash/ice6_flash.py`（纯 Python 标准库 ctypes，零 pip 依赖）。识别到 ICE6 时自动改用该脚本下载编译产物 `.hex`，**不需要 SCMCU Writer**，也不再需要打开官方 IDE。
>
> 📦 **下载运行时随插件内置**（`flash/py/`，官方 embeddable Python 3.11.9，仅保留 ctypes/unicodedata 等必需组件）。
> 装完 vsix 即可直接下载，**不需要另外安装 Python**；`SCMCU_BUILD_PY` 环境变量可强制指向自己的 `python.exe`（改脚本调试时用）。
>
> ⚠️ 两点前提：① 目标板供电正常（VDD ≈ 4.5V）——断电/接触不良时帧会发出但数据不落盘；② **下载前先关闭 SCMCU IDE**，它会抢占 HID 设备并切断目标板供电（现象：后续所有块读回 `0xFF`）。

- 加载后立即检测一次；VS Code 窗口**聚焦时每 5 秒轮询**（USB 枚举约 1s/次，失焦自动停表，避免后台空耗 CPU）
- 点击状态栏立即刷新并弹结果；Tooltip 含 VID / PID / 模式；升级模式显示 `(Boot)` 并提示用 Writer 升级功能刷固件
- 未连接 → `编程器: 未连接`；识别失败 → `编程器: 检测失败`；未知 PID → 「未知编程器」（便于将来新硬件）
- 实现（src/programmer.ts，纯 Node 可单测）：优先 `pnputil /enum-devices /connected /deviceids`，失败回退 `Get-PnpDevice`；VID 白名单 1209 / 0925；仅 Windows 生效

## 一键编译下载 / 只下载（编译 → 自动烧录）

两条命令共用同一条烧录通道，区别只在**要不要先编译**：

| 命令 | 底栏按钮 | 行为 |
|---|---|---|
| `SCMCU: 一键编译下载` | `$(zap)` | 编译 → 烧写 `build/<输出名>.hex`（+`.scx`） |
| `SCMCU: 只下载（不编译）` | `$(cloud-download)` | 直接烧写 `build/` 中**上一次**的固件，不重新编译 |

「只下载」适合这些场景：改了芯片设置/配置字后想重烧、换了一片目标板、或者只想把那块已经编译好的固件再烧一次。

前置：USB 连接编程器（Writer 烧录器 **或 CMS-ICE6 仿真器**），芯片/目标板在座且供电正常。

> **用过官方 SCMCU IDE 的话，先关 IDE 并拔插一次 ICE6 的 USB 再下**。IDE 退出后 ICE6 会遗留成
> 「命令都回 `03`、擦除有效、但编程数据一位都不落盘」的状态（详见下文坑⑩），软件侧解除不了。
> 脚本能自动识别并提示，但白跑一趟不如提前插拔一下。

**两种下载通道自动选择**（由 `detectProgrammers()` 识别的 VID 决定）：
- **Writer 烧录器（VID 0x1209）**：需本机装有官方 `SCMCU_Writer`，用 `.scx` + 内置烧录助手。
- **CMS-ICE6 仿真器（VID 0x0925）**：无需 Writer，用编译产物 `.hex` + 内置 `flash/ice6_flash.py`。
  该脚本按官方 IDE V2.00.17 的**完整下载会话**逐段复刻（Frida hook 抓包逆向 + 真机验证，2026-11-26）：

  | 顺序 | 帧 | 作用 |
  |---|---|---|
  | ① | `0x50 0x53` / `0x1A` | PS 自检 + 目标链路；不就绪则 `0xA6 0x78` → `0x52` 重连目标 |
  | ② | `FC` → `18` → `1B` | 会话握手（旧版漏发） |
  | ③ | `0x17` | 芯片 ID / ROM 大小 / 高压参数（ERASE·PROGTIME·**VPPMODE=0x89**），高压由 ICE6 硬件自行产生；必须 ACK `03` |
  | ④ | `0C 02 10` | **进入编程态**（旧版漏发） |
  | ⑤ | `0x01` × N | 逐块编程，**字地址**步进 0x18、48B/帧（24 字），每帧等自己的 ACK 做流控 |
  | ⑥ | `03` (配置字=FF) → `0C 01 04` | 清配置字区 → 退出编程态 |
  | ⑦ | `0x06` × 64 | 整片回读校验 |
  | ⑧ | `03` (配置字=实际值) → `0C 01 04` | 写配置字（从同目录 `.scx` 的 `0xA0` 槽读取，换工程也不会写错） |
  | ⑨ | `0D` → `0B` → `04` → `0F` → `13` → `11`×8 → `09`×4 | **收尾序列**（旧版漏发，见坑⑦） |

  **下载过程中每个步骤只占一行**（原始协议帧会刷屏，默认不打，需要排障时给脚本加 `--debug`；
  运行中的百分比不写进输出面板，改为在 VS Code **底栏状态条**里一行滚动 `$(sync~spin) 校验 24/64`）：

  ```
  [SCMCU] 检测到 CMS-ICE6 (VID 0x0925/PID 0x0283)
  ──── CMS-ICE6 下载 ────
  固件        c:\...\build\SCMCU_Project.hex  (4096 字节, 需编程 14 块)
  配置字      FFF7 FAEF FFFF FFFF   (来源: SCMCU_Project.scx)
  选项        WDT=DISABLE  PROTECT=ENABLE  LVR_SEL=1.8V  FCPU_DIV=4T  ICSPPORT_SEL=NORMAL  EXT_RESET=DISABLE
  擦除中
  擦除完成
  下载中
  下载完成    14/14 帧，ACK 14（0.1s）
  校验中
  校验完成    64/64 页，差异 0 字（3.7s）
  结果        ✅ 校验通过 · 用时 5.6s
  *** 下载成功 ***
  ```

  - 四步对应关系：**固件** = 要烧的 `.hex` 与需编程块数；**擦除** = `0x17`（整片擦除 + 高压就绪，
    没有独立擦除命令）；**下载** = `0x01`×N 编程帧；**校验** = `0x06` 整片回读比对。
  - 每步只出两行纯文字（`xxx中` / `xxx完成 …`），不使用进度条；运行中的百分比由脚本用 `@@P` 标记
    发出去，扩展显示在状态栏那一行并在烧完后消失，因此输出面板行数固定、不随帧数增长。
  - `补烧` / `复验` 只在首轮校验出现差异时才出现；`结果` 行的 `补烧 N 轮 / 重连 N 次 / 读不到 N 页`
    也只在非零时追加。

  ⚠️ 关键坑①：抓包得到的 wire 已含首字节 ReportID(0x00)，写入前**必须剥掉**，
  否则整帧错位一字节，设备对所有命令只回通用错误码 `03 31 34`，表现为"能通信但写不进"。
  ⚠️ 关键坑②：**烧写前必须先确认目标链路就绪**。若 ICE6 只应答型号查询（`0x50 0x53`）而其余命令一律回 `14`，
  说明目标链路断了；此时要复刻 IDE 启动时的重连序列 —— `0xA6 0x78` → `0x52`（读目标寄存器，
  设备会以文本回 `[CMSC] OPTION_REG=...`）→ `0x1A` 复检。脚本已内置该预热，探测不过就**拒绝烧写**。
  ⚠️ 关键坑③：编程刚结束时 ICE6 回包会变慢，紧接着的全片校验若沿用短超时会把超时误判成数据差异
  （实测误报 1992 处）；脚本在编程后先等待，校验用宽超时并对读不到的块单独重试。
  ⚠️ 关键坑④：**绝不要在编程帧之间插读操作**。逐块「编程→回读」会让 ICE6 的编程状态机中途失效，
  表现为第 40 帧之后的块整片读回 `0xFF`。这也是"烧写卡住"的真因之一：
  旧版读到无应答后调用 `GetOverlappedResult(..., bWait=True)`，那是**无界等待**，设备不回包就永久挂住
  （现象：进程 CPU 时间恒为 0、进度停在某一帧）。现在所有 Overlapped 等待都有上限，超时即抛 `IOError` 并重连。
  ⚠️ 关键坑⑤：编程帧的 ACK 必须收走，否则塞满 HID 输入队列后设备开始拒收（实测首轮漏烧 23 块）。
  现改为**每帧读一个 ACK**，既做流控又天然节流（实测 86 帧约 1 秒）。
  ⚠️ 关键坑⑥：**读之前必须先做会话握手**（`FC` `18` `1B` + `0x52`）。不握手直接发 `0x06`，
  设备会返回填充帧 `11 1B 11 1B …`，读出来像"全是 0x111B 的垃圾"。此前一度把"某页读不到"
  归因为 `0x560` 地址怪癖，实际是漏握手导致的设备状态异常；IDE 实测连续读 64 个地址
  （`0x0000/0x0020/…/0x07E0`）全部正常。脚本里保留的 ±8 字错位读只是兜底，正常不会触发。
  ⚠️ 关键坑⑦：**`0x17` 配置帧同时完成整片擦除**——IDE 没有任何独立的擦除命令，它的
  "重新编译并下载"就是先发 `0x17`（擦除 + 高压就绪），再发 `0x01` 编程帧。实测：板上原有 82 块
  （`0x0000~0x0798`）固件，用 13 块的固件走一次下载后，`0x0200` 之后全部为 `0xFF`、0 残留。
  因此脚本只编程非空白块是安全的，不必像 IDE 那样补发 72 帧全 FF。
  ⚠️ 关键坑⑧：**`0x06` 读命令只返回每个字的低 8 位**，第二字节恒为 `0x00`。SC8F072 的指令字
  高 6 位（bit8~13）**读不回来**，IDE 也是如此（它同样是 64 次读、每字 2 字节）。所以全片校验的
  粒度天然是 8 位，无法验证高 6 位——这是协议/硬件限制，不是脚本缺陷。
  ⚠️ 关键坑⑨（**"必须给调试器断电才能再烧一次"的根因**）：IDE 下载结束后还会发一段**收尾序列**
  `0D/0B/04/0F/13 + 11×8 + 09×4`。少了它，ICE6 会停在"**擦得掉但写不进**"的状态 ——
  `0x17` 照样回 `03`、芯片照样被擦成全 `FF`、编程帧照发，但一个位都写不进去，
  只有拔插 USB（或开一次 IDE）才能恢复。本脚本把收尾放在 `finally`，**任何情况下都会发**（校验失败也发）。
  另注意：收尾帧**不能脱离上下文单独重放**，否则设备会进入数据流状态（读回 `1B` 乱码）。
  ⚠️ 关键坑⑩（**"用过官方 IDE 之后又写不进"的第二形态**）：被官方 IDE 连接过之后，ICE6 会进入另一种
  "擦得掉但写不进"——与坑⑨不同，此时它**所有命令都正常回 `03`**（`0x17` 接受、编程帧接受、ACK 齐全），
  擦除照样生效（整片变 `FF`），但**编程数据一位都不落盘**，补烧多少轮都是 0。软件侧没有能解除它的
  命令（实测 `A6 78` 重连返回 `14`，状态帧由 `09 01 00 00 …` 变成 `09 F6 01 01 …`），**只能给调试器断电**
  （拔插 ICE6 的 USB，不必重启电脑/VS Code）。脚本已能自动识别：首轮校验若"几乎全片读回 `FF` 且所有
  差异值都是 `FF`"，立即打印该结论并退出（不再空转补烧 6 轮）。
  纯 Python 标准库（ctypes），零 pip 依赖。运行时由插件自带（`flash/py/python.exe`），
  因此下载链路**不依赖用户环境里的 Python**。

Writer 通道：插件编译出 `.scx` 后，spawn 内置烧录助手 `flash/ScmcuFlashHelper.exe` 完成烧录，全程**无需打开 Writer GUI**。
助手引用 Writer 自带的 `Writer.Core.dll`（`AssemblyResolve` 动态加载，不污染安装目录），复用其加密
芯片库（SQLite，口令 `cmsxc`）与 USB HID 协议，时序与 Writer GUI 完全一致：

```
编译 → .scx → 连接编程器(版本握手/WriterID 校验)
     → 0x61 信息帧1(Series/Type/段长/WriterCount/CRC32) → 0x21 芯片名+注解
     → ROM/Config/EE 分段下发(57B/块，逐块等 ACK) → 0x60 整段 CRC 校验 → 0x50 结束(可复位运行)
```

- 入口：命令 `SCMCU: 一键编译下载` / `SCMCU: 只下载（不编译）`；底栏左侧 `$(cloud-download)` 只下载、`$(zap)` 编译下载（编译按钮旁）
- `scmcu.writerPath`：Writer 安装目录；**留空自动扫描**（盘符根 / `Work` / `Program Files` /
  `gat/sheet/中微` 下含 `library`+`data` 的 `SCMCU_Writer*` 目录）
- `scmcu.flashCount`：烧录片数（WriterCount），默认 1
- 出错场景均有明确中文报错：编程器未连接 / 型号不支持该芯片 / 芯片库无此型号 / 文件解析失败
- 助手 `--probe` 模式只验证链路（连接→芯片库→.scx 解析）**不烧录**，用于排障
- 助手依赖：x86 / .NET Framework 4.x（Win7+ 自带）；无 .NET SDK 的机器用 `python flash/build_helper.py`
  从 NuGet 拉 Roslyn 一键重编（见「开发」）

## 设置项（settings.json）

| 键 | 说明 |
|---|---|
| `scmcu.compilerPath` | SCMCU_IDE 的 `data\bin` 目录（含 picc.exe），留空自动检测 |
| `scmcu.idePath` | SCMCU_IDE 安装根目录（含 `mcu\config`），留空自动检测 |
| `scmcu.buildDir` | 编译输出目录，默认 `build` |
| `scmcu.outputName` | 产物文件名，默认 `SCMCU_Project` |
| `scmcu.sourceDirs` | **C 源文件目录**（相对工程根目录；空串 = 根目录），默认 `["src"]` |
| `scmcu.includeDirs` | **头文件 include 目录**（相对工程根目录；空串 = 根目录），默认 `["inc"]`，编译时加入 `-I` |
| `scmcu.device` | **脱离 .scw 模式必填**：芯片型号，如 `"SC8F052A04"`；留空则该模式编译报错 |
| `scmcu.configWords` | **脱离 .scw 模式建议填**：4 个配置字（十六进制字符串数组），如 `["0x1FFF","0x3FFF","0x3FFF","0x3FFF"]`；留空则用芯片默认未编程值（编译时警告） |
| `scmcu.sourceFiles` | **脱离 .scw 模式可选**：源文件清单（相对工程根，顺序即编译顺序）；`[]` = 自动扫描（用「源文件管理」面板维护） |
| `scmcu.noScwBehavior` | 找不到 `.scw` 时的行为：`prompt`（默认，右下角询问）/ `load`（直接加载）/ `skip`（不加载，可手动 `SCMCU: 启动`） |
| `scmcu.writerPath` | SCMCU_Writer 安装目录（一键编译下载用）；留空自动扫描，见「一键编译下载」 |
| `scmcu.flashCount` | 一键下载烧录片数（WriterCount），默认 `1` |

## 错误跳转（Problem 面板）

编译时 picc 输出的错误/警告会解析到 VS Code「问题」面板（`--errformat` 格式化为机器可读格式），
点击即可跳转到对应源文件行号。编译输出仍保留在「SCMCU」输出面板。

## 工作原理（与 IDE 一致性的保证）

- **源文件顺序**：按 `.scw` 的 `SourceFile=` 行顺序编译——XC8 的 psect 分配依赖编译顺序，顺序不同产物不同（实测字母序 vs IDE 顺序差异 504 处）。
- **编译参数**：与 IDE 完全一致（从 IDE 生成的 `startup.as` 头部提取）：`--fill=0xFFFF --output=intel -D__DEBUG=1 -g --asmlist --warn=-9 --runtime=default, --opt=-local,-asmfile,+asm,-speed,+space,-debug --stack=compiled:auto:auto:auto --addrqual=request --mode=pro`。
- **配置字**：从 `.scw` 的 `config=` 行读取（IDE 权威值，含模板外隐藏位规则），写入 `.scx` 头 0xA0 起的 4 个 16 位槽位。
- **芯片参数**：从 IDE 的 `mcu/ini/<chip>.ini` 读取 `ROMSIZE`（程序区大小）、`HEXMCU`（未编程 word 值）。
  `.ini` 缺 `HEXMCU` 时按型号兜底（14-bit SC8F05x/SC8F070 → `0x3FFF`，其余 16-bit → `0xFFFF`），配置字计算末尾统一 `& hexmcu` 按位宽清高位。
- **`.scx` 头部**：芯片名 + `!`（烧录器靠 `!` 识别固件，8 字符芯片名如 SC8P052B 不会截断 `!`）。

## 项目结构

```
src/
├── extension.ts         # 扩展入口：命令注册 + 状态栏 + 自动规范化 / 编程器 / 烧录接线
├── build.ts             # 编译编排 + 错误诊断解析 + CfgCRC/CfgSum 输出
├── chip.ts              # .scw 解析、芯片列表、cfg 模板、配置字计算/规范化核心（normalizeConfigWordsCore）
├── compiler.ts          # 编译器目录查找（配置/常见路径/盘符/环境变量）
├── scx.ts               # .scx 生成 + 校验值计算
├── programmer.ts        # 编程器/仿真器识别（USB HID VID 0x1209 Writer + 0x0925 CMS-ICE6；纯 Node，可单测）
├── flash.ts             # 一键烧录：识别设备 → Writer 走烧录助手 / CMS-ICE6 走内置 Python 脚本
└── webview/
    ├── hardwareOptions.ts  # 芯片设置面板（单例）
    └── sourceManager.ts    # 源文件管理面板（按钮/拖拽排序）
flash/
├── ScmcuFlashHelper.cs   # Writer 通道烧录助手源码（net40/x86，引用 Writer.Core.dll，AssemblyResolve 加载依赖）
├── ScmcuFlashHelper.exe  # 助手编译产物（可 build_helper.py 重编）
├── build_helper.py       # 无 .NET SDK 机器一键重编助手（NuGet 拉 Roslyn Toolset）
├── ice6_flash.py         # CMS-ICE6 下载编排：握手→擦除→编程→校验→收尾，含进度与配置字可读化
├── ice6_flash_core.py    # ICE6 协议原语（HID 读写、控制帧表、块编解码）
└── py/                   # 内置 embeddable Python 3.11.9 运行时（下载脚本零环境依赖）
test/
├── configWords.regression.js  # 配置字回归（15 断言，驱动 out/chip.js 真实实现）
├── programmer.regression.js   # 编程器识别回归（22 断言，含 CMS-ICE6，纯函数层）
└── fixtures/ide/mcu/          # 从 SCMCU_IDE 拷入的芯片模板 .cfg/.ini（模拟 <idePath>，来源见 fixtures/README.md）
images/icon.png            # 扩展图标
```

## 开发

```bash
npm install          # 安装依赖
npm run compile      # TypeScript 编译
npm test             # 回归测试（配置字 15 + 编程器 22 断言；跑 out/chip.js 真实实现 + test/fixtures
                     #   模拟 IDE 芯片数据，不需要本机安装 SCMCU_IDE）
npm run package      # 打包 .vsix（scmcu-vscode-<version>.vsix，含 flash/py 内置运行时，约 7 MB）
```

F5 调试：打开本目录，按 F5 启动扩展开发宿主。

烧录助手重编（本机无需 .NET SDK，脚本自动从 NuGet 拉 Roslyn Toolset 4.8）：

```bash
npm run build:helper           # 或 python flash/build_helper.py
# 产物 flash/ScmcuFlashHelper.exe（x86 / .NET Framework 4.x）
```

> 打包脚本 `npm run package` 不再自动重编助手（原来会因为联网拉 Roslyn 失败而中断），
> 助手源码改动后单独跑一次 `npm run build:helper` 即可。

> 测试夹具 `test/fixtures` 从官方 SCMCU_IDE 的 `mcu/{config,ini}` 拷入（SC8F052 / SC8F072 模板），
> 来源与更新方式见 `test/fixtures/README.md`。

## 版本历史
- **v0.9.10** — **下载运行时内置，装完即用（不需要装 Python）**
  - vsix 内新增 `flash/py/`：官方 embeddable **Python 3.11.9**（Win x64），只保留 `python.exe` /
    `python311.dll` / 标准库 zip / `_ctypes.pyd` / `unicodedata.pyd` / vcruntime，删掉 ssl、sqlite、
    crypto、lzma 等无关组件（解压 11.2 MB，vsix 约 7 MB）。
  - `src/flash.ts` 新增 `resolvePython()`：`SCMCU_BUILD_PY` → 内置 `flash/py/python.exe` → PATH 里的 `python`，
    前两级都可用；启动失败时的报错会区分「内置运行时被拦」和「系统没装 Python」。
  - 实测：直接用内置运行时对真机完成一次烧写（14 帧、校验 64 页、差异 0、5.3s）。
  - 文案：`擦除完成` 不再带「高压就绪」；仿真器悬停提示删掉「下载走 IDE 私有 HID 帧序列…需本机有 python」一行。
- **v0.9.9** — **进度条改纯文字**
  - 下载日志里去掉了方块进度条，每步只留两行文字：`擦除中` / `擦除完成 高压就绪`、
    `下载中` / `下载完成 14/14 帧，ACK 14（0.1s）`、`校验中` / `校验完成 64/64 页，差异 0 字（3.7s）`。
  - 运行中的百分比仍走 `@@P` 标记显示在底栏状态条，输出面板不再出现任何中间态。
  - 第一步的标签列宽由 8 列放宽到 12 列（`擦除完成` 本身占 8 列），`固件 / 配置字 / 选项 / 结果` 同步对齐。
- **v0.9.8** — **日志收敛：每步一行 + 去掉多余字样**
  - 进度条不再逐档刷行（`0% / 14% / 29% …` 那一串没了），**每个步骤只留一行 100% 结果**
    （擦除 / 下载 / 校验各一行，含耗时）。运行中的百分比改由脚本用 `@@P` 标记发给扩展，
    显示在 VS Code **底栏状态条**（`$(sync~spin) 校验 24/64`），烧完自动消失。
  - 去掉下载日志里的「复刻 IDE …」类字样：`检测到 CMS-ICE6 (VID/PID)` 不再带尾巴，
    `CMS-ICE6 下载（复刻 IDE 私有 HID 帧序列）` 整行删除（Python 侧标题行已足够）。
  - `直读无应答、已用错位读绕过的页` 这类实现细节移入 `--debug`。
  - `结果` 行改为按需追加：只有补烧过 / 重连过 / 有差异时才出现对应字段。
- **v0.9.7** — **下载日志可读化：配置字翻成硬件选项 + 四步进度条**
  - **配置字不再只是一串十六进制**：编译输出在 `[SCMCU] 配置字: FFF7,FAEF,FFFF,FFFF` 之后新增
    `[SCMCU] 硬件选项: WDT=DISABLE  PROTECT=ENABLE  LVR_SEL=1.8V  FCPU_DIV=4T  ICSPPORT_SEL=NORMAL  EXT_RESET=DISABLE`。
    实现：`src/chip.ts` 新增 `describeConfig()`，用 IDE 的 `mcu/config/<芯片>.cfg`（芯片设置面板的同一份位定义）
    反查每个节命中的选项名，节顺序与 IDE 面板一致；ICE6 脚本侧同样支持（`--ide=` / `--cfg-file=`，
    芯片名从 `.scx` 头部自动读取），因此单独跑脚本也有可读选项。
  - **下载阶段改成四步进度条**：`固件 → 擦除 → 下载 → 校验`，后三步带 `[████░░░░] 68%` 进度条与当前
    帧/页计数；擦除对应 `0x17`（整片擦除 + 高压就绪）、下载对应 `0x01`×N 帧、校验对应 `0x06` 整片回读。
    结束给一行汇总（用时 / 补烧轮数 / 重连次数 / 差异字数）。
  - **原始协议帧默认不打印**：`PS 自检 -> 06 50 …`、`FC -> …`、`17 -> ACK 03`、`0D -> …` 等只有加
    `--debug` 才输出，排障时仍可看全套；正常下载只剩十来行。
  - 进度条按 1/8 分档（输出面板追加式、不能原地刷新），单步最多 9 行；控制台编码不支持 `█` 时自动退化为 `#`/`-`。
- **v0.9.6（正式发布；0.9.5 之后的本地迭代内容一并纳入）** — **CMS-ICE6 一键下载 + 新增「只下载」**
  - **新增命令 `SCMCU: 只下载（不编译）`**：底栏 `$(cloud-download)` 按钮，位于 `$(debug-start)` 编译与 `$(zap)` 编译下载之间。跳过编译，直接烧写 `build/` 中**上一次**的固件（换板重烧、只改硬件选项后重烧时省一次编译）。与「一键编译下载」共用同一套通道选择逻辑 `flashBuildArtifacts()`，所以两条通道（Writer / ICE6）都自动适用。
  - **底栏提示文案更新**：右侧 tooltip 不再写「本插件的一键下载仅支持 Writer 烧录器，暂不能通过它下载」，改为明确说明 ICE6 已支持「一键编译下载」与「只下载」，并提示**下载前关闭 SCMCU IDE**（它会抢占 HID 设备并切断目标板供电）；「未连接」提示同时列出两条通道及其区别。
  - **CMS-ICE6 下载通道**（真机验证，多次连续烧写零差异）：完整复刻官方 IDE V2.00.17 会话 —— `FC/18/1B` 握手 → `0x17`（芯片 ID / ROM 大小 / 高压参数 ERASE·PROGTIME·**VPPMODE=0x89**，高压由 ICE6 硬件自行产生——正是当年 ESP32 模拟方案跳过的部分）→ `0C 02 10` 进编程态 → `0x01`×N（**字地址**步进 0x18、48B/帧，每帧读 ACK 做流控）→ `03` 写配置字 → `0C 01 04` 退出 → `0x06` 整片回读校验 → 收尾 `0D/0B/04/0F/13 + 11×8 + 09×4`。
  - 关键根因（细节见上文坑①~⑨）：抓包 wire 已含 ReportID 需剥掉否则整帧错位；**编程帧之间绝不能插读**（会打断 ICE6 编程状态机）；ACK 必须及时收走（否则 HID 输入队列塞满、设备从第 60 帧起拒收）；**`0x17` 即整片擦除**（IDE 没有独立擦除命令，实测换小固件后旧固件 0 残留）；`0x06` 读命令只返回每条字的低 8 位；**缺收尾序列会让设备停在「擦得掉但写不进」，只能拔插 USB 恢复**——现收尾放在 `finally`，校验失败也照发。所有 Overlapped 等待改为有界（超时抛 `IOError` 并重连设备），彻底修掉「一键下载卡死」。
  - **ICE6 不再依赖 SCMCU Writer**：`flashScx()` 的 ICE 分支已移到 Writer 安装目录/烧录助手检查**之前**，只装 IDE + 本机有 `python`（仅标准库，零 pip 依赖）即可下载。
  - 配置字改从同目录 `.scx` 头部 `0xA0` 槽读取（换工程 / 换振荡器选项不会写错）；`flash.ts` 日志文案同步为完整会话描述。回归测试 15 / 22 断言全过。
- **v0.9.5** — **配置字校验和与官方 SCWriter 对齐**：修复「配置字槽数」推导错误——旧逻辑从芯片选项模板 `mcu/config/<芯片>.cfg` 取「最大 word 索引 + 1」，对 SC8P052B 这类模板只覆盖 word0 的器件会误判为 1 槽，导致 `CfgCRC`/`CfgSum` 与 SCWriter 不一致（SC8P052B 实测：插件 0x6021/0x20DC vs Writer 0x319A/0x2304）。现改为优先读 IDE `mcu/ini/<型号>.ini` 的 `CONFIGLENTH`，槽数 = `CONFIGLENTH + 1`（十六进制），`.cfg` 模板仅作兜底；并把槽数上限由 4 放开到 **16**（`.scx` 头部 `[0xA0,0xC0)` 恰好预留 16 个字），修正 SC8F27xx 等 16 槽器件的校验和。
- **v0.9.4** — **烧录助手下载信息乱码修复**：`ScmcuFlashHelper.exe`（.NET 程序）实际输出 UTF-8，v0.9.3 误将其按 GBK 解码，导致一键下载的 `[STEP]`/`[INFO]` 中文状态乱码（如「配置模板 / 机型 / 固件 / 烧写次数上限 / 已连接编程器」）；本次将烧录助手输出解码改为 **UTF-8 优先、GBK 兜底**（编译器警告仍走 GBK，保持正常可点击）。
- **v0.9.3** — ① **编译/烧录输出中文乱码修复**：build.ts 编译输出与 flash.ts 烧录助手输出统一按 GBK 解码（失败回退 utf-8），中文路径与中文状态不再乱码；② **编译器警告可点击跳转**：picc 对 Warning 缺列号的 `路径:行::` 已归一化为 `路径:行:列:`，输出面板支持 Ctrl+点击跳转，并正常进入「问题」面板；③ programmer.ts 设备枚举输出同样改 GBK 解码。


- **v0.9.2** — ① **底栏按钮精简**：芯片设置/源文件/构建/编译下载四个操作按钮改为纯图标，悬停提示精简为短文案（编译并下载到编程器 / 芯片设置 / 管理源文件 / 编译）；② **烧录助手补 wafer 修调数据下发**：按官方 `Run.StartDownload` 时序，在 0x60 校验前下发 `writer.fdat` 的 wafer 修调数据（Series 无数据自动跳过），为 FLASH 系列芯片脱机烧录兜底（SC8F072 全流程下载已验证）
- **v0.9.1** — ① **脱机烧录「找不到芯片」修复**：一键下载时写入正确的脱机选项 OfflineOption0/1（POWER=0，即官方默认 0xE8/0xE0），不再误用全局默认 0xFF（POWER=7），修掉「插件下载后按编程器烧录键找不到芯片」；② **脱机烧录「烧写次数不足」修复**：烧写次数上限默认改为无限（0=无限），`scmcu.flashCount` 设正整数可作量产限次；③ **源文件管理器死循环修复**：面板增删/排序改为整体覆写 `.scw` 的 SourceFile 段，在目录里删除源文件后也能正常从面板移除失效条目，不再报「源文件集合与 .scw 不一致」卡死
- **v0.9.0** — ① **配置字规范化**：每芯片 HEXMCU 兜底表 + 配置字位宽 mask + `SCMCU: 规范化配置字`，scw-less 加载时自动执行一次，修复从 16-bit 工程串来的高位错误（SC8F072 隐藏位有 fullWidth 守卫不误改）；② **编程器识别**：底栏右侧实时显示 SCMCU 编程器型号（PID 表来自 Writer.Core 反编译，聚焦 5s 轮询，升级模式标注 Boot）；③ **一键编译下载** `SCMCU: 一键编译下载` / 底栏 `$(zap) 编译下载`：spawn 烧录助手（引用 Writer.Core.dll 芯片库 + USB HID 协议）走 0x61/0x21/分段下发/0x60 校验/0x50 结束全时序，真机实烧闭环验证通过（SC8F052 含 EE 段）；④ 回归测试 `npm test`（15 + 17 断言）
- **v0.8.4** — 脱离 .scw 模式下面板全可用：状态栏「芯片设置」「源文件」两按钮在 scw / scw-less 两种模式都显示；芯片设置面板写 `scmcu.configWords`、源文件面板维护 `scmcu.sourceFiles`（可控制编译顺序）；新增 `SCMCU: 设置芯片型号/设置配置字` 命令面板入口
- **v0.8.3** — 命令面板新增 `SCMCU: 设置芯片型号/设置配置字 (脱离 .scw)`，用输入框直接写工作区设置；`engines.vscode` 从异常的 `^1.134.0` 修正为 `^1.85.0`，避免旧版 VS Code 判为不兼容
- **v0.8.1** — 新增「源文件管理」面板：可视化添加/移除/排序 `.scw` 的 `SourceFile=`
- **v0.7.0** — 插件图标；（之前各版为迭代开发，功能见上文）
- **v0.6.x** — 可配置源码/头文件目录、错误跳转、CfgCRC/CfgSum 与烧录器一致、SC8P 系列 8 字符芯片名修复
- **v0.3.x** — 芯片设置单例窗口、状态栏芯片切换与构建按钮
- **v0.1.x** — 基础编译 + 硬件选项配置 + 编译器自动检测
