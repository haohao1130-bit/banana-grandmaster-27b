param([string]$Root = 'F:\AI\BANANAMV_27B_STUDIO')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Root = [System.IO.Path]::GetFullPath($Root)
if (!$Root.StartsWith('F:\',[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The 27B independent studio must be installed on F:; no other drive will be modified.'
}
if (!(Test-Path 'F:\')) { throw 'F: does not exist. Connect the F: SSD first.' }
$App = Join-Path $Root 'App'
$Runtime = Join-Path $Root 'Runtime'
$Models = Join-Path $Root 'Models'
$Logs = Join-Path $Root 'Logs'
$Data = Join-Path $Root 'Data'
$Output = Join-Path $Root 'Output'
$Cache = Join-Path $Root 'Cache'
foreach ($dir in @($Root,$Runtime,$Models,$Logs,$Data,$Output,$Cache)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
$env:HF_HOME = Join-Path $Cache 'huggingface'
$env:HF_HUB_ENABLE_HF_TRANSFER = '0'
Start-Transcript -Path (Join-Path $Logs 'install_27b.log') -Append | Out-Null
try {
    function Refresh-Path {
        $env:PATH = [Environment]::GetEnvironmentVariable('PATH','Machine')+';'+[Environment]::GetEnvironmentVariable('PATH','User')+';'+$env:PATH
    }
    function Require-Tool([string]$Name, [string]$WingetId) {
        if (Get-Command $Name -ErrorAction SilentlyContinue) { return }
        if (!(Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "Missing $Name and Windows winget. Install Windows App Installer and rerun."
        }
        Write-Host "Installing missing prerequisite: $WingetId"
        & winget install --exact --id $WingetId --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -ne 0) { throw "winget failed: $WingetId" }
        Refresh-Path
        if (!(Get-Command $Name -ErrorAction SilentlyContinue)) {
            throw "$Name was installed but not found on PATH. Restart terminal and rerun installer."
        }
    }
    Require-Tool 'git' 'Git.Git'
    Require-Tool 'ffmpeg' 'Gyan.FFmpeg'
    Require-Tool 'ffprobe' 'Gyan.FFmpeg'
    function Python312 {
        if (Get-Command py -ErrorAction SilentlyContinue) {
            $p = (& py -3.12 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -Last 1)
            if ($LASTEXITCODE -eq 0 -and $p -and (Test-Path -LiteralPath $p)) { return $p }
        }
        foreach ($candidate in @(
          (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
          (Join-Path $env:ProgramFiles 'Python312\python.exe'))) {
            if (Test-Path $candidate) { return $candidate }
        }
        return $null
    }
    $basePython = Python312
    if (!$basePython) {
        if (!(Get-Command winget -ErrorAction SilentlyContinue)) { throw 'Python 3.12 missing; Windows winget unavailable' }
        & winget install --exact --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
        if ($LASTEXITCODE -ne 0) { throw 'Could not install Python 3.12' }
        Refresh-Path
        $basePython = Python312
        if (!$basePython) { throw 'Python 3.12 installed, but cannot locate python.exe. Rerun after logging in.' }
    }
    $branch = 'experiment/rtx5070-latest-27b-lab'
    $gitUrl = 'https://github.com/haohao1130-bit/banana-grandmaster-27b.git'
    if (!(Test-Path -LiteralPath (Join-Path $App '.git'))) {
        if ((Test-Path $App) -and @(Get-ChildItem -LiteralPath $App -Force).Count) {
            throw "App exists but is not a Git checkout; refusing to overwrite: $App"
        }
        & git clone --single-branch --branch $branch $gitUrl $App
        if ($LASTEXITCODE -ne 0) { throw 'Cannot clone 27B studio branch' }
    } else {
        $remote = (& git -C $App remote get-url origin).Trim()
        if ($remote -notlike '*haohao1130-bit/banana-grandmaster-27b*') {
            throw "App checkout points at a different Git repository: $remote"
        }
        $dirty = & git -C $App status --porcelain
        if ($dirty) {
            Write-Warning 'App contains local edits; keeping installed version without pulling. Never force reset.'
        } else {
            & git -C $App fetch origin $branch
            if ($LASTEXITCODE -ne 0) { throw 'Git fetch failed' }
            $current = (& git -C $App branch --show-current).Trim()
            if ($current -ne $branch) { throw "App is on a different branch: $current. Refusing to switch automatically." }
            & git -C $App pull --ff-only origin $branch
            if ($LASTEXITCODE -ne 0) { throw 'Git branch diverged; no reset performed' }
        }
    }
    Write-Host "27B source: $((& git -C $App log -1 --oneline))"
    # The director reads this required guide from App/guides at runtime.
    # Gitignore already excludes the fetched file, preserving clean future Git pulls.
    $guideDir = Join-Path $App 'guides'
    $guide = Join-Path $guideDir 'VIDEO_PROMPT_WRITING_GUIDE_ref_en.md'
    New-Item -ItemType Directory -Force -Path $guideDir | Out-Null
    if (!(Test-Path $guide) -or (Get-Item $guide).Length -lt 1000) {
        Invoke-WebRequest -UseBasicParsing -Uri 'https://huggingface.co/MiniMaxAI/MiniMax-H3/resolve/main/docs/VIDEO_PROMPT_WRITING_GUIDE_ref_en.md' -OutFile $guide
        if ((Get-Item $guide).Length -lt 1000) { throw 'H3 official prompt guide is incomplete' }
    }
    $python = Join-Path $Runtime 'venv\Scripts\python.exe'
    if (!(Test-Path $python)) {
        & $basePython -m venv (Join-Path $Runtime 'venv')
        if ($LASTEXITCODE -ne 0) { throw 'Could not create independent venv' }
    }
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed' }
    # Install CUDA13 runtime in our isolated environment; do not touch the other two studios.
    & $python -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu130
    if ($LASTEXITCODE -ne 0) { throw 'CUDA 13 PyTorch install failed' }
    $comfy = Join-Path $Runtime 'ComfyUI'
    if (!(Test-Path -LiteralPath (Join-Path $comfy '.git'))) {
        & git clone https://github.com/Comfy-Org/ComfyUI.git $comfy
        if ($LASTEXITCODE -ne 0) { throw 'ComfyUI clone failed' }
    }
    # Reuse the tested H3 source revision used in the original Banana runtime.
    $comfyPin = '56f179f6c50dad0c4c860ae4da427415c8e86415'
    if (!(Test-Path (Join-Path $comfy 'main.py'))) { throw 'ComfyUI checkout missing main.py' }
    if (!(& git -C $comfy status --porcelain)) {
        & git -C $comfy fetch --depth 1 origin $comfyPin
        if ($LASTEXITCODE -ne 0) { throw 'ComfyUI pin download failed' }
        & git -C $comfy checkout --detach $comfyPin
        if ($LASTEXITCODE -ne 0) { throw 'ComfyUI pin checkout failed' }
    } else {
        Write-Warning 'ComfyUI local changes detected, retaining original without reset'
    }
    & $python -m pip install -r (Join-Path $comfy 'requirements.txt') huggingface_hub hf_xet Pillow numpy
    if ($LASTEXITCODE -ne 0) { throw 'ComfyUI Python dependencies failed' }
    $node = Join-Path $comfy 'custom_nodes\minimax-h3-audio-T8'
    if (!(Test-Path (Join-Path $node '.git'))) {
        & git clone https://github.com/T8mars/comfyui-minimax-h3-audio-T8.git $node
        if ($LASTEXITCODE -ne 0) { throw 'H3 T8 node clone failed' }
    }
    $nodePin = '3a23f333537d9a715aad7ce79af8d9ec891d9ad8'
    if (!(& git -C $node status --porcelain)) {
        & git -C $node fetch --depth 1 origin $nodePin
        if ($LASTEXITCODE -ne 0) { throw 'T8 source pin fetch failed' }
        & git -C $node checkout --detach $nodePin
        if ($LASTEXITCODE -ne 0) { throw 'T8 checkout failed' }
    }
    $nodeReq = Join-Path $node 'requirements.txt'
    if (Test-Path $nodeReq) {
        & $python -m pip install -r $nodeReq
        if ($LASTEXITCODE -ne 0) { throw 'H3 T8 dependencies failed' }
    }
    $yaml = Join-Path $Runtime 'extra_model_paths.yaml'
    $modelPath = (Join-Path $Models 'H3').Replace('\','/')
    $yamlText = "banana27b:`n  base_path: `"$modelPath`"`n  diffusion_models: diffusion_models`n  text_encoders: text_encoders`n  vae: vae`n  loras: loras`n"
    [IO.File]::WriteAllText($yaml, $yamlText, (New-Object System.Text.UTF8Encoding($false)))
    # Windows PowerShell 5.1 does not auto-load ZipFile; verify the assembly
    # before touching any cached CUDA13 archive or downloading its replacement.
    try {
        Add-Type -AssemblyName 'System.IO.Compression.FileSystem' -ErrorAction Stop
    } catch {
        Add-Type -AssemblyName 'System.IO.Compression.ZipFile' -ErrorAction Stop
    }
    if (-not ('System.IO.Compression.ZipFile' -as [type])) {
        throw 'The .NET ZIP reader could not be loaded. Install/repair .NET Framework and rerun.'
    }
    $llamaFolder = Join-Path $Runtime 'llama.cpp'
    $llamaExe = Join-Path $llamaFolder 'llama-server.exe'
    if (!(Test-Path $llamaExe)) {
        Write-Host 'Downloading official llama.cpp CUDA13 Windows release and matching runtime DLLs...'
        $headers = @{ 'User-Agent' = 'BANANAMV-27B-OneClick'; 'Accept' = 'application/vnd.github+json' }
        $releases = Invoke-RestMethod -Uri 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=12' -Headers $headers
        $chosen = $null
        foreach ($release in $releases) {
            $main = @($release.assets | Where-Object { $_.name -match '^llama-.*-bin-win-cuda-13(\.\d+)?-x64\.zip$' } | Select-Object -First 1)
            $cudart = @($release.assets | Where-Object { $_.name -match '^cudart-llama(?:-.*)?-bin-win-cuda-13(\.\d+)?-x64\.zip$' } | Select-Object -First 1)
            if ($main.Count -gt 0 -and $cudart.Count -gt 0) {
                $chosen = @{ main=$main[0]; runtime=$cudart[0]; tag=$release.tag_name }
                break
            }
        }
        if (!$chosen) { throw 'No complete Windows CUDA13 llama.cpp release pair found; do not substitute CPU binaries.' }
        New-Item -ItemType Directory -Force -Path $llamaFolder | Out-Null
        foreach ($item in @($chosen.main,$chosen.runtime)) {
            $zip = Join-Path $Runtime $item.name
            $validZip = $false
            if (Test-Path $zip) {
                try {
                    $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
                    try { $validZip = ($archive.Entries.Count -gt 0) }
                    finally { $archive.Dispose() }
                } catch { $validZip = $false }
            }
            if (!$validZip) {
                # Never retain an interrupted/incomplete download as a valid cached ZIP.
                Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
                $partial = "$zip.partial"
                Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
                Invoke-WebRequest -UseBasicParsing -Uri $item.browser_download_url -OutFile $partial -Headers @{ 'User-Agent'='BANANAMV-27B-OneClick' }
                $archive = [System.IO.Compression.ZipFile]::OpenRead($partial)
                try { if ($archive.Entries.Count -eq 0) { throw 'llama.cpp archive is empty' } }
                finally { $archive.Dispose() }
                Move-Item -LiteralPath $partial -Destination $zip -Force
            }
            $expanded = Join-Path $Runtime ('unzip_'+$item.name.Replace('.zip',''))
            New-Item -ItemType Directory -Force -Path $expanded | Out-Null
            Expand-Archive -LiteralPath $zip -DestinationPath $expanded -Force
            foreach ($file in @(Get-ChildItem -Path $expanded -Recurse -File)) {
                Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $llamaFolder $file.Name) -Force
            }
            Remove-Item -LiteralPath $expanded -Recurse -Force
        }
        if (!(Test-Path $llamaExe)) { throw 'Downloaded llama.cpp archive does not contain llama-server.exe' }
    }
    # CPU music parser remains isolated from the GPU video environment.
    $musicPython = Join-Path $Runtime 'music-venv\Scripts\python.exe'
    if (!(Test-Path $musicPython)) {
        & $basePython -m venv (Join-Path $Runtime 'music-venv')
        if ($LASTEXITCODE -ne 0) { throw 'Music venv create failed' }
    }
    & $musicPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Music pip setup failed' }
    & $musicPython -m pip install torch --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'Music CPU torch install failed' }
    & $musicPython -m pip install 'all-in-one-infer @ git+https://github.com/openmirlab/all-in-one-infer.git@566f96c3f007c783ab5eb6db0123bf3335af8f31'
    if ($LASTEXITCODE -ne 0) { throw 'Music analysis dependency install failed' }
    Write-Host 'Downloading all eight required model files (resumable, no 9B)...'
    & $python (Join-Path $App 'tools\install_27b_models.py') --models-root $Models
    if ($LASTEXITCODE -ne 0) { throw 'Model download did not complete; rerun installer to resume' }
    # Run a real file instead of inline python -c: PowerShell 5.1 strips nested
    # double quotes, turning print("Torch") into print(Torch) and causing NameError.
    Write-Host 'Checking isolated RTX 5070 CUDA 13 PyTorch runtime...'
    & $python (Join-Path $App 'tools\check_cuda27b.py')
    if ($LASTEXITCODE -ne 0) { throw '27B CUDA13 smoke test failed; inspect the Python output above before changing drivers.' }
    $launchCmd = Join-Path $Root 'Launch_BANANAMV_27B.cmd'
    $launchText = "@echo off`r`nchcp 65001 >nul`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -File `"%~dp0App\tools\launch_27b.ps1`"`r`nif errorlevel 1 pause`r`n"
    [IO.File]::WriteAllText($launchCmd,$launchText,(New-Object System.Text.UTF8Encoding($false)))
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'BANANAMV 27B.lnk'))
        $shortcut.TargetPath = $launchCmd
        $shortcut.WorkingDirectory = $Root
        $shortcut.Description = 'BANANAMV 27B Q4_K_M independent F-drive studio'
        $shortcut.Save()
    } catch { Write-Warning 'Desktop shortcut failed; use Launch_BANANAMV_27B.cmd' }
    Write-Host '✅ BANANAMV 27B standalone installation ready.'
    Write-Host "Root: $Root"
    Write-Host 'Frontend: http://127.0.0.1:8193'
    Write-Host 'Default: 720P / 10 seconds, independent project and model storage'
    & (Join-Path $App 'tools\launch_27b.ps1') -Root $Root
} finally {
    Stop-Transcript | Out-Null
}
