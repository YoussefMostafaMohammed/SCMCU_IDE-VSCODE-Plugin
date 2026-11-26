# -*- coding: utf-8 -*-
"""CMS-ICE6 下载器（最终版）—— 复刻 SCMCU IDE V2.00.17 的真实下载协议。

协议要点（2026-11-26 Frida 抓包 + 真机验证通过）：
  * HID 报文 = [ReportID=0x00] + 64B payload；payload = [len][op][args][SUM8]
  * 抓包 wire 已含 ReportID，交给 write() 前必须剥掉，否则整帧错位一字节，
    设备对一切命令都回通用错误码 (03 31 34)。这是此前"能通信却写不进"的根因。
  * 握手帧 0xFC/0x18 无校验和；数据帧 01/03/06/0C/17 带 SUM8。
  * 0x17 完整 64B 帧 = 芯片配置 + 高压参数（ERASE / PROGTIME / VPPMODE），
    高压由 ICE6 硬件按帧内参数自行产生，主机原样下发即可。
  * op=0x01 编程帧：地址为【字地址】，步进 0x18(24 字)，48 字节/帧。
  * 单次编程脉冲常不足以烧透全部位（实测会出现"位漏烧"），
    必须【回读校验 + 重发】，编程只能清位，重发会收敛到目标值。
  * 回读 op=0x06 每次 32 字，64 字节里偶数位为字低字节、奇数位恒 0。

用法: python ice6_flash_final.py <firmware.hex> [--max-retry N] [--quiet]
"""
import sys, os, time

import ctypes, time
from ctypes import wintypes

DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
FILE_FLAG_OVERLAPPED = 0x40000000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x1
FILE_SHARE_WRITE = 0x2
OPEN_EXISTING = 3

class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]
class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]
class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT), ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT), ("Reserved", wintypes.USHORT * 17),
                ("NumberLinkCollectionNodes", wintypes.USHORT), ("NumberInputButtonCaps", wintypes.USHORT),
                ("NumberInputValueCaps", wintypes.USHORT), ("NumberInputDataIndices", wintypes.USHORT),
                ("NumberOutputButtonCaps", wintypes.USHORT), ("NumberOutputValueCaps", wintypes.USHORT),
                ("NumberOutputDataIndices", wintypes.USHORT), ("NumberFeatureButtonCaps", wintypes.USHORT),
                ("NumberFeatureValueCaps", wintypes.USHORT), ("NumberFeatureDataIndices", wintypes.USHORT)]
class OVERLAPPED(ctypes.Structure):
    _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE)]

hid = ctypes.WinDLL('hid.dll')
setup = ctypes.WinDLL('setupapi.dll', use_last_error=True)
kernel32 = ctypes.WinDLL('kernel32.dll', use_last_error=True)
kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(OVERLAPPED)]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
# 句柄必须按 64 位声明，否则 ctypes 默认按 int 传递会截断高 32 位
kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.c_void_p]
kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL,
                                  wintypes.LPCWSTR]
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED)]
kernel32.CancelIoEx.restype = wintypes.BOOL
kernel32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(OVERLAPPED),
                                         ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
kernel32.GetOverlappedResult.restype = wintypes.BOOL
ERROR_IO_PENDING = 997
ERROR_IO_INCOMPLETE = 996

def sum8(data): return sum(data) & 0xFF

def make_cmd(*body):
    body = list(body)
    p = bytearray(64)
    p[0] = len(body) + 2
    p[1:1+len(body)] = body
    p[p[0]-1] = sum8(p[0:p[0]-1])
    return bytes(p)

def hexline(b, n=None):
    end = min(len(b), n) if n else len(b)
    return ' '.join('%02X' % x for x in b[:end])

def find_device(vid=0x0925, pid=0x0283):
    guid = GUID(); hid.HidD_GetHidGuid(ctypes.byref(guid))
    hdev = setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if hdev == INVALID_HANDLE_VALUE: return None
    did = SP_DEVICE_INTERFACE_DATA(); did.cbSize = ctypes.sizeof(did)
    i = 0; paths = []
    while setup.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), i, ctypes.byref(did)):
        needed = wintypes.DWORD()
        setup.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), None, 0, ctypes.byref(needed), None)
        buf = ctypes.create_string_buffer(needed.value); detail = ctypes.cast(buf, ctypes.c_void_p)
        ctypes.cast(detail, ctypes.POINTER(wintypes.DWORD))[0] = 8
        if setup.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(did), detail, needed.value, None, None):
            path = ctypes.cast(detail.value + 4, ctypes.c_wchar_p).value or ""
            h = kernel32.CreateFileW(path, 0, 0x1|0x2, None, 3, 0, None)
            if h != INVALID_HANDLE_VALUE:
                a = HIDD_ATTRIBUTES(); a.Size = ctypes.sizeof(a)
                if hid.HidD_GetAttributes(h, ctypes.byref(a)) and a.VendorID == vid and a.ProductID == pid:
                    paths.append(path)
                kernel32.CloseHandle(h)
        i += 1
    setup.SetupDiDestroyDeviceInfoList(hdev)
    return paths[0] if paths else None

