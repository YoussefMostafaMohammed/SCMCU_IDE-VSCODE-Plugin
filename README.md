# SCMCU IDE for VS Code (SC8 Series MCUs)

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.10-orange.svg)](https://github.com/wanguyouy/SCMCU_IDE-VSCODE-Plugin/releases)

**中文文档：[README.md](README.md)**

Compile SC8F/SC8P series MCU projects in VS Code using the SCMCU_IDE MPLAB XC8/PICC toolchain. Configure chip hardware options, select chips, detect the compiler, navigate to build errors, and generate `.hex` and `.scx` files. The extension also detects SCMCU programmers and supports one-click build-and-program and programming an existing build.

## Features

| Command | Description |
|---|---|
| `SCMCU: Build (Generate .hex + .scx)` | Builds the project using the `.scw` device, source-file order, and configuration words. |
| `SCMCU: Build and Flash` | Builds, then programs with a Writer programmer using `.scx` or a CMS-ICE6 simulator using `.hex`. |
| `SCMCU: Flash (Without Building)` | Programs the most recent firmware in `build/` without rebuilding. |
| `SCMCU: Hardware Options` | Configure WDT, PROTECT, LVR, FCPU_DIV, and other hardware options. Saves to `.scw` or workspace settings and synchronizes existing `.scx` configuration words. |
| `SCMCU: Select Chip Model` | Select a chip from the IDE library and update the `.scw` device. |
| `SCMCU: Source File Manager` | Add, remove, and reorder source files. The order is the compilation order. |
| `SCMCU: Configure Compiler Directory` | Set the SCMCU_IDE installation directory manually. |
| `SCMCU: Detect Compiler Automatically` | Search common installation paths, drives, and `SCMCU_IDE_HOME`. |
| `SCMCU: Set Chip Model (Without .scw)` / `SCMCU: Set Configuration Words (Without .scw)` | Configure standalone-project workspace settings. |
| `SCMCU: Startup` | Manually enable the extension after choosing not to load it for a workspace without a `.scw` file. |
| `SCMCU: Normalize Configuration Words` | Repair configuration-word bits copied from a chip with a different word width. |

**Status bar**

- Left side: chip selection, hardware options, build, flash, build-and-flash, and source-file management.
- Right side: programmer detection. Click to refresh; automatic polling runs every five seconds while the VS Code window is focused.
- If no `.scw` file is found, the extension follows `scmcu.noScwBehavior` (ask, load, or skip).

## Getting Started

1. Open a folder containing a `.scw` project in VS Code.
2. Run `SCMCU: Detect Compiler Automatically`, or use `SCMCU: Configure Compiler Directory`.
3. Run `SCMCU: Build`. The build output is written to `build/` by default:
   - `<name>.hex`: Intel HEX program image.
   - `<name>.scx`: SCMCU programming file containing the program and configuration words.
4. To change hardware options, run `SCMCU: Hardware Options`, select the desired values, and save.
5. To select a different chip, click the chip item in the status bar or run `SCMCU: Select Chip Model`.
6. To manage source files, click the source-file item in the status bar or run `SCMCU: Source File Manager`. Reordering files changes compilation order.

## Complete Windows Setup (Downloads, Source Build, and VS Code)

This walkthrough covers a fresh Windows setup: install the SCMCU tools, build this extension from source, configure the local tool paths, and build/program a project. The SCMCU IDE, SCMCU Writer, and this VS Code extension are separate downloads/installations.

### 1. Install the SCMCU IDE and SCMCU Writer

1. Download the SCMCU IDE package and the **normal SCMCU Writer** package from the SCMCU vendor or the distributor that supplied your MCU/programmer. Install or extract each package and note its actual folder. Use a Writer version that supports your programmer and target chip.
2. Check that the IDE folder contains the compiler and chip files:

   ```text
   <SCMCU IDE root>\
   ├── data\bin\picc.exe
   └── mcu\config\
   ```

   The IDE root is the folder above `data` and `mcu`, not the `bin` folder and not `picc.exe` itself.
3. Check that the Writer folder contains the runtime files:

   ```text
   <SCMCU Writer root>\
   ├── data\system.info
   ├── data\database.db
   └── library\Writer.Core.dll
   ```

   If the downloaded Writer archive has an extra nested folder, use the inner folder that contains both `data` and `library` as the Writer root. A copy of `library` by itself is not a complete Writer installation for programming.

### 2. Build the extension from source

Install Node.js (including npm), Git, and Python 3. To rebuild the Writer programming helper, also install the .NET 8+ runtime (or SDK, which includes the runtime); the build script runs the downloaded Roslyn compiler with `dotnet`. The first helper build needs internet access to download Roslyn from NuGet.

Open PowerShell in the extension source folder (the folder containing `package.json`) and run:

```powershell
npm install
npm run compile
npm test
```

The commands install the JavaScript development dependencies, compile the TypeScript extension, and run its regression tests. To build the `.vsix` installer, first configure the Writer library path as described in the next section, then run:

```powershell
npm run package
```

This runs the helper build and creates a file such as `scmcu-vscode-0.9.10.vsix` in the extension source folder. The `package` script requires Python, `dotnet`, the .NET Framework reference assemblies used by the helper, and access to the Writer DLLs.

### 3. Point the Writer helper build at your Writer libraries

`flash\build_helper.py` needs the Writer **library directory** at build time so the C# helper can reference `Writer.Core.dll` and its companion assemblies. Find the `_pick_first(...)` call in that file and add your library directory as a candidate. For example, if the Writer is installed in the nested Program Files location:

```python
writer_lib = (os.environ.get('SCMCU_WRITER_LIB') or
              _pick_first(r'F:/Work/SCMCU_Writer_V9.01.16/library',
                          r'C:/Program Files (x86)/SCMCU_Writer_V9.01.16/SCMCU_Writer_V9.01.16/library',
                          r'C:/Program Files (x86)/SCMCU_Writer_V9.01.16/library',
                          r'C:/Program Files/SCMCU_Writer_V9.01.16/library'))
```

Keep the paths comma-separated and make sure the selected directory contains `Writer.Core.dll`. `_pick_first` selects the first path that exists. Then rebuild the helper from the extension source folder:

```powershell
python flash\build_helper.py
```

Instead of editing the candidate list, you can set `SCMCU_WRITER_LIB` before packaging, or pass `--writer-lib` when building only the helper:

```powershell
$env:SCMCU_WRITER_LIB = 'C:\Program Files (x86)\SCMCU_Writer_V9.01.16\SCMCU_Writer_V9.01.16\library'
npm run package

python flash\build_helper.py --writer-lib 'C:\Program Files (x86)\SCMCU_Writer_V9.01.16\SCMCU_Writer_V9.01.16\library'
```

This helper-build path is **not** the same setting as `scmcu.writerPath`: `_pick_first` (or `SCMCU_WRITER_LIB`) is for compiling the helper; `scmcu.writerPath`, below, is the full Writer installation directory used when the extension programs a chip.

### 4. Install the extension in VS Code

From the extension source folder, install the packaged VSIX using either method:

- In VS Code, open **Extensions** → `...` → **Install from VSIX...**, then select the generated `.vsix`.
- Or run this in PowerShell, replacing the filename if the extension version differs:

  ```powershell
  code --install-extension .\scmcu-vscode-0.9.10.vsix
  ```

Reload VS Code after installation. To test the compiled source directly without installing a VSIX, run `npm run compile`, then launch an Extension Development Host from PowerShell (replace both paths):

```powershell
code --extensionDevelopmentPath "C:\path\to\SCMCU_IDE-VSCODE-Plugin" "C:\path\to\your\MCU-project"
```

### 5. Configure the IDE, compiler, and Writer paths in VS Code

Open the MCU project folder in VS Code. Create or edit that project’s `.vscode\settings.json` (create the `.vscode` folder if needed), or use **Preferences: Open Workspace Settings (JSON)** from the Command Palette. Add the following settings and replace each example with the path on your computer:

```json
{
  "scmcu.idePath": "C:\\Program Files (x86)\\SCMCU_IDE_V2.00.17",
  "scmcu.compilerPath": "C:\\Program Files (x86)\\SCMCU_IDE_V2.00.17\\data\\bin",
  "scmcu.writerPath": "C:\\Program Files (x86)\\SCMCU_Writer_V9.01.16\\SCMCU_Writer_V9.01.16"
}
```

On Windows, JSON strings require doubled backslashes (`\\`). These settings are directories:

- `scmcu.idePath`: IDE root containing `mcu\config` and `data\bin`.
- `scmcu.compilerPath`: the `data\bin` directory containing `picc.exe`; do not include `picc.exe` in the setting.
- `scmcu.writerPath`: full Writer root containing `library\Writer.Core.dll`, `data\system.info`, and `data\database.db`. Do not set this to the `library` subdirectory.

The extension can auto-detect some installations, but explicit settings avoid ambiguity when you have multiple IDE/Writer versions or installed them in non-standard locations. You can also set the compiler using **SCMCU: Configure Compiler Directory** or try **SCMCU: Detect Compiler Automatically**.

### 6. Build and program a project

1. Connect the target board and programmer, and install the programmer’s USB driver if Windows has not already done so.
2. In VS Code, open the project folder containing its `.scw` file.
3. Run **SCMCU: Build (Generate .hex + .scx)** from the Command Palette. The output channel should show the selected chip/compiler and report that the build succeeded. The generated firmware is in the project’s `build` directory.
4. To program using a Writer programmer, run **SCMCU: Build and Flash**. The extension uses the `.scx` file and the Writer path configured above; the Writer GUI does not need to be open. You can also run **SCMCU: Flash (Without Building)** to program the existing output in `build`.
5. Check the **SCMCU** output channel for the programming steps and final success message. A successful Writer download should include messages for the ROM/configuration data and verification, followed by `[OK]`/download complete.

If compilation fails, verify that `scmcu.compilerPath` ends at the folder containing `picc.exe` and that `scmcu.idePath` is the IDE root. If programming reports a missing Writer database or DLL, verify `scmcu.writerPath` is the full Writer root and separately verify that the helper was built with the correct Writer `library` directory. After changing paths or installing the VSIX, reload the VS Code window.

## Build Without a `.scw` Project
- `scmcu.device` (**required**): chip model, for example `SC8F052A04`.
- `scmcu.configWords` (**recommended**): four hexadecimal strings, for example `["0x1FFF","0x3FFF","0x3FFF","0x3FFF"]`. If empty, the extension uses the chip's default unprogrammed values and warns during the build. Verify hardware options before programming.
- `scmcu.sourceFiles` (optional): ordered source-file list relative to the project root. An empty list (the default) scans for `.c`, `.asm`, and `.s` files; a non-empty list is compiled in the specified order.

Commands for standalone settings:

- `SCMCU: Set Chip Model (Without .scw)` writes `scmcu.device` to workspace settings.
- `SCMCU: Set Configuration Words (Without .scw)` accepts four comma-separated hexadecimal values and writes `scmcu.configWords`.

When `scmcu.device` is set, the chip, hardware-options, build, and source-file status-bar actions are available without a `.scw` file. Hardware options and source-file changes are saved to workspace settings in standalone mode; with a `.scw` file, they are saved to the project.

If `scmcu.sourceFiles` is empty, the extension scans the project for `.c`, `.asm`, and `.s` files, excluding common generated and dependency directories. Files are sorted alphabetically. XC8's psect allocation can depend on source order; if the default order causes link errors, use the Source File Manager to create an explicit ordered list.

Both modes produce `build/<name>.hex` and `build/<name>.scx` and use the same build configuration and checksum calculation.

## Configuration-Word Normalization

Copying configuration words from a 16-bit chip (such as SC8F072, default `0xFFFF`) to a 14-bit chip (such as SC8F052, default `0x3FFF`) can leave invalid high bits. For example, `FFFB,FAEF,FFFF,FFFF` may need to become `3FFB,3FEF,3FFF,3FFF`.

- **Automatic:** In standalone mode, if both `scmcu.device` and manually entered `scmcu.configWords` are set, the extension normalizes the words once per workspace. It writes them back only when they change and attempts to update existing `.scx` files.
- **Manual:** Run `SCMCU: Normalize Configuration Words`.

Normalization preserves bits defined by the chip's `mcu/config/<chip>.cfg` template, resets undefined fixed bits for chips that require it, and masks values to the chip's word width. It is idempotent. For 16-bit chips, only the width mask is applied.

Chip width is read from `HEXMCU` in the IDE `.ini` file when available. Otherwise, the extension uses a model-based fallback (`0x3FFF` for supported 14-bit families and `0xFFFF` for 16-bit families).

## Build Output and Checksums

The output channel reports the project, chip, compiler, sources, include directories, configuration words, and generated programming file. Build errors and warnings are also shown in VS Code's Problems panel and can be clicked to navigate to their source locations.

The generated `.scx` file's CfgSum and CfgCRC are calculated to match SCMCU Writer:

```text
CfgSum = (sum of program bytes from 0x100 + checksum configuration bytes) & 0xFFFF
CfgCRC = CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF, xorout=0)
```

The number of configuration-word slots included in the checksum is chip-specific. It is derived from the chip database or configuration template; it is not necessarily four just because `.scx` reserves four slots.

| Project | Chip | Configuration words | Slots | CfgSum | CfgCRC |
|---|---|---|---:|---|---|
| test1 | SC8F052 | `3FFB,3FEF` | 2 | `A5AE` | `20CD` |
| test2 | SC8F052 | `7FFF,FFEF` | 2 | `AA75` | `9665` |
| test3 | SC8F072 | `FFFF,FAEF,FFFF,FFFF` | 4 | `4619` | `EC0D` |

These sample values were checked against SCMCU_Writer. If a newly supported chip reports different values, verify its configuration-word count and core type, then update the relevant tables in `src/scx.ts`.

## Programmer Detection

The status bar detects supported USB devices on Windows.

**Writer programmers** use VID `0x1209`:

| Model | Normal PID | Bootloader PID |
|---|---:|---:|
| WRITER8 LITE | `0x0201` | `0x0101` |
| WRITER V8 | `0x0032` | `0x0011` |
| WRITER V8 PRO | `0x0023` | `0x0021` |
| ICE8 PRO | `0x1502` | `0x1102` |

**CMS-ICE6 simulator**:

| Model | VID | PID |
|---|---:|---:|
| CMS-ICE6 | `0x0925` | `0x0283` |

The extension checks once after activation and polls every five seconds while the window is focused. Clicking the status item refreshes detection immediately. Bootloader-mode Writer devices are reported with a reminder to restore normal firmware using SCMCU Writer.

## Build and Program

`SCMCU: Build and Flash` builds first; `SCMCU: Flash (Without Building)` programs the existing output in `build/`. Both commands select a channel based on the connected device:

| Device | Input | Requirements |
|---|---|---|
| Writer programmer (`0x1209`) | `.scx` | SCMCU_Writer must be installed so the extension can use its chip database and libraries. |
| CMS-ICE6 (`0x0925`) | `.hex` | No Writer installation required. The extension includes the programming script and Python runtime. |

### Writer channel

The extension runs `flash/ScmcuFlashHelper.exe` and loads the Writer libraries from the configured or detected SCMCU_Writer installation. The GUI does not need to be open.

- `scmcu.writerPath`: Writer installation path. If empty, the extension searches common drive and software directories for `SCMCU_Writer*`.
- `scmcu.flashCount`: maximum allowed programming operations for the firmware. `0` (the default) means unlimited; a positive integer sets a limit.
- The helper can be rebuilt with `npm run build:helper` or `python flash/build_helper.py`.

### CMS-ICE6 channel

The extension uses `flash/ice6_flash.py` and the bundled embeddable Python runtime in `flash/py/`; a system Python installation is not required. Set `SCMCU_BUILD_PY` to use a different Python executable.

The script performs the device handshake, erase, programming, read-back verification, configuration-word update, and cleanup. Progress is displayed in the VS Code status bar.

**Before programming**

- Ensure the target board is powered (approximately 4.5 V VDD).
- Close SCMCU IDE before programming. It can take exclusive control of the ICE6 and leave it unable to write until the USB device is disconnected and reconnected.

If verification reports that the chip was erased but no data was written, disconnect and reconnect the ICE6, then retry.

## Settings

| Setting | Description |
|---|---|
| `scmcu.compilerPath` | SCMCU_IDE `data\\bin` directory containing `picc.exe`. Empty means automatic detection. |
| `scmcu.idePath` | SCMCU_IDE root containing `mcu\\config`. Empty means automatic detection. |
| `scmcu.buildDir` | Build output directory, relative to the project root. Default: `build`. |
| `scmcu.outputName` | Output filename without an extension. Default: `SCMCU_Project`. |
| `scmcu.sourceDirs` | C source directories relative to the project root. Empty string means the project root. Default: `["src"]`. |
| `scmcu.includeDirs` | Header include directories; added to the compiler's `-I` options. Default: `["inc"]`. |
| `scmcu.device` | Chip model required for builds without `.scw`. |
| `scmcu.configWords` | Four hexadecimal configuration words for builds without `.scw`. Empty uses unprogrammed defaults and emits a warning. |
| `scmcu.sourceFiles` | Ordered source-file list for builds without `.scw`. Empty triggers automatic scanning. |
| `scmcu.noScwBehavior` | Behavior when no `.scw` is found: `prompt` (default), `load`, or `skip`. |
| `scmcu.writerPath` | SCMCU_Writer installation directory. Empty triggers automatic detection. |
| `scmcu.flashCount` | Maximum programming operations for offline Writer programming. Default `0` means unlimited. |

## Development

```bash
npm install
npm run compile
npm test
npm run package
```

- `npm test` runs the configuration-word and programmer-detection regression suites.
- `npm run package` creates `scmcu-vscode-<version>.vsix`.
- Press **F5** in VS Code to launch an Extension Development Host.
- `npm run build:helper` rebuilds the Writer flash helper.

The regression tests use fixtures under `test/fixtures` and do not require SCMCU_IDE to be installed on the development machine.

## Project Structure

```text
src/
├── extension.ts             # Commands, status bar, activation, and programming workflow
├── build.ts                 # Compiler orchestration and diagnostics
├── chip.ts                  # .scw parsing, chip data, and configuration-word handling
├── compiler.ts              # Compiler discovery
├── scx.ts                   # .scx generation and checksum calculation
├── programmer.ts            # USB programmer/simulator detection
├── flash.ts                 # Writer and CMS-ICE6 programming channels
└── webview/
    ├── hardwareOptions.ts   # Hardware-options panel
    └── sourceManager.ts     # Ordered source-file manager
flash/
├── ScmcuFlashHelper.cs      # Writer-channel helper source
├── ice6_flash.py            # CMS-ICE6 download orchestration
├── ice6_flash_core.py       # CMS-ICE6 protocol primitives
└── py/                      # Bundled Python runtime
l10n/
├── bundle.l10n.json         # Default runtime localization catalog
└── bundle.l10n.zh-cn.json   # Simplified Chinese runtime translations
```

## Version History

| Version | Highlights |
|---|---|
| **v0.9.10** | Bundled Python runtime; no system Python required for CMS-ICE6 programming. |
| **v0.9.9** | Simplified programming progress output. |
| **v0.9.8** | Progress moved to the status bar; concise output. |
| **v0.9.7** | Added readable hardware-option information and programming progress. |
| **v0.9.6** | CMS-ICE6 programming and flash-without-building command. |
| **v0.9.5** | Chip-specific configuration-word slot counts and Writer-matching checksums. |
| **v0.9.0** | Configuration-word normalization, programmer detection, and Writer programming channel. |
| **v0.8.x** | Source-file manager and standalone mode support. |
| **v0.6.x** | Configurable source/include directories, error navigation, and checksum alignment. |
| **v0.3.x** | Hardware-options panel and status-bar chip selection/build actions. |
| **v0.1.x** | Initial build, hardware-options, and compiler auto-detection features. |
