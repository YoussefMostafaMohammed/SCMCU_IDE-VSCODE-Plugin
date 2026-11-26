# -*- coding: utf-8 -*-
"""CMS-ICE6 下载入口（替代 SCMCU IDE 的下载按钮）。

本文件按官方 IDE V2.00.17 的**完整会话**逐段复刻（Frida 抓包，三段会话完全一致）：

    PS 自检 0x50 0x53
    目标链路 0x1A（不就绪则 A6 78 -> 52 重连目标）
    --- 会话开始 ---
    FC -> 18 -> 1B                     握手
    17                                 芯片参数 + 高压参数（必须 ACK "03"）
    0C 02 10                           进入编程态
    01 ...                             逐块编程，24 字/帧（等每帧 ACK 做流控）
    03 (配置字 = FF..)                 清配置字区
    0C 01 04                           退出编程态
    06 ...                             整片回读校验
    03 (配置字 = 实际值)               写配置字
    0C 01 04
    0D -> 0B -> 04 -> 0F -> 13         收尾
    11 x8 / 09 x4                      收尾
    --- 会话结束 ---

⚠️ 收尾那一段（0D/0B/04/0F/13 + 11x8 + 09x4）不是可选项：
   缺了它 ICE6 会停在"擦得掉但写不进"的状态，下次必须给调试器断电才能再烧。
   因此本脚本把收尾放在 finally 里，**任何情况下都会发**。

输出约定（给 VS Code 输出面板看）：
   默认只打四步进度：固件 / 擦除 / 下载 / 校验，原始协议帧仅在 --debug 时打印。
   配置字同时解码成 IDE 硬件选项（WDT=DISABLE、LVR_SEL=1.8V…），模板取自
   <IDE>/mcu/config/<chip>.cfg，芯片名从同目录 .scx 头部读。

已知硬件怪癖：以 0x560 为起始地址的 0x06 读命令永远无应答（与内容无关），
read_page() 会用 ±8 字的错位读拼接绕过。

协议实现与 IDE 抓包帧在 ice6_flash_core.py，本文件负责编排与时序。

命令行：
    python ice6_flash.py <firmware.hex> [--config FFF7,FAEF,FFFF,FFFF] [--no-config]
                         [--max-retry N] [--quiet] [--no-wake] [--probe-only]
                         [--debug] [--ide <IDE目录>] [--device SC8F072] [--cfg-file <x.cfg>]

退出码：0 成功 / 2 烧写校验未通过 / 3 目标链路未就绪
"""
import sys
import os
import time
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 输出统一走 UTF-8：扩展侧按 UTF-8 解码，否则中文在 VS Code 输出面板里是乱码
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import ice6_flash_core as core

ROM_WORDS = 0x800       # 2K words
BLOCK_W = 0x18          # 24 字 / 编程帧
BLOCK_B = BLOCK_W * 2   # 48 字节
READ_W = 32             # 0x06 单次读 32 字（64 字节）

DEFAULT_CFG = [0xFFF7, 0xFAEF, 0xFFFF, 0xFFFF]

# 抓包模板里的固定帧下标（见 ice6_flash_core.CONTROL_FRAMES）
F_HANDSHAKE = (0, 1, 2)         # FC / 18 / 1B
F_CFG17 = 3                     # 0x17 芯片+高压参数
F_ENTER = 4                     # 0C 02 10  进入编程态
F_EXIT = 92                     # 0C 01 04  退出编程态
F_CFG_WRITE = 157               # 03 配置字（模板里是 FFF7/FAEF）
F_TAIL = tuple(range(159, 176))  # 0D 0B 04 0F 13 11x8 09x4


def hx(b, n=14):
    return 'None' if b is None else ' '.join('%02X' % x for x in b[:n])


def ascii_of(b, n=44):
    return ''.join(chr(x) if 32 <= x < 127 else '.' for x in b[:n])