class Ice6:
    def __init__(self, timeout_ms=400, vid=0x0925, pid=0x0283):
        self.path = find_device(vid, pid)
        if not self.path: raise RuntimeError('HID device %04X:%04X not found' % (vid, pid))
        self.h = kernel32.CreateFileW(self.path, GENERIC_READ|GENERIC_WRITE,
                                      FILE_SHARE_READ|FILE_SHARE_WRITE, None,
                                      OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if self.h == INVALID_HANDLE_VALUE:
            raise RuntimeError('CreateFile failed: %d' % ctypes.get_last_error())
        pre = ctypes.c_void_p()
        if hid.HidD_GetPreparsedData(self.h, ctypes.byref(pre)):
            caps = HIDP_CAPS(); hid.HidP_GetCaps(pre, ctypes.byref(caps))
            self.in_len, self.out_len = caps.InputReportByteLength, caps.OutputReportByteLength
            hid.HidD_FreePreparsedData(pre)
        else:
            self.in_len = self.out_len = 65
        self.timeout = timeout_ms

    def close(self):
        kernel32.CloseHandle(self.h)

    def _reap(self, ov, got, ev, budget_ms=400):
        """取消后等 IRP 真正结束。全程有界轮询，绝不用 bWait=True（设备不回包时会永久挂死）。"""
        deadline = time.time() + budget_ms / 1000.0
        while time.time() < deadline:
            if kernel32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(got), False):
                return True
            err = ctypes.get_last_error()
            if err != ERROR_IO_INCOMPLETE:
                return False
            time.sleep(0.005)
        return False

    def _read_raw(self, timeout_ms=None):
        t = self.timeout if timeout_ms is None else timeout_ms
        ev = kernel32.CreateEventW(None, True, False, None)
        ov = OVERLAPPED(); ov.hEvent = ev
        buf = ctypes.create_string_buffer(self.in_len)
        read = wintypes.DWORD()
        ok = kernel32.ReadFile(self.h, buf, self.in_len, ctypes.byref(read), ctypes.byref(ov))
        if not ok:
            err = ctypes.get_last_error()
            if err != ERROR_IO_PENDING:
                kernel32.CloseHandle(ev)
                raise RuntimeError('ReadFile failed: %d' % err)
            if kernel32.WaitForSingleObject(ev, t) != WAIT_OBJECT_0:
                kernel32.CancelIoEx(self.h, ctypes.byref(ov))
                if self._reap(ov, read, ev):
                    kernel32.CloseHandle(ev)
                return None
            kernel32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(read), False)
        kernel32.CloseHandle(ev)
        b = bytes(buf[:read.value])
        return b[1:] if b and b[0] == 0 else b  # strip report ID

    def drain(self, max_reads=64):
        """读空当前所有 pending 的 input report（有上限，防止死循环）。"""
        n = 0
        while n < max_reads and self._read_raw(40) is not None:
            n += 1
        return n

    def write(self, payload):
        wire = b'\x00' + payload  # report ID prefix
        ev = kernel32.CreateEventW(None, True, False, None)
        ov = OVERLAPPED(); ov.hEvent = ev
        written = wintypes.DWORD()
        ok = kernel32.WriteFile(self.h, wire, len(wire), ctypes.byref(written), ctypes.byref(ov))
        if ok:
            kernel32.CloseHandle(ev)
            return written.value
        err = ctypes.get_last_error()
        if err != ERROR_IO_PENDING:
            kernel32.CloseHandle(ev)
            raise RuntimeError('WriteFile failed: %d' % err)
        if kernel32.WaitForSingleObject(ev, self.timeout) != WAIT_OBJECT_0:
            # 设备不收包（输入队列积压/目标板掉电）时取消本次写，抛异常让上层重连，
            # 而不是像旧版那样 GetOverlappedResult(bWait=True) 无限期挂住
            kernel32.CancelIoEx(self.h, ctypes.byref(ov))
            if self._reap(ov, written, ev):
                kernel32.CloseHandle(ev)
            raise IOError('write timeout (%d ms)' % self.timeout)
        kernel32.GetOverlappedResult(self.h, ctypes.byref(ov), ctypes.byref(written), False)
        kernel32.CloseHandle(ev)
        return written.value

    def cmd(self, *body, want_raw=False, match=None, max_tries=8, timeout_ms=None):
        """发命令，读应答。match(payload)->bool 用于挑出目标应答。"""
        self.drain()
        payload = make_cmd(*body)
        self.write(payload)
        last = None
        for _ in range(max_tries):
            r = self._read_raw(timeout_ms)
            if r is None:
                break
            last = r
            n = r[0] if r else 0
            if match:
                if match(r): return r
            elif want_raw:
                if n >= 0x20 and r[1:3] != b'\x01\x00': return r
            else:
                if 3 <= n <= 64 and n <= len(r) and r[n-1] == sum8(r[:n-1]) and n >= 3:
                    return r
        return last


