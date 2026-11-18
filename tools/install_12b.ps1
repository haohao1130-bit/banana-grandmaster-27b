param([string]$Root = 'F:\BANANAMV_12B_STUDIO')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Thin installation: only a new App checkout, per-studio data and Gemma models.
# The already working 27B studio owns the shared CUDA13, ComfyUI/H3 and music runtimes.
$Root = [System.IO.Path]::GetFullPath($Root)
$SharedRoot = 'F:\AI\BANANAMV_27B_STUDIO'
if (!$Root.StartsWith('F:\', [System.StringComparison]::OrdinalIgnoreCase) -or
    $Root.TrimEnd('\') -ieq 'F:' -or
    $Root -like 'F:\AI\BANANAMV_27B_STUDIO*') {
    throw '12B must install under its own F: directory, never into the existing 27B studio.'
}
$App = Join-Path $Root 'App'
$Models = Join-Path $Root 'Models'
$Logs = Join-Path $Root 'Logs'
$Data = Join-Path $Root 'Data'
$Output = Join-Path $Root 'Output'
$Cache = Join-Path $Root 'Cache'
$LocalRuntime = Join-Path $Root 'Runtime'
$SharedRuntime = Join-Path $SharedRoot 'Runtime'
$SharedComfy = Join-Path $SharedRuntime 'ComfyUI'
$SharedH3 = Join-Path $SharedRoot 'Models\H3'
$Python = Join-Path $SharedRuntime 'venv\Scripts\python.exe'
$MusicPython = Join-Path $SharedRuntime 'music-venv\Scripts\python.exe'
$Llama = Join-Path $SharedRuntime 'llama.cpp\llama-server.exe'

foreach ($dir in @($Root,$Models,$Logs,$Data,$Output,$Cache,$LocalRuntime)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$env:HF_HOME = Join-Path $Cache 'huggingface'
$env:HF_HUB_ENABLE_HF_TRANSFER = '0'
Start-Transcript -Path (Join-Path $Logs 'install_12b.log') -Append | Out-Null
try {
    Write-Host '12B thin install: reusing the existing F:\AI 27B runtime and H3 weights.'
    if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git not found on PATH; the original studio Git is required.' }

    # Do not touch or repair existing Python, CUDA, ComfyUI, H3 or music packages.
    $required = @(
        $Python,
        $MusicPython,
        $Llama,
        (Join-Path $SharedComfy 'main.py'),
        (Join-Path $SharedH3 'diffusion_models\Minimax-h3_Singularity_x_10Eros-Max_PRISM_int8.safetensors'),
        (Join-Path $SharedH3 'text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'),
        (Join-Path $SharedH3 'vae\minimax_h3_video_vae_int8_convrot.safetensors'),
        (Join-Path $SharedH3 'vae\minimax_h3_audio_vae_fp32.safetensors'),
        (Join-Path $SharedH3 'loras\H3_Combat_V2.safetensors'),
        (Join-Path $SharedH3 'loras\Motion_Repair.safetensors')
    )
    foreach ($file in $required) {
        if (!(Test-Path -LiteralPath $file -PathType Leaf) -or
            (Get-Item -LiteralPath $file).Length -eq 0) {
            throw "Missing shared 5070 asset: $file. Existing studio was not modified."
        }
    }
    $devices = (& $Llama --list-devices 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $devices -notmatch 'CUDA0:') {
        throw "Shared llama.cpp CUDA13 failed GPU detection: $devices"
    }
    Write-Host ($devices.Trim())
    & $Python -c 'import huggingface_hub, PIL, torch; print("Shared Python libraries: OK")'
    if ($LASTEXITCODE -ne 0) { throw 'The existing 27B Python venv lacks required packages. No shared packages were changed.' }

    # Locate the installed FFmpeg/ffprobe pair. Winget may report "installed"
    # but not export their locations into the current Windows PATH.
    function Find-FFmpegBin {
        $exe = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
        if ($exe -and $exe.Source) {
            $dir = Split-Path -Parent $exe.Source
            if (Test-Path -LiteralPath (Join-Path $dir 'ffprobe.exe')) { return $dir }
        }
        $candidates = @(
            'F:\AI\Tools',
            'F:\AI\NVEncC',
            (Join-Path $SharedRuntime 'ffmpeg'),
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),
            (Join-Path $env:ProgramFiles 'WinGet\Packages'),
            (Join-Path $env:ProgramFiles 'ffmpeg'),
            'C:\ffmpeg'
        )
        foreach ($base in $candidates) {
            if (!$base -or !(Test-Path -LiteralPath $base)) { continue }
            $match = Get-ChildItem -LiteralPath $base -Filter 'ffmpeg.exe' -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.DirectoryName 'ffprobe.exe') } |
                Select-Object -First 1
            if ($match) { return $match.DirectoryName }
        }
        return $null
    }
    $FFmpegBin = Find-FFmpegBin
    if (!$FFmpegBin) {
        throw 'FFmpeg is installed according to winget but its binaries could not be located. Run: Get-Command ffmpeg -All; where.exe ffmpeg. No FFmpeg download was attempted.'
    }
    $env:PATH = "$FFmpegBin;$env:PATH"
    [IO.File]::WriteAllText((Join-Path $LocalRuntime 'ffmpeg_path.txt'), $FFmpegBin,
        (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Reusing existing FFmpeg: $FFmpegBin"

    $branch = 'experiment/rtx5070-gemma3-12b'
    $gitUrl = 'https://github.com/haohao1130-bit/banana-grandmaster-27b.git'
    if (!(Test-Path -LiteralPath (Join-Path $App '.git'))) {
        if ((Test-Path -LiteralPath $App) -and @(Get-ChildItem -LiteralPath $App -Force).Count -gt 0) {
            throw "12B App is nonempty but not a Git checkout: $App"
        }
        & git clone --single-branch --branch $branch $gitUrl $App
        if ($LASTEXITCODE -ne 0) { throw '12B branch clone failed.' }
    } else {
        $remote = (& git -C $App remote get-url origin).Trim()
        if ($remote -notlike '*haohao1130-bit/banana-grandmaster-27b*') {
            throw "12B App has unexpected Git remote: $remote"
        }
        $current = (& git -C $App branch --show-current).Trim()
        if ($current -ne $branch) { throw "Refusing to change existing App branch: $current" }
        $dirty = & git -C $App status --porcelain
        if (!$dirty) {
            & git -C $App pull --ff-only origin $branch
            if ($LASTEXITCODE -ne 0) { throw '12B Git fast-forward failed; no reset was attempted.' }
        } else {
            Write-Warning 'Local App edits found; skipping automatic update, no reset.'
        }
    }
    Write-Host "12B source: $((& git -C $App log -1 --oneline))"

    # The H3 writing guide is already present in the existing 27B studio.
    $guide = Join-Path $App 'guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'
    if (!(Test-Path $guide) -or (Get-Item $guide).Length -lt 1000) {
        $sourceGuide = Join-Path $SharedRoot 'App\guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'
        if (!(Test-Path $sourceGuide) -or (Get-Item $sourceGuide).Length -lt 1000) {
            throw "Cannot locate existing H3 director guide: $sourceGuide"
        }
        New-Item -Path (Split-Path $guide) -ItemType Directory -Force | Out-Null
        Copy-Item -LiteralPath $sourceGuide -Destination $guide
    }

    # Point ComfyUI at existing H3 weights: zero copies, zero H3 downloads.
    $yamlPath = Join-Path $LocalRuntime 'extra_model_paths.yaml'
    $h3Path = $SharedH3.Replace('\','/')
    $yamlText = @(
        'banana12b:'
        "  base_path: '$h3Path'"
        '  diffusion_models: diffusion_models'
        '  text_encoders: text_encoders'
        '  vae: vae'
        '  loras: loras'
    ) -join [Environment]::NewLine
    [IO.File]::WriteAllText($yamlPath, $yamlText, (New-Object System.Text.UTF8Encoding($false)))

    # ONLY two files are downloaded: Gemma 12B Q5 and its matched F16 mmproj.
    Write-Host 'Downloading/checking only the two Gemma 3 12B GGUF files...'
    & $Python (Join-Path $App 'tools\install_12b_models.py') --models-root $Models
    if ($LASTEXITCODE -ne 0) { throw 'Gemma model download failed; rerun installer to resume.' }

    $launchCmd = Join-Path $Root 'Launch_BANANAMV_12B.cmd'
    $launchText = "@echo off" + [Environment]::NewLine +
        "chcp 65001 >nul" + [Environment]::NewLine +
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0App\tools\launch_12b.ps1"' +
        [Environment]::NewLine + 'if errorlevel 1 pause' + [Environment]::NewLine
    [IO.File]::WriteAllText($launchCmd,$launchText,(New-Object System.Text.UTF8Encoding($false)))
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'BANANAMV 12B.lnk'))
        $shortcut.TargetPath = $launchCmd
        $shortcut.WorkingDirectory = $Root
        $shortcut.Description = 'BANANAMV Gemma 3 12B Q5, shared 5070 runtime'
        $shortcut.Save()
    } catch { Write-Warning 'Desktop shortcut not created; use Launch_BANANAMV_12B.cmd.' }
    Write-Host '12B thin installation ready: two new model files, existing 5070 runtime and H3 weights.'
    Write-Host "Root: $Root; 5070 runtime: $SharedRuntime"
    & (Join-Path $App 'tools\launch_12b.ps1') -Root $Root
}
finally {
    Stop-Transcript | Out-Null
}