# ---------------- 输出排版：四步文字提示 ----------------
# 输出面板按行追加、不能靠 \r 原地刷新，所以每一步只打两行纯文字：
#   `擦除中` → `擦除完成 …`
# 运行中的百分比不往面板写，改由 @@P 标记交给扩展显示在状态栏那一行里。

# 扩展会设 SCMCU_PROGRESS=1，此时逐步进度以 @@P 标记发出去（供状态栏一行显示）；
# 命令行直接跑没人消费标记，就不发，免得 @@P 干扰阅读。
PROGRESS_TOKENS = os.environ.get('SCMCU_PROGRESS') == '1'


def _dw(s):
    """显示宽度：CJK 全角算 2 列，保证标签纵向对齐。"""
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in s)


def pad(s, width):
    return s + ' ' * max(0, width - _dw(s))


class Bar:
    """一个步骤只出两行纯文字：`xxx中` 与 `xxx完成 …`（失败时 `xxx失败 …`）。

    step() 不打印，只把进度以 `@@P\t标签\t已完成\t总数` 的标记发给扩展
    （扩展解析后写进 VS Code 状态栏一行，输出面板不再刷屏）；
    命令行直接跑时没有扩展消费标记，故标记默认关闭，
    由扩展设置环境变量 SCMCU_PROGRESS=1 打开。
    """

    WIDTH = 12   # 「擦除完成」= 8 列，留 4 列间距

    def __init__(self, label, total):
        self.label = label
        self.total = max(1, int(total))
        self.token = PROGRESS_TOKENS
        self.shown = -1
        self.t0 = time.time()

    def begin(self, note=''):
        print(('%s%s' % (pad(self.label + '中', self.WIDTH), note)).rstrip(), flush=True)
        return self

    def step(self, done, note=''):
        if not self.token:
            return
        bucket = min(8, int(done * 8 / self.total))
        if bucket <= self.shown:
            return
        self.shown = bucket
        print('@@P\t%s\t%d\t%d' % (self.label, done, self.total), flush=True)

    def finish(self, note=''):
        print(('%s%s' % (pad(self.label + '完成', self.WIDTH), note)).rstrip(), flush=True)
        return time.time() - self.t0

    def fail(self, note=''):
        print(('%s%s' % (pad(self.label + '失败', self.WIDTH), note)).rstrip(), flush=True)
        return time.time() - self.t0


def hdr(title):
    print('', flush=True)
    print('──── %s ────' % title, flush=True)


def kv(label, text):
    print('%s%s' % (pad(label, Bar.WIDTH), text), flush=True)


# ---------------- 硬件选项解码 ----------------

def find_ide_dir(explicit=None):
    """定位 SCMCU IDE 安装目录（只为读 mcu/config/<chip>.cfg）。"""
    cands = []
    if explicit:
        cands.append(explicit)
    env = os.environ.get('SCMCU_IDE_HOME')
    if env:
        cands.append(env)
    for drv in 'CDEFGHIJ':
        for sub in ('', 'Work', 'Program Files', 'Program Files (x86)', 'gat'):
            root = drv + ':\\' + (sub + '\\' if sub else '')
            if not os.path.isdir(root):
                continue
            try:
                entries = os.listdir(root)
            except OSError:
                continue
            for e in entries:
                if e.upper().startswith('SCMCU_IDE'):
                    cands.append(os.path.join(root, e))
    for d in cands:
        if os.path.isdir(os.path.join(d, 'mcu', 'config')):
            return d
    return None