# ---- IDE 抓包的完整帧序列(控制帧原样, 编程帧= None 占位) ----
CONTROL_FRAMES = [
    '0003fcff1e16ffffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 0 op=FC
    '0003181b1e16ffffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 1 op=18
    '00041b001f16ffffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 2 op=1B
    '004017015dff0704003f00ffff00011f001f001f001f0000000000fa00fa009600890000000000000000000000000000000000000000000000000000000000008c',  # 3 op=17
    '00050c0210230704003f00ffff00011f001f001f001f0000000000fa00fa009600890000000000000000000000000000000000000000000000000000000000008c',  # 4 op=0C
    None,  # 5 PROG
    None,  # 6 PROG
    None,  # 7 PROG
    None,  # 8 PROG
    None,  # 9 PROG
    None,  # 10 PROG
    None,  # 11 PROG
    None,  # 12 PROG
    None,  # 13 PROG
    None,  # 14 PROG
    None,  # 15 PROG
    None,  # 16 PROG
    None,  # 17 PROG
    None,  # 18 PROG
    None,  # 19 PROG
    None,  # 20 PROG
    None,  # 21 PROG
    None,  # 22 PROG
    None,  # 23 PROG
    None,  # 24 PROG
    None,  # 25 PROG
    None,  # 26 PROG
    None,  # 27 PROG
    None,  # 28 PROG
    None,  # 29 PROG
    None,  # 30 PROG
    None,  # 31 PROG
    None,  # 32 PROG
    None,  # 33 PROG
    None,  # 34 PROG
    None,  # 35 PROG
    None,  # 36 PROG
    None,  # 37 PROG
    None,  # 38 PROG
    None,  # 39 PROG
    None,  # 40 PROG
    None,  # 41 PROG
    None,  # 42 PROG
    None,  # 43 PROG
    None,  # 44 PROG
    None,  # 45 PROG
    None,  # 46 PROG
    None,  # 47 PROG
    None,  # 48 PROG
    None,  # 49 PROG
    None,  # 50 PROG
    None,  # 51 PROG
    None,  # 52 PROG
    None,  # 53 PROG
    None,  # 54 PROG
    None,  # 55 PROG
    None,  # 56 PROG
    None,  # 57 PROG
    None,  # 58 PROG
    None,  # 59 PROG
    None,  # 60 PROG
    None,  # 61 PROG
    None,  # 62 PROG
    None,  # 63 PROG
    None,  # 64 PROG
    None,  # 65 PROG
    None,  # 66 PROG
    None,  # 67 PROG
    None,  # 68 PROG
    None,  # 69 PROG
    None,  # 70 PROG
    None,  # 71 PROG
    None,  # 72 PROG
    None,  # 73 PROG
    None,  # 74 PROG
    None,  # 75 PROG
    None,  # 76 PROG
    None,  # 77 PROG
    None,  # 78 PROG
    None,  # 79 PROG
    None,  # 80 PROG
    None,  # 81 PROG
    None,  # 82 PROG
    None,  # 83 PROG
    None,  # 84 PROG
    None,  # 85 PROG
    None,  # 86 PROG
    None,  # 87 PROG
    None,  # 88 PROG
    None,  # 89 PROG
    None,  # 90 PROG
    '000d030000ffffffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 91 op=03
    '00050c010416ffffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 92 op=0C
    '0006060000404cffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 93 op=06
    '0006062000406cffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 94 op=06
    '0006064000408cffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 95 op=06
    '000606600040acffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 96 op=06
    '000606800040ccffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 97 op=06
    '000606a00040ecffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 98 op=06
    '000606c000400cffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 99 op=06
    '000606e000402cffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 100 op=06
    '0006060001404dffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 101 op=06
    '0006062001406dffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 102 op=06
    '0006064001408dffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 103 op=06
    '000606600140adffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 104 op=06
    '000606800140cdffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 105 op=06
    '000606a00140edffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 106 op=06
    '000606c001400dffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 107 op=06
    '000606e001402dffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 108 op=06
    '0006060002404effffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 109 op=06
    '0006062002406effffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 110 op=06
    '0006064002408effffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 111 op=06
    '000606600240aeffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 112 op=06
    '000606800240ceffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 113 op=06
    '000606a00240eeffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 114 op=06
    '000606c002400effffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 115 op=06
    '000606e002402effffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 116 op=06
    '0006060003404fffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 117 op=06
    '0006062003406fffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 118 op=06
    '0006064003408fffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 119 op=06
    '000606600340afffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 120 op=06
    '000606800340cfffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 121 op=06
    '000606a00340efffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 122 op=06
    '000606c003400fffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 123 op=06
    '000606e003402fffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 124 op=06
    '00060600044050ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 125 op=06
    '00060620044070ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 126 op=06
    '00060640044090ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 127 op=06
    '000606600440b0ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 128 op=06
    '000606800440d0ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 129 op=06
    '000606a00440f0ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 130 op=06
    '000606c0044010ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 131 op=06
    '000606e0044030ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 132 op=06
    '00060600054051ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 133 op=06
    '00060620054071ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 134 op=06
    '00060640054091ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 135 op=06
    '000606600540b1ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 136 op=06
    '000606800540d1ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 137 op=06
    '000606a00540f1ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 138 op=06
    '000606c0054011ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 139 op=06
    '000606e0054031ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 140 op=06
    '00060600064052ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 141 op=06
    '00060620064072ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 142 op=06
    '00060640064092ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 143 op=06
    '000606600640b2ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 144 op=06
    '000606800640d2ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 145 op=06
    '000606a00640f2ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 146 op=06
    '000606c0064012ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 147 op=06
    '000606e0064032ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 148 op=06
    '00060600074053ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 149 op=06
    '00060620074073ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 150 op=06
    '00060640074093ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 151 op=06
    '000606600740b3ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 152 op=06
    '000606800740d3ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 153 op=06
    '000606a00740f3ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 154 op=06
    '000606c0074013ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 155 op=06
    '000606e0074033ffffffffffff086400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 156 op=06
    '000d030000f7ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 157 op=03
    '00050c010416ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 158 op=0C
    '00040d001116ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 159 op=0D
    '00040b000f16ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 160 op=0B
    '000404000816ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 161 op=04
    '00040f001316ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 162 op=0F
    '000413001716ffeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 163 op=13
    '00061100004057effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 164 op=11
    '00061140004097effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 165 op=11
    '000611800040d7effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 166 op=11
    '000611c0004017effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 167 op=11
    '00061100014058effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 168 op=11
    '00061140014098effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 169 op=11
    '000611800140d8effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 170 op=11
    '000611c0014018effaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 171 op=11
    '0006090000000feffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 172 op=09
    '0006090000404feffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 173 op=09
    '0006090000808feffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 174 op=09
    '0006090000c0cfeffaffffffffeb6400fc2f8301ea2f2dffffff8b017230940081010514851483160516851683128517851683160612fc0000000000000000008c',  # 175 op=09
]

