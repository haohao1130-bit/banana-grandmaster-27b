param([string]$Root = 'F:\BANANAMV_12B_STUDIO')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = [IO.Path]::GetFullPath($Root)
$Original = 'F:\AI'
$Legacy27B = 'F:\AI\BANANAMV_27B_STUDIO'
if (!$Root.StartsWith('F:\', [StringComparison]::OrdinalIgnoreCase) -or
    $Root -ieq 'F:\' -or $Root.StartsWith('F:\AI\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '12B must be installed outside F:\AI. Original MV/FILM files must not be modified.'
}
$App = Join-Path $Root 'App'
$Runtime = Join-Path $Root 'Runtime'
$Models = Join-Path $Root 'Models'
$Logs = Join-Path $Root 'Logs'
foreach ($dir in @($Root,$App,$Runtime,$Models,$Logs,(Join-Path $Root 'Cache'),(Join-Path $Root 'Data'),(Join-Path $Root 'Output'))) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$env:HF_HOME = Join-Path $Root 'Cache\huggingface'
$env:HF_HUB_ENABLE_HF_TRANSFER = '0'
Start-Transcript -Path (Join-Path $Logs 'install_12b.log') -Append | Out-Null
try {
    if (!(Get-Command git -ErrorAction SilentlyContinue)) { throw 'Missing Git.' }
    $Python = Join-Path $Original 'Banana9B-cu130\Scripts\python.exe'
    $MusicPython = Join-Path $Original 'BananaMusicVenv\Scripts\python.exe'
    $Comfy = Join-Path $Original 'ComfyUI\App'
    $Llama = Join-Path $Legacy27B 'Runtime\llama.cpp\llama-server.exe'
    foreach ($file in @($Python,$MusicPython,(Join-Path $Comfy 'main.py'),$Llama)) {
        if (!(Test-Path -LiteralPath $file -PathType Leaf)) {
            throw "Missing preinstalled RTX 5070 component: $file. No packages were installed."
        }
    }
    $deviceInfo = (& $Llama --list-devices 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $deviceInfo -notmatch 'CUDA0:') {
        throw "Existing llama.cpp is not CUDA-enabled: $deviceInfo"
    }
    Write-Host 'Reusing original BANANAMV/BANANAFILM Python, music tools and ComfyUI.'
    Write-Host ($deviceInfo.Trim())

    # Try original shared F:\AI\Models first. The legacy 27B H3 model set
    # is an existing-file fallback, never an additional download or copy.
    $required = @{
        diffusion_models = 'Minimax-h3_Singularity_x_10Eros-Max_PRISM_int8.safetensors'
        text_encoders = 'qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors'
        vae_video = 'minimax_h3_video_vae_int8_convrot.safetensors'
        vae_audio = 'minimax_h3_audio_vae_fp32.safetensors'
        lora_combat = 'H3_Combat_V2.safetensors'
        lora_repair = 'Motion_Repair.safetensors'
    }
    $resolved = @{}
    $searchRoots = @('F:\AI\Models',(Join-Path $Legacy27B 'Models\H3'))
    foreach ($entry in $required.GetEnumerator()) {
        $found = $null
        foreach ($searchRoot in $searchRoots) {
            if (!(Test-Path -LiteralPath $searchRoot)) { continue }
            $found = Get-ChildItem -LiteralPath $searchRoot -Filter $entry.Value -File -Recurse -ErrorAction SilentlyContinue |
                Where-Object { $_.Length -gt 0 } | Select-Object -First 1
            if ($found) { break }
        }
        if (!$found) {
            throw "Missing existing H3 model: $($entry.Value). No H3 files will be downloaded."
        }
        $resolved[$entry.Key] = $found.FullName
        Write-Host "Shared H3: $($found.FullName)"
    }

    function RelativeToF([string]$file) {
        return (Split-Path -Parent $file).Substring(3).Replace('\','/')
    }
    $yaml = @(
        'banana12b_h3:'
        '  base_path: "F:/"'
        "  diffusion_models: '$(RelativeToF $resolved.diffusion_models)'"
        "  text_encoders: '$(RelativeToF $resolved.text_encoders)'"
        "  vae: '$(RelativeToF $resolved.vae_video)'"
        "  loras: '$(RelativeToF $resolved.lora_combat)'"
    ) -join [Environment]::NewLine
    foreach ($pair in @('vae_audio|vae','lora_repair|loras')) {
        $entry = $pair.Split('|')
        $name = $entry[0]
        $category = $entry[1]
        $yaml += [Environment]::NewLine + 'banana12b_' + $name + ':' +
            [Environment]::NewLine + '  base_path: "F:/"' +
            [Environment]::NewLine + '  ' + $category + ": '$(RelativeToF $resolved[$name])'"
    }
    [IO.File]::WriteAllText((Join-Path $Runtime 'extra_model_paths.yaml'),$yaml,(New-Object Text.UTF8Encoding($false)))

    # FFmpeg is already installed; never ask winget to reinstall/upgrade it.
    $ffmpegBin = $null
    $cmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        $dir = Split-Path -Parent $cmd.Source
        if (Test-Path -LiteralPath (Join-Path $dir 'ffprobe.exe')) { $ffmpegBin = $dir }
    }
    if (!$ffmpegBin) {
        $roots = @(
            'F:\AI\Tools',
            'F:\AI\ComfyUI',
            (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),
            (Join-Path $env:ProgramFiles 'WinGet\Packages'),
            'C:\ffmpeg'
        )
        foreach ($candidate in $roots) {
            if (!(Test-Path -LiteralPath $candidate)) { continue }
            $hit = Get-ChildItem -LiteralPath $candidate -Recurse -Filter 'ffmpeg.exe' -File -ErrorAction SilentlyContinue |
                Where-Object { Test-Path -LiteralPath (Join-Path $_.DirectoryName 'ffprobe.exe') } |
                Select-Object -First 1
            if ($hit) { $ffmpegBin = $hit.DirectoryName; break }
        }
    }
    if (!$ffmpegBin) {
        throw 'Existing FFmpeg/ffprobe could not be found; no FFmpeg download or winget changes attempted.'
    }
    [IO.File]::WriteAllText((Join-Path $Runtime 'ffmpeg_path.txt'),$ffmpegBin,(New-Object Text.UTF8Encoding($false)))

    $branch = 'experiment/rtx5070-gemma3-12b'
    $gitUrl = 'https://github.com/haohao1130-bit/banana-grandmaster-27b.git'
    if (!(Test-Path -LiteralPath (Join-Path $App '.git'))) {
        if (@(Get-ChildItem -LiteralPath $App -Force).Count -gt 0) { throw "App is not empty: $App" }
        & git clone --single-branch --branch $branch $gitUrl $App
        if ($LASTEXITCODE -ne 0) { throw 'Cannot clone 12B branch.' }
    } else {
        $remote = (& git -C $App remote get-url origin).Trim()
        if ($remote -notlike '*haohao1130-bit/banana-grandmaster-27b*') {
            throw "Unexpected Git remote: $remote"
        }
        if ((& git -C $App branch --show-current).Trim() -ne $branch) {
            throw 'Existing 12B branch differs. No automatic switching was attempted.'
        }
        if (!(& git -C $App status --porcelain)) {
            & git -C $App pull --ff-only origin $branch
            if ($LASTEXITCODE -ne 0) { throw 'Git fast-forward update failed.' }
        } else { Write-Warning 'Local 12B changes; skipping update.' }
    }
    $guide = Join-Path $App 'guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'
    if (!(Test-Path -LiteralPath $guide)) {
        $source = Join-Path $Legacy27B 'App\guides\VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'
        if (!(Test-Path -LiteralPath $source)) { throw "Missing original H3 guide: $source" }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $guide) | Out-Null
        Copy-Item -LiteralPath $source -Destination $guide
    }

    $downloadPython = $Python
    & $downloadPython -c 'import huggingface_hub'
    if ($LASTEXITCODE -ne 0) {
        $downloadPython = Join-Path $Legacy27B 'Runtime\venv\Scripts\python.exe'
        & $downloadPython -c 'import huggingface_hub'
        if ($LASTEXITCODE -ne 0) { throw 'No installed Python has huggingface_hub. Existing environments were not changed.' }
    }
    Write-Host 'Downloading ONLY Gemma 12B Q5 and matching F16 mmproj...'
    & $downloadPython (Join-Path $App 'tools\install_12b_models.py') --models-root $Models
    if ($LASTEXITCODE -ne 0) { throw 'Gemma model download incomplete. Rerun one-click installer to resume.' }

    $settings = @{
        python=$Python; music_python=$MusicPython; comfy=$Comfy
        llama=$Llama; ffmpeg_bin=$ffmpegBin
    } | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $Runtime 'shared_5070.json'),$settings,(New-Object Text.UTF8Encoding($false)))
    $cmdPath = Join-Path $Root 'Launch_BANANAMV_12B.cmd'
    $cmdText = "@echo off" + [Environment]::NewLine +
        "chcp 65001 >nul" + [Environment]::NewLine +
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0App\tools\launch_12b.ps1"' +
        [Environment]::NewLine + 'if errorlevel 1 pause' + [Environment]::NewLine
    [IO.File]::WriteAllText($cmdPath,$cmdText,(New-Object Text.UTF8Encoding($false)))
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'BANANAMV 12B.lnk'))
        $shortcut.TargetPath=$cmdPath
        $shortcut.WorkingDirectory=$Root
        $shortcut.Description='Gemma 3 12B using existing BANANAMV/BANANAFILM 5070 CUDA13 and ComfyUI'
        $shortcut.Save()
    } catch { Write-Warning 'Desktop shortcut failed. The CMD launcher was created.' }
    Write-Host '12B thin install ready; original MV/FILM resources are unchanged.'
    & (Join-Path $App 'tools\launch_12b.ps1') -Root $Root
} finally {
    Stop-Transcript | Out-Null
}