def load_cfg_template(cfg_path):
    """解析 IDE 芯片配置模板 → {节: {选项: [(word, bit, val), ...]}}，保持文件顺序。

    .cfg 格式：
        [WDT]
        DISABLE=1,11,1:1,10,0:1,9,1:1,8,0
    即 选项名 = word,bit,值 的列表（word 从 0 计），全部位匹配才算该选项。
    """
    tpl = {}
    cur = None
    with open(cfg_path, 'r', encoding='utf-8', errors='replace') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                cur = line[1:-1]
                tpl.setdefault(cur, {})
                continue
            if cur is None or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            if k.upper() == 'DISPMODE':
                continue
            bits = []
            for it in v.strip().split(':'):
                p = it.split(',')
                if len(p) == 3:
                    try:
                        bits.append((int(p[0]), int(p[1]), int(p[2])))
                    except ValueError:
                        pass
            if bits:
                tpl[cur][k] = bits
    return tpl


def decode_options(words, cfg_path):
    """反查每一节当前命中的选项名，返回 [(节, 选项或 None)]（保持模板顺序）。"""
    tpl = load_cfg_template(cfg_path)
    out = []
    for sec, opts in tpl.items():
        hit = None
        for name, bits in opts.items():
            ok = True
            for (w, b, v) in bits:
                if w >= len(words) or ((words[w] >> b) & 1) != v:
                    ok = False
                    break
            if ok:
                hit = name
                break
        out.append((sec, hit))
    return out


def format_options(pairs):
    return '  '.join('%s=%s' % (sec, opt if opt else '?') for sec, opt in pairs)


# ---------------- 会话：开始 / 编程 / 收尾 ----------------

def fixed_frame(idx):
    """从抓包模板取一帧（已剥掉 ReportID）。"""
    raw = core.CONTROL_FRAMES[idx]
    if raw is None:
        raise RuntimeError('模板第 %d 帧不是控制帧' % idx)
    return core.wire_to_payload(bytes.fromhex(raw))


def make_cfg_payload(words):
    """op=0x03 写配置字帧：[len][03][00 00][4 字小端][sum]。"""
    body = [0x03, 0x00, 0x00]
    for w in words:
        body += [w & 0xFF, (w >> 8) & 0xFF]
    p = bytearray(64)
    p[0] = len(body) + 2
    p[1:1 + len(body)] = bytes(body)
    p[p[0] - 1] = core.sum8(p[:p[0] - 1])
    return bytes(p)


# ---------------- 链路 ----------------

def probe_status(ice, timeout=500):
    """0x1A：健康时回 09 打头的状态帧（含 VDD/VPP 采样）。"""
    ice.drain()
    ice.write(core.make_cmd(0x1A))
    for _ in range(3):
        r = ice._read_raw(timeout)
        if r is None:
            return None
        if r and r[0] == 0x09:
            return r
    return None


def wake_target(ice, verbose=True):
    """复刻 IDE「连接调试器」那一步，把 ICE6 从只回 14 的状态拉回来。"""
    ice.drain()
    ice.write(core.make_cmd(0xA6, 0x78))
    time.sleep(0.06)
    r1 = ice._read_raw(400)
    if verbose:
        print('[wake] A6 78 -> %s' % hx(r1, 12), flush=True)

    ice.drain()
    ice.write(core.make_cmd(0x52))
    time.sleep(0.10)
    got = []
    for _ in range(8):
        r = ice._read_raw(350)
        if r is None:
            break
        got.append(r)
    if verbose:
        if got:
            print('[wake] 52    -> %s | %s' % (hx(got[0], 10), ascii_of(got[0], 46)), flush=True)
        else:
            print('[wake] 52    -> 无应答', flush=True)

    st = probe_status(ice)
    if verbose:
        print('[wake] 0x1A  -> %s' % hx(st, 14), flush=True)
    return st is not None