ROM_WORDS = 0x800
BLOCK_BYTES = 0x30  # 每次编程 48 字节


def parse_hex(path):
    mem = {}
    for ln in open(path, encoding='utf-8', errors='replace').read().splitlines():
        ln = ln.strip()
        if not ln.startswith(':'): continue
        n = int(ln[1:3],16); addr = int(ln[3:7],16); typ = int(ln[7:9],16)
        if typ == 1: break
        if typ != 0: continue
        data = bytes.fromhex(ln[9:9+2*n])
        for i,x in enumerate(data): mem[addr+i] = x
    return mem


def build_image(mem):
    img = bytearray([0xFF]) * (ROM_WORDS * 2)
    for a,x in mem.items():
        if a < len(img): img[a] = x
    return img


def make_prog_payload(wa_word, data):
    """构造 op=0x01 编程帧的 64B payload（**不含 ReportID**，由 Ice6.write 统一补）。
    帧格式: [len=0x36][op=01][addr_lo][addr_hi][cnt=48][48B data][SUM8]"""
    cnt = len(data)
    payload = bytearray(64)
    body = [0x01, wa_word & 0xFF, (wa_word >> 8) & 0xFF, cnt] + list(data)
    payload[0] = len(body) + 2
    payload[1:1 + len(body)] = body
    payload[payload[0] - 1] = sum8(payload[:payload[0] - 1])
    return bytes(payload)


