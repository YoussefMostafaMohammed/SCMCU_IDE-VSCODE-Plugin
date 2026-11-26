// programmer.ts — SCMCU 编程器（烧录器）识别
//
// 识别机制参考对官方 SCMCU_Writer（Writer.Core.dll + scmcu writer.exe）的反编译结论：
//   - 官方软件按机型从加密配置 system.info 取 VID/PID，再用 Windows HID API 轮询比对；
//   - 真实设备表：所有编程器 USB VID = 0x1209，正常模式 / 升级(bootloader)模式各一个 PID：
//        WRITER8 LITE  -> 0x0201 / 0x0101
//        WRITER V8     -> 0x0032 / 0x0011
//        WRITER V8 PRO -> 0x0023 / 0x0021
//        ICE8 PRO      -> 0x1502 / 0x1102
//   CMS-ICE6 仿真器则使用另一个 VID：VID=0x0925 PID=0x0283（厂商串 "CMS ICE"，
//   在系统里伪装成"USB 输入设备"）。它是仿真器而非 Writer 烧录器，不能套用 Writer 的
//   --pid 烧录流程；本插件已为它单独实现了下载通道（flash/ice6_flash.py，复刻 IDE HID 会话），
//   识别出 kind:'ice' 后由 flash.ts 改走该脚本。本模块不依赖 vscode，纯 Node，便于回归测试。
//   枚举优先 pnputil（原生可执行文件），失败时回退 PowerShell Get-PnpDevice。仅 Windows 有意义。
import * as cp from 'child_process';

export interface ProgrammerDevice {
    pidHex: string;                 // 4 位大写十六进制 PID，如 '0201'
    name: string;                   // 型号名，如 'WRITER8 LITE'
    mode: 'normal' | 'bootloader' | 'unknown';
    kind: 'writer' | 'ice';         // Writer 烧录器 / ICE 仿真器（下载通道不同）
    vidHex: string;                 // 4 位大写十六进制 VID，如 '1209' / '0925'
}

interface ModelInfo { name: string; mode: 'normal' | 'bootloader'; kind: 'writer' | 'ice'; vidHex: string; }

// 正常 / 升级模式 设备表（来自官方 Writer 反编译的设备库 + 实测 CMS-ICE6）
// key = VID:PID，避免不同 VID 下 PID 撞号；ICE6 为仿真器(kind:'ice')，无 bootloader 模式。
const DEVICE_TABLE: Record<string, ModelInfo> = {
    '1209:0201': { name: 'WRITER8 LITE', mode: 'normal', kind: 'writer', vidHex: '1209' },
    '1209:0101': { name: 'WRITER8 LITE', mode: 'bootloader', kind: 'writer', vidHex: '1209' },
    '1209:0032': { name: 'WRITER V8', mode: 'normal', kind: 'writer', vidHex: '1209' },
    '1209:0011': { name: 'WRITER V8', mode: 'bootloader', kind: 'writer', vidHex: '1209' },
    '1209:0023': { name: 'WRITER V8 PRO', mode: 'normal', kind: 'writer', vidHex: '1209' },
    '1209:0021': { name: 'WRITER V8 PRO', mode: 'bootloader', kind: 'writer', vidHex: '1209' },
    '1209:1502': { name: 'ICE8 PRO', mode: 'normal', kind: 'writer', vidHex: '1209' },
    '1209:1102': { name: 'ICE8 PRO', mode: 'bootloader', kind: 'writer', vidHex: '1209' },
    '0925:0283': { name: 'CMS-ICE6', mode: 'normal', kind: 'ice', vidHex: '0925' },
};

// 仅按 PID 归类（兼容旧调用与回归测试）：只在 PID 唯一时安全；ICE6 的 0283 也在列。
const PID_TABLE: Record<string, ModelInfo> = {
    '0201': DEVICE_TABLE['1209:0201'],
    '0101': DEVICE_TABLE['1209:0101'],
    '0032': DEVICE_TABLE['1209:0032'],
    '0011': DEVICE_TABLE['1209:0011'],
    '0023': DEVICE_TABLE['1209:0023'],
    '0021': DEVICE_TABLE['1209:0021'],
    '1502': DEVICE_TABLE['1209:1502'],
    '1102': DEVICE_TABLE['1209:1102'],
    '0283': DEVICE_TABLE['0925:0283'],
};

// 纯函数：按 PID 归类（未知 PID 也返回，避免将来新硬件被静默忽略）
export function classifyPid(pidHex: string): ProgrammerDevice {
    const p = (pidHex || '').trim().replace(/^0[xX]/, '').toUpperCase();
    const hit = PID_TABLE[p];
    return hit
        ? { pidHex: p, name: hit.name, mode: hit.mode, kind: hit.kind, vidHex: hit.vidHex }
        : { pidHex: p, name: '未知编程器', mode: 'unknown', kind: 'writer', vidHex: '' };
}