def prepare(ice, do_wake=True, verbose=True, trace=False):
    """PS 自检 + 目标链路就绪检查。trace=True 才打印握手原始帧。"""
    ice.drain()
    ice.write(core.make_cmd(0x50, 0x53))
    r = ice._read_raw(600)
    if trace:
        print('  PS 自检  -> %s' % hx(r, 10), flush=True)
    if not r or r[1:2] != b'\x50':
        print('!! 未收到 ICE6 的型号应答，请确认设备已插好（VID 0925 / PID 0283）', flush=True)
        return False

    if probe_status(ice) is not None:
        if trace:
            print('  目标链路 -> 已就绪（无需唤醒）', flush=True)
        return True
    if not do_wake:
        print('!! 目标链路未就绪，且已禁用唤醒', flush=True)
        return False

    if verbose:
        print('链路未就绪，执行唤醒序列 …', flush=True)
    if wake_target(ice, trace or verbose):
        return True
    print('!! 唤醒失败：ICE6 只应答型号查询，其余命令均返回 14。\n'
          '   请打开一次 SCMCU IDE 让它连接调试器，或拔插 ICE6 的 USB 后再试。', flush=True)
    return False


def read_ack(ice, timeout=350):
    """读一个 ASCII 状态码。返回 '03'(成功) / '14'(错误) / None(无应答)。"""
    r = ice._read_raw(timeout)
    if r is None:
        return None
    if len(r) >= 3 and r[0] == 0x03 and r[1] == 0x30 and r[2] in (0x33, 0x34):
        return chr(r[1]) + chr(r[2])
    return None


def send_frame(ice, payload, timeout=250):
    ice.drain()
    ice.write(payload)
    return ice._read_raw(timeout)


def session_open(ice, verbose=True, trace=False):
    """FC -> 18 -> 1B -> 17（整片擦除 + 高压）-> 0C 02 10。0x17 必须被接受。"""
    for idx in F_HANDSHAKE:
        r = send_frame(ice, fixed_frame(idx), 200)
        if trace:
            print('  %-4s -> %s' % ({0: 'FC', 1: '18', 2: '1B'}[idx], hx(r, 8)), flush=True)
        time.sleep(0.01)
    time.sleep(0.12)

    bar = Bar('擦除', 1).begin() if verbose else None

    ice.drain()
    ice.write(core.full_17_payload())
    ack = None
    for _ in range(3):
        ack = read_ack(ice, 700)
        if ack:
            break
    if ack != '03':
        msg = '擦除/高压配置被拒绝（ACK=%s），请确认目标板供电正常' % (ack or '无应答')
        if bar:
            bar.fail(msg)
        else:
            print('  !! ' + msg, flush=True)
        return False
    if bar:
        bar.finish()
    elif trace:
        print('  17   -> ACK %s (芯片参数 + 高压参数已接受)' % ack, flush=True)

    r = send_frame(ice, fixed_frame(F_ENTER), 300)
    if trace:
        print('  0C   -> %s (进入编程态)' % hx(r, 8), flush=True)
    time.sleep(0.02)
    return True


def program_blocks(ice, blocks, verbose=True, head='下载', trace=False):
    """逐块编程。每帧等自己的 ACK：既做流控，也让 HID 输入队列不积压。"""
    acked = 0
    noack = 0
    bar = Bar(head, len(blocks)) if (verbose and blocks) else None
    if bar:
        bar.begin()
    for n, (wa, seg) in enumerate(blocks):
        ice.write(core.make_prog_payload(wa, list(seg)))
        a = read_ack(ice, 350)
        if a is None:
            noack += 1
            if trace:
                print('    帧 %d @%04X 无应答' % (n + 1, wa), flush=True)
        else:
            acked += 1
        if bar:
            bar.step(n + 1)
    if bar:
        bar.finish('%d/%d 帧，ACK %d（%.1fs）' % (
            len(blocks), len(blocks), acked, time.time() - bar.t0))
    ice.drain()
    return acked, noack
    ice.drain()
    return acked, noack


def exit_program(ice, verbose=True, trace=False):
    r = send_frame(ice, fixed_frame(F_EXIT), 300)
    if trace:
        print('  0C   -> %s (退出编程态)' % hx(r, 8), flush=True)
    return r


def write_config(ice, words, verbose=True, trace=False):
    if words is None:
        return None
    r = send_frame(ice, make_cfg_payload(words), 400)
    if trace:
        print('  03   -> %s (配置字 %s)' % (hx(r, 8), ' '.join('%04X' % w for w in words)), flush=True)
    return r