def wire_to_payload(raw):
    """抓包里的 wire 含首字节 ReportID(0x00)，write() 会自己补，故须剥掉，否则整帧错位。"""
    if raw and raw[0] == 0x00 and len(raw) == 65:
        return raw[1:]
    return raw




ROM_WORDS = 0x800
BLOCK_W = 0x18          # 24 字 / 编程帧
BLOCK_B = BLOCK_W * 2   # 48 字节
READ_W = 32             # op06 单次读 32 字


def full_17_payload():
    for w in CONTROL_FRAMES:
        if w and bytes.fromhex(w)[2] == 0x17:
            return wire_to_payload(bytes.fromhex(w))
    raise RuntimeError('模板缺少 0x17 配置帧')


def read_block(ice, wa, tries=4):
    """读 32 字（64B）。偶数位=字低字节，奇数位恒 0。"""
    for _ in range(tries):
        ice.drain()
        ice.write(make_cmd(0x06, wa & 0xFF, (wa >> 8) & 0xFF, 0x40))
        for _ in range(3):
            r = ice._read_raw(220)
            if r is None:
                break
            if len(r) >= 64 and not (r[0] == 0x03 and r[1] in (0x30, 0x31)):
                return bytes(r[:64])
    return None


def send_ack(ice, payload, timeout=500):
    ice.write(payload)
    for _ in range(3):
        r = ice._read_raw(timeout)
        if r is None:
            return None
        if len(r) >= 3 and r[0] == 0x03:
            return chr(r[1]) + chr(r[2])
    return None


def flash(hex_path, max_retry=40, verbose=True):
    mem = parse_hex(hex_path)
    img = build_image(mem)
    if verbose:
        print('固件: %s  (有效 %d 字节)' % (os.path.basename(hex_path), len(mem)), flush=True)

    ice = Ice6(timeout_ms=300)
    try:
        code = send_ack(ice, make_cmd(0x50, 0x53))
        if verbose:
            print('ICE6 自检: %s' % code, flush=True)

        if send_ack(ice, full_17_payload()) != '03':
            print('!! 0x17 配置帧被拒绝，中止', flush=True)
            return False
        if verbose:
            print('0x17 配置帧 + 高压参数: ACK 03 (OK)', flush=True)

        blocks = []
        for wa in range(0, ROM_WORDS, BLOCK_W):
            seg = img[wa * 2: wa * 2 + BLOCK_B]
            if any(b != 0xFF for b in seg):
                blocks.append((wa, bytes(seg)))
        if verbose:
            print('需编程 %d 块（其余为 0xFF 空白，跳过）' % len(blocks), flush=True)

        retries = 0
        failed = []
        for n, (wa, seg) in enumerate(blocks):
            payload = make_prog_payload(wa, list(seg))
            ok = False
            attempt = 0
            for attempt in range(max_retry):
                ice.write(payload)
                time.sleep(0.115)          # 24 字 x ~4.6ms 编程周期 + 余量
                ice.drain()
                rd_base = wa & ~(READ_W - 1)
                got = read_block(ice, rd_base)
                if got is None:
                    continue
                good = True
                for k in range(0, len(seg), 2):
                    gi = wa * 2 + k - rd_base * 2
                    if 0 <= gi < len(got) and got[gi] != seg[k]:
                        good = False
                        break
                if good:
                    ok = True
                    retries += attempt
                    break
            if not ok:
                failed.append(wa)
            if verbose:
                print('  块 %2d/%2d @%04X  %s%s' % (
                    n + 1, len(blocks), wa, 'OK' if ok else '!! FAIL',
                    ('  (重试 %d 次)' % attempt) if ok and attempt else ''), flush=True)

        mism = 0
        for wa in range(0, ROM_WORDS, READ_W):
            got = read_block(ice, wa)
            if got is None:
                mism += READ_W
                continue
            for k in range(0, READ_W * 2, 2):
                a = wa * 2 + k
                if a < len(img) and img[a] != got[k]:
                    mism += 1
        if verbose:
            print('--- 完成: 重试 %d 次, 失败块 %d, 全片差异 %d 处 ---' % (
                retries, len(failed), mism), flush=True)
        return not failed and mism == 0
    finally:
        ice.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    mr = 40
    if '--max-retry' in sys.argv:
        mr = int(sys.argv[sys.argv.index('--max-retry') + 1])
    quiet = '--quiet' in sys.argv
    ok = flash(sys.argv[1], max_retry=mr, verbose=not quiet)
    print('*** 下载成功 ***' if ok else '*** 下载未通过校验 ***')
    return 0 if ok else 2


if __name__ == '__main__':
    sys.exit(main())