// 按 VID+PID 精确归类（新增，推荐路径）
export function classifyDevice(vidHex: string, pidHex: string): ProgrammerDevice {
    const v = (vidHex || '').trim().replace(/^0[xX]/, '').toUpperCase();
    const p = (pidHex || '').trim().replace(/^0[xX]/, '').toUpperCase();
    const hit = DEVICE_TABLE[v + ':' + p] || PID_TABLE[p];
    return hit
        ? { pidHex: p, name: hit.name, mode: hit.mode, kind: hit.kind, vidHex: hit.vidHex }
        : { pidHex: p, name: '未知编程器', mode: 'unknown', kind: 'writer', vidHex: v };
}

// 纯函数：从枚举输出文本提取去重 PID（pnputil / PowerShell 输出都适用，pnputil 常同时
// 出现 USB 父设备与 HID 子接口两条同 PID 记录，故按出现顺序去重）
export interface DeviceId { vidHex: string; pidHex: string; }

// 支持的 VID 白名单：1209 = SCMCU Writer / ICE8 PRO，0925 = CMS-ICE6 仿真器
const SUPPORTED_VIDS = ['1209', '0925'];

// 从枚举文本提取 VID+PID 对（ pnputil / PowerShell 输出通用）
export function parseDevicePairs(text: string): DeviceId[] {
    const out: DeviceId[] = [];
    const push = (v: string, p: string): void => {
        const vid = v.toUpperCase(), pid = p.toUpperCase();
        if (SUPPORTED_VIDS.indexOf(vid) < 0) return;
        if (out.some((d) => d.vidHex === vid && d.pidHex === pid)) return;
        out.push({ vidHex: vid, pidHex: pid });
    };
    // 带前缀的枚举输出（pnputil：USB/HID\\VID_xxxx&PID_yyyy\\...）
    const re = /VID_([0-9A-Fa-f]{4})&PID_([0-9A-Fa-f]{4})/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) push(m[1], m[2]);
    // 整行只有裸 PID 的输出（回退枚举器格式：每行一个 4 位十六进制）→ 归入默认 VID 1209
    const re2 = /(?:^|[\r\n])\s*([0-9A-Fa-f]{4})\s*(?:[\r\n]|$)/g;
    while ((m = re2.exec(text)) !== null) push('1209', m[1]);
    return out;
}

// 兼容旧接口：只返回 PID 列表（去重，保持出现顺序）
export function parseDeviceIds(text: string): string[] {
    return parseDevicePairs(text).map((d) => d.pidHex);
}

// 检测当前连接的 SCMCU 编程器（仅 Windows；非 Windows 恒返回空数组）
export async function detectProgrammers(timeoutMs = 4000): Promise<ProgrammerDevice[]> {
    if (process.platform !== 'win32') return [];
    let raw = '';
    try {
        raw = await execText('pnputil', ['/enum-devices', '/connected', '/deviceids'], timeoutMs);
    } catch (e) {
        // 老系统无 pnputil 或被执行策略禁用 → 回退 PowerShell（同时支持两个 VID）
        const ps = "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | ForEach-Object { $m=[regex]::Match($_.InstanceId,'VID_(1209|0925)&PID_([0-9A-Fa-f]{4})'); if($m.Success){ 'VID_' + $m.Groups[1].Value + '&PID_' + $m.Groups[2].Value.ToUpper() } } | Sort-Object -Unique";
        raw = await execText('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', ps], timeoutMs);
    }
    return parseDevicePairs(raw).map((d) => classifyDevice(d.vidHex, d.pidHex));
}

// 中文 Windows 下 pnputil / PowerShell 以 GBK 输出设备名，按 GBK 解码避免乱码。
function makeGbkDecoder(): any {
    try { return new TextDecoder('gbk'); } catch (e) {}
    try { return new TextDecoder('gb2312'); } catch (e) {}
    return new TextDecoder('utf-8');
}

function execText(cmd: string, args: string[], timeoutMs: number): Promise<string> {
    return new Promise<string>((resolve, reject) => {
        cp.execFile(cmd, args, {
            windowsHide: true,
            timeout: timeoutMs,
            maxBuffer: 4 * 1024 * 1024,
            encoding: 'buffer',
        }, (err, stdout) => {
            if (err) { reject(err); return; }
            const buf = (stdout as unknown) as Buffer;
            let s = '';
            try { s = makeGbkDecoder().decode(buf); } catch (e) { s = buf.toString('utf8'); }
            resolve(s || '');
        });
    });
}