def session_close(ice, verbose=True, trace=False):
    """收尾序列。**必须发**，否则下一次会卡在「擦得掉但写不进」。

    IDE 的间隔：0D 之后约 250ms 再发 0B，0B/04/0F/13 连发，11 每帧约 15ms，09 连发。
    """
    try:
        r = send_frame(ice, fixed_frame(159), 400)      # 0D
        if trace:
            print('  0D   -> %s' % hx(r, 8), flush=True)
        time.sleep(0.25)
        r = send_frame(ice, fixed_frame(160), 300)      # 0B
        if trace:
            print('  0B   -> %s' % hx(r, 8), flush=True)
        for idx in (161, 162, 163):                     # 04 / 0F / 13
            send_frame(ice, fixed_frame(idx), 200)
            time.sleep(0.004)
        for idx in range(164, 172):                     # 11 x8
            send_frame(ice, fixed_frame(idx), 200)
            time.sleep(0.015)
        for idx in range(172, 176):                     # 09 x4
            send_frame(ice, fixed_frame(idx), 200)
            time.sleep(0.004)
        ice.drain()
        if verbose and trace:
            print('  收尾序列已发（设备已可再次烧写）', flush=True)
        return True
    except Exception as e:
        if verbose:
            print('  !! 收尾序列异常: %s' % e, flush=True)
        return False


# ---------------- 设备（可重连） ----------------

class Device:
    """持有 HID 句柄。写超时/链路失效时重开句柄 + 重新握手 + 重开会话。"""

    def __init__(self, verbose=True, trace=False):
        self.ice = None
        self.verbose = verbose
        self.trace = trace
        self.reconnects = 0

    def open(self):
        if self.ice is not None:
            try:
                self.ice.close()
            except Exception:
                pass
            self.ice = None
            time.sleep(0.25)
        self.ice = core.Ice6(timeout_ms=700)
        return self.ice

    def recover(self):
        self.reconnects += 1
        if self.verbose:
            print('   [恢复] I/O 超时，重开设备并重新建立会话（第 %d 次）' % self.reconnects, flush=True)
        for _ in range(4):
            try:
                self.open()
                if (prepare(self.ice, do_wake=True, verbose=False, trace=self.trace)
                        and session_open(self.ice, verbose=False, trace=self.trace)):
                    if self.verbose:
                        print('   [恢复] 已恢复，继续', flush=True)
                    return True
            except Exception as e:
                if self.verbose:
                    print('   [恢复] 本次尝试失败: %s' % e, flush=True)
            time.sleep(0.4)
        return False


# ---------------- 读 ----------------

def read_words(ice, wa, tries=4, timeout=700):
    """读 32 字（64 字节）。偶数位是字低字节、奇数位恒 0。I/O 超时向上抛 IOError。"""
    for _ in range(tries):
        ice.drain()
        ice.write(core.make_cmd(0x06, wa & 0xFF, (wa >> 8) & 0xFF, 0x40))
        for _ in range(3):
            r = ice._read_raw(timeout)
            if r is None:
                break
            if len(r) >= 64 and not (r[0] == 0x03 and len(r) >= 2 and r[1] in (0x30, 0x31)):
                return bytes(r[:64])
    return None


# 实测：以 0x560 为起始地址的 0x06 读命令**永远无应答**（ICE6 固件怪癖，与内容无关）。
# 这类页改用 ±8 字的错位读拼接，绕开该起始地址。
BAD_PAGE = set()


def read_page(ice, base, timeout=700, tries=4):
    """读一个 32 字对齐的页，返回 64 字节（偶数位为字低字节）。"""
    if base not in BAD_PAGE:
        got = read_words(ice, base, tries=tries, timeout=timeout)
        if got is not None:
            return got

    pieces = {}
    for off in (-8, 8):
        seg = read_words(ice, base + off, tries=tries, timeout=timeout)
        if seg is None:
            continue
        for k in range(0, 64, 2):
            w = base + off + k // 2
            if base <= w < base + 32:
                pieces[w - base] = seg[k]
    if len(pieces) >= 32:
        buf = bytearray(64)
        for i in range(32):
            buf[i * 2] = pieces[i]
        BAD_PAGE.add(base)
        return bytes(buf)
    return None


def verify_chip(ice, img, progress=None):
    """整片回读校验。返回 (mismatches{word:(期望,实际)}, unread_pages[])。

    progress: 可选回调 progress(已完成页数, 总页数)，用于画校验进度条。
    """
    mism = {}
    unread = []
    total = (ROM_WORDS + READ_W - 1) // READ_W
    for i, base in enumerate(range(0, ROM_WORDS, READ_W)):
        got = read_page(ice, base)
        if progress:
            progress(i + 1, total)
        if got is None:
            unread.append(base)
            continue
        for k in range(0, 64, 2):
            w = base + k // 2
            if w >= ROM_WORDS:
                break
            exp = img[w * 2]
            if exp != 0xFF and got[k] != exp:
                mism[w] = (exp, got[k])
    return mism, unread


# ---------------- 烧写 ----------------

def flash(hex_path, cfg_words=None, max_retry=6, verbose=True,
          opts_text='', cfg_src='', trace=False):
    t_start = time.time()
    mem = core.parse_hex(hex_path)
    img = core.build_image(mem)

    blocks = []
    for wa in range(0, ROM_WORDS, BLOCK_W):
        seg = img[wa * 2: wa * 2 + BLOCK_B]
        if any(b != 0xFF for b in seg):
            blocks.append((wa, bytes(seg)))

    if verbose:
        hdr('CMS-ICE6 下载')
        kv('固件', '%s  (%d 字节, 需编程 %d 块)' % (hex_path, len(mem), len(blocks)))
        if cfg_words:
            kv('配置字', '%s   (来源: %s)' % (' '.join('%04X' % w for w in cfg_words), cfg_src))
        else:
            kv('配置字', '不写入 (%s)' % cfg_src)
        if opts_text:
            kv('选项', opts_text)

    dev = Device(verbose, trace)
    ice = dev.open()
    try:
        if not session_open(ice, verbose, trace):
            if not dev.recover():
                print('!! 会话建立失败，中止', flush=True)
                return False
            ice = dev.ice

        # ---- 编程 → 清配置字区 → 退出编程态（顺序与 IDE 一致）----
        acked, noack = program_blocks(ice, blocks, verbose, head='下载', trace=trace)
        write_config(ice, [0xFFFF] * 4 if cfg_words else None, verbose, trace)
        exit_program(ice, verbose, trace)

        # ---- 回读校验 ----
        time.sleep(0.30)
        pages = (ROM_WORDS + READ_W - 1) // READ_W
        vbar = Bar('校验', pages) if verbose else None
        if vbar:
            vbar.begin()
        mism, unread = verify_chip(ice, img, (lambda d, t: vbar.step(d)) if vbar else None)
        if vbar:
            vbar.finish('%d/%d 页，差异 %d 字（%.1fs）' % (
                pages, pages, len(mism), time.time() - vbar.t0))

        # ---- 识别「擦得掉但写不进」：几乎全部字读回 FF、且编程帧 ACK 全正常 ----
        # 这种状态下擦除有效、0x17 回 03、编程帧回 03，但一个位都没落盘；补烧再多次也没用。
        # 成因是 CMS-ICE6 被官方 IDE 连接过之后遗留的状态，软件命令无法解除，只能给调试器断电。
        # 与「个别块漏烧」区分：漏烧是成块的 FF（比例低），这里是几乎全片。
        expect_words = sum(1 for w in range(ROM_WORDS) if img[w * 2] != 0xFF)
        stuck = bool(mism and expect_words and len(mism) >= expect_words * 0.9
                     and all(act == 0xFF for _, act in mism.values()))

        rounds = 0
        if stuck:
            print('!! 检测到「擦得掉但写不进」：擦除有效、编程帧全部 ACK 正常，但数据一位都没落盘。', flush=True)
            print('   这是 CMS-ICE6 被官方 IDE 连接过之后遗留的状态，软件侧无法解除，补烧也不会有效。', flush=True)
            print('   请拔插 ICE6 的 USB（给调试器断电）后重试 —— 不需要重启电脑或 VS Code。', flush=True)
        else:
            while (mism or unread) and rounds < max_retry:
                rounds += 1
                bad = sorted(set(((w // BLOCK_W) * BLOCK_W) for w in mism))
                if verbose:
                    print('补烧 第 %d 轮: %d 块%s' % (
                        rounds, len(bad),
                        ('  首个差异: 字%04X 期望%02X 实际%02X' % (
                            min(mism), mism[min(mism)][0], mism[min(mism)][1])) if mism else ''), flush=True)
                if not bad:
                    break
                send_frame(ice, fixed_frame(F_ENTER), 300)      # 重新进入编程态
                time.sleep(0.02)
                program_blocks(ice, [(wa, img[wa * 2: wa * 2 + BLOCK_B]) for wa in bad],
                               verbose, head='补烧', trace=trace)
                exit_program(ice, verbose=False, trace=trace)
                time.sleep(0.30)
                rbar = Bar('复验', pages) if verbose else None
                if rbar:
                    rbar.begin()
                mism, unread = verify_chip(ice, img, (lambda d, t: rbar.step(d)) if rbar else None)
                if rbar:
                    rbar.finish('%d/%d 页，差异 %d 字（%.1fs）' % (
                        pages, pages, len(mism), time.time() - rbar.t0))

        ok = not mism and not unread

        # ---- 写实际配置字 + 退出编程态 ----
        # 无论校验是否通过都要把工程配置字写回：中途已把配置区清成 FF，
        # 若这里不写回，芯片会留在"配置字未编程"状态。
        try:
            write_config(ice, cfg_words, verbose, trace)
        except Exception as e:
            if verbose:
                print('  !! 写配置字失败: %s' % e, flush=True)
        try:
            exit_program(ice, verbose=False, trace=trace)
        except Exception:
            pass

        if verbose:
            msg = '%s · 用时 %.1fs' % ('✅ 校验通过' if ok else '❌ 校验未通过', time.time() - t_start)
            if rounds:
                msg += ' · 补烧 %d 轮' % rounds
            if dev.reconnects:
                msg += ' · 重连 %d 次' % dev.reconnects
            if mism:
                msg += ' · 差异 %d 字' % len(mism)
            if unread:
                msg += ' · 读不到 %d 页' % len(unread)
            kv('结果', msg)
            if trace and BAD_PAGE:
                print('        （直读无应答、已用错位读绕过的页: %s）' % (
                    ' '.join('%04X' % p for p in sorted(BAD_PAGE))), flush=True)
        return ok
    finally:
        # 收尾序列无条件发送：这是"设备还能再次烧写"的关键
        try:
            if dev.ice is not None:
                session_close(dev.ice, verbose, trace)
        except Exception as e:
            if verbose:
                print('!! 收尾失败: %s' % e, flush=True)
        try:
            if dev.ice is not None:
                dev.ice.close()
        except Exception:
            pass


def parse_cfg(text):
    words = []
    for part in text.replace('0x', '').replace(' ', '').split(','):
        if not part:
            continue
        words.append(int(part, 16) & 0xFFFF)
    if len(words) != 4:
        raise ValueError('配置字需 4 个 16 位数，例如 FFF7,FAEF,FFFF,FFFF')
    return words


def read_scx_info(hex_path):
    """从同目录同名 .scx 读取 (配置字, 芯片名, scx 路径)。

    .scx 是构建产物：头部是「芯片名 + '!'」，0xA0 起 4 个配置字槽。
    芯片名用于定位 IDE 的硬件选项模板 mcu/config/<chip>.cfg；
    配置字由工程（.scw / scmcu.configWords）决定，比脚本里的默认值可靠 ——
    换工程、换振荡器/看门狗选项都不会写错。
    """
    scx = os.path.splitext(hex_path)[0] + '.scx'
    if not os.path.exists(scx):
        return None, None, None
    try:
        with open(scx, 'rb') as f:
            head = f.read(0xC0)
        if len(head) < 0xA8:
            return None, None, scx
        raw = head[:0x9F].split(b'\x21')[0]
        device = raw.decode('ascii', 'ignore').strip().strip('\x00')
        device = ''.join(c for c in device if 32 <= ord(c) < 127)
        slots = head[0xA0:0xA8]
        words = [slots[i] | (slots[i + 1] << 8) for i in range(0, 8, 2)]
        return words, device, scx
    except Exception:
        return None, None, scx


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    hex_path = argv[0]

    def opt(name):
        """取 --name=value 或 --name value。"""
        for i, a in enumerate(argv):
            if a.startswith('--' + name + '='):
                return a.split('=', 1)[1]
            if a == '--' + name and i + 1 < len(argv):
                return argv[i + 1]
        return ''

    max_retry = 6
    try:
        max_retry = int(opt('max-retry') or 6)
    except ValueError:
        pass

    cfg_words = None
    cfg_src = ''
    cfg_arg = opt('config')
    if cfg_arg:
        try:
            cfg_words = parse_cfg(cfg_arg)
            cfg_src = '命令行 --config'
        except ValueError as e:
            print('!! %s' % e, flush=True)
            return 1

    quiet = '--quiet' in argv
    do_wake = '--no-wake' not in argv
    probe_only = '--probe-only' in argv
    trace = '--debug' in argv

    if not os.path.exists(hex_path):
        print('!! 固件不存在: %s' % hex_path, flush=True)
        return 1

    scx_words, scx_device, scx_path = read_scx_info(hex_path)
    device = (opt('device') or scx_device or '').strip()

    if cfg_words is None and '--no-config' not in argv:
        if scx_words:
            cfg_words = scx_words
            cfg_src = os.path.basename(scx_path)
        else:
            cfg_words = list(DEFAULT_CFG)
            cfg_src = '脚本默认值'
    if '--no-config' in argv:
        cfg_words = None
        cfg_src = '已禁用（--no-config）'

    # 硬件选项模板：把 FFF7 FAEF … 翻成 WDT=DISABLE / LVR_SEL=1.8V 这类可读状态
    opts_text = ''
    if cfg_words and not quiet:
        cfg_file = opt('cfg-file')
        if not cfg_file and device:
            ide = find_ide_dir(opt('ide') or None)
            if ide:
                cand = os.path.join(ide, 'mcu', 'config', device + '.cfg')
                if os.path.exists(cand):
                    cfg_file = cand
        if cfg_file and os.path.exists(cfg_file):
            try:
                opts_text = format_options(decode_options(cfg_words, cfg_file))
            except Exception as e:
                opts_text = ''
                if trace:
                    print('!! 硬件选项解码失败: %s' % e, flush=True)

    ice = core.Ice6(timeout_ms=700)
    try:
        if not prepare(ice, do_wake=do_wake, verbose=not quiet, trace=trace):
            return 3
    finally:
        ice.close()

    if probe_only:
        print('链路探测通过（未烧写）', flush=True)
        return 0

    ok = flash(hex_path, cfg_words=cfg_words, max_retry=max_retry,
               verbose=not quiet, opts_text=opts_text, cfg_src=cfg_src, trace=trace)
    print('*** 下载成功 ***' if ok else '*** 下载未通过校验 ***', flush=True)
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
