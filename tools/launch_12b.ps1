param(
    [string]$Root = 'F:\BANANAMV_12B_STUDIO',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath($Root)
$app = Join-Path $Root 'App'
$runtime = Join-Path $Root 'Runtime'
$sharedFile = Join-Path $runtime 'shared_5070.json'
if (!(Test-Path -LiteralPath $sharedFile)) {
    throw '12B shared 5070 runtime inventory missing. Run Install_BANANAMV_12B.cmd.'
}
$shared = Get-Content -Raw -LiteralPath $sharedFile | ConvertFrom-Json
$comfy = [string]$shared.comfy
$python = [string]$shared.python
$musicPython = [string]$shared.music_python
$llama = [string]$shared.llama
$ffmpegBin = [string]$shared.ffmpeg_bin
$models = Join-Path $Root 'Models'
$data = Join-Path $Root 'Data'
$logs = Join-Path $Root 'Logs'
$out = Join-Path $Root 'Output'
$inputDir = Join-Path $runtime 'ComfyInput'
$tempDir = Join-Path $runtime 'ComfyTemp'
$yaml = Join-Path $runtime 'extra_model_paths.yaml'
foreach ($required in @($python,$musicPython,$llama,(Join-Path $comfy 'main.py'),
                         (Join-Path $ffmpegBin 'ffmpeg.exe'),(Join-Path $ffmpegBin 'ffprobe.exe'),$yaml)) {
    if (!(Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Shared 5070 dependency was moved or removed: $required"
    }
}
$env:PATH = "$ffmpegBin;$env:PATH"
# The phone/Tailscale frontend is fixed to 8193, matching existing 5070 URLs.
# Do not terminate the original MV or FILM if they currently own this listener.
$portCheck = New-Object System.Net.Sockets.TcpClient
try {
    $async = $portCheck.BeginConnect('127.0.0.1',8193,$null,$null)
    if ($async.AsyncWaitHandle.WaitOne(800,$false)) {
        try {
            $portCheck.EndConnect($async)
            throw 'Port 8193 is already in use. Close the original BANANAMV or BANANAFILM backend before launching 12B. Existing services were not stopped.'
        } catch [System.Net.Sockets.SocketException] { }
    }
} finally {
    $portCheck.Close()
}
if (!(Test-Path -LiteralPath $python)) { throw "12B Python missing: $python. Run Install_BANANAMV_12B.cmd." }
if (!(Test-Path -LiteralPath (Join-Path $comfy 'main.py'))) { throw 'Shared 5070 ComfyUI missing; rerun installer.' }
# Safe one-click startup update. Never reset local edits or switch branches.
# If a new launcher is downloaded, reload the new script before any service
# starts; otherwise PowerShell would continue running its old in-memory version.
$beforeUpdate = ''
if (Get-Command git -ErrorAction SilentlyContinue) {
    $beforeUpdate = (& git -C $app rev-parse HEAD 2>$null | Select-Object -Last 1)
    if (!$beforeUpdate) { $beforeUpdate = '' }
}
if (Get-Command git -ErrorAction SilentlyContinue) {
    $current = (& git -C $app branch --show-current 2>$null).Trim()
    $dirty = & git -C $app status --porcelain
    if ($current -eq 'experiment/rtx5070-gemma3-12b' -and !$dirty) {
        & git -C $app pull --ff-only origin experiment/rtx5070-gemma3-12b
        if ($LASTEXITCODE -ne 0) { Write-Warning '12B auto-update skipped: network/divergence; keeping existing working source.' }
    } else {
        Write-Warning '12B local source edits / different branch detected; no update or reset.'
    }
}
$afterUpdate = ''
if (Get-Command git -ErrorAction SilentlyContinue) {
    $afterUpdate = (& git -C $app rev-parse HEAD 2>$null | Select-Object -Last 1)
    if (!$afterUpdate) { $afterUpdate = '' }
}
if ($beforeUpdate -and $afterUpdate -and $beforeUpdate -ne $afterUpdate -and
    $env:BANANA_12B_LAUNCH_RELOADED -ne '1') {
    Write-Host '12B updated; reloading the new launcher before starting services.'
    $env:BANANA_12B_LAUNCH_RELOADED = '1'
    & (Join-Path $app 'tools\launch_12b.ps1') -Root $Root -NoBrowser:$NoBrowser
    exit $LASTEXITCODE
}
foreach ($dir in @($data,$logs,$out)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$env:BANANA_DATA = $data
$env:BANANA_PORT = '8193'
$env:BANANA_12B_STANDALONE = '1'
# Stability isolation: disable web-triggered restart, keeping original direct backend.
# The supervisor utility remains in the repo but is NOT launched.
$env:BANANA_SUPERVISED_RESTART = '0'
$env:BANANA_FINISHED_VIDEOS = $out
$env:BANANA_12B_ROOT = $Root
$env:BANANA_12B_SERVER = $llama
$env:BANANA_12B_MODEL = (Join-Path $models '12B\google_gemma-3-12b-it-Q5_K_M.gguf')
$env:BANANA_12B_MMPROJ = (Join-Path $models '12B\mmproj-google_gemma-3-12b-it-f16.gguf')
$env:BANANA_12B_PORT = '8217'
$env:BANANA_MUSIC_PYTHON = $musicPython
$env:HF_HOME = (Join-Path $Root 'Cache\huggingface')
$mustHave = @(
  '12B\google_gemma-3-12b-it-Q5_K_M.gguf',
  '12B\mmproj-google_gemma-3-12b-it-f16.gguf'
)
if (@($mustHave | Where-Object { !(Test-Path -LiteralPath (Join-Path $models $_)) }).Count -gt 0) {
    Write-Host 'Missing model file detected; downloading and repairing model inventory...'
    & $python (Join-Path $app 'tools\install_12b_models.py') --models-root $models
    if ($LASTEXITCODE -ne 0) { throw 'Model repair failed; rerun installer.' }
}
# Reuse the working RTX5070 9B T8 plugin path, without copying or reinstalling it.
$existingNodeHomes = @(
    (Join-Path $env:USERPROFILE 'Documents\ComfyUI\custom_nodes'),
    (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'ComfyUI\custom_nodes'),
    (Join-Path (Split-Path -Parent $comfy) 'Data\custom_nodes'),
    (Join-Path $comfy 'custom_nodes')
)
$existing9bNodes = $null
foreach ($candidate in ($existingNodeHomes | Select-Object -Unique)) {
    if (!(Test-Path -LiteralPath $candidate -PathType Container)) { continue }
    $t8 = Get-ChildItem -LiteralPath $candidate -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '(?i)^minimax[-_]h3[-_]audio[-_]t8$' } |
        Select-Object -First 1
    if ($t8) { $existing9bNodes = $candidate; break }
}
if (!$existing9bNodes) {
    throw 'Existing 9B H3 T8 custom node source not found; refusing to download or modify the original 9B install.'
}
$blockBegin = '# BANANA12B_EXISTING_9B_NODES_BEGIN'
$blockEnd = '# BANANA12B_EXISTING_9B_NODES_END'
$nodeHomeYaml = $existing9bNodes.Replace('\','/').Replace("'","''")
$nodeBlock = $blockBegin + [Environment]::NewLine +
    'banana12b_existing_9b_nodes:' + [Environment]::NewLine +
    "  base_path: '$nodeHomeYaml'" + [Environment]::NewLine +
    '  custom_nodes: .' + [Environment]::NewLine +
    $blockEnd + [Environment]::NewLine
$yamlBefore = [IO.File]::ReadAllText($yaml)
$yamlCore = [regex]::Replace($yamlBefore,
    '(?ms)^# BANANA12B_EXISTING_9B_NODES_BEGIN\r?\n.*?^# BANANA12B_EXISTING_9B_NODES_END\r?\n?', '')
$yamlAfter = $yamlCore.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $nodeBlock
$nodePathChanged = ($yamlBefore -cne $yamlAfter)
if ($nodePathChanged) {
    [IO.File]::WriteAllText($yaml,$yamlAfter,(New-Object System.Text.UTF8Encoding($false)))
}
Write-Host "12B reuses 9B H3 custom nodes: $existing9bNodes"

$configFile = Join-Path $data 'config.json'
$config = @{ comfy_url='http://127.0.0.1:8218'; comfy_input_dir=$inputDir;
             free_after_rewrite=$true;
             rewriter=@{ model=$env:BANANA_12B_MODEL; mmproj=$env:BANANA_12B_MMPROJ;
                         server=$env:BANANA_12B_SERVER; port=8217; gpu_layers=99;
                         context=16384; max_length=4096; temperature=0.4; top_p=0.8 } }
if (Test-Path $configFile) {
    $old = Get-Content -Raw -LiteralPath $configFile | ConvertFrom-Json
    if ($old.rewriter) {
        foreach ($key in @('gpu_layers','context','max_length','temperature','top_p')) {
            if ($null -ne $old.rewriter.$key) {
                # Dedicated 12B installation: keep intentional local tuning.
                $config.rewriter[$key] = $old.rewriter.$key
            }
        }
    }
    # Undo the overly broad 8192-token default introduced by the previous update.
    # Leave any other explicitly tuned output value unchanged.
    if ([int]$config.rewriter.max_length -eq 8192) {
        $config.rewriter.max_length = 4096
    }
}
[System.IO.File]::WriteAllText($configFile, ($config | ConvertTo-Json -Depth 16), (New-Object System.Text.UTF8Encoding($false)))
# Do not adopt the old 27B/9B ComfyUI that happens to be listening on 8218.
# Such a server has a different input folder and model search path.
$existingComfy = Get-NetTCPConnection -LocalPort 8218 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existingComfy) {
    $ownerPid = [int]$existingComfy.OwningProcess
    $ownerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $ownerPid" -ErrorAction SilentlyContinue
    if (!$ownerProcess -or !$ownerProcess.CommandLine -or
        $ownerProcess.CommandLine.IndexOf($comfy, [System.StringComparison]::OrdinalIgnoreCase) -lt 0 -or
        $ownerProcess.CommandLine.IndexOf($Root, [System.StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Port 8218 belongs to a different ComfyUI/process (PID $ownerPid). Close the old studio first; nothing was terminated."
    }
}
# A failed earlier boot may leave 8218 alive without T8. Restart ONLY our own idle 12B process.
if ($existingComfy -and $nodePathChanged) {
    try { $queue = Invoke-RestMethod -Uri 'http://127.0.0.1:8218/queue' -TimeoutSec 5 }
    catch { throw 'Cannot confirm the 12B ComfyUI queue is idle; no process was stopped.' }
    if (($queue.queue_running -and @($queue.queue_running).Count -gt 0) -or
        ($queue.queue_pending -and @($queue.queue_pending).Count -gt 0)) {
        throw '12B ComfyUI has active/pending work; refusing to restart it.'
    }
    Write-Host "Restarting verified idle 12B ComfyUI PID $ownerPid to register 9B T8."
    Stop-Process -Id $ownerPid -ErrorAction Stop
    $stopDeadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $stopDeadline -and
           (Get-NetTCPConnection -LocalPort 8218 -State Listen -ErrorAction SilentlyContinue)) {
        Start-Sleep -Seconds 1
    }
    if (Get-NetTCPConnection -LocalPort 8218 -State Listen -ErrorAction SilentlyContinue) {
        throw '12B ComfyUI did not release 8218; no other process was stopped.'
    }
}
try {
    $nodes = Invoke-RestMethod -Uri 'http://127.0.0.1:8218/object_info' -TimeoutSec 4
} catch {
    Write-Host 'Starting independent H3 ComfyUI on 8218 ...'
    foreach ($folder in @($inputDir,$tempDir,$out)) { New-Item -ItemType Directory -Force -Path $folder | Out-Null }
    $comfyArgs = @('-u', ('"' + (Join-Path $comfy 'main.py') + '"'),
                   '--base-directory', ('"' + $comfy + '"'),
                   '--extra-model-paths-config', ('"' + $yaml + '"'),
                   '--input-directory', ('"' + $inputDir + '"'),
                   '--output-directory', ('"' + $out + '"'),
                   '--temp-directory', ('"' + $tempDir + '"'),
                   '--listen','127.0.0.1','--port','8218','--lowvram','--preview-method','none')
    $proc = Start-Process -FilePath $python -ArgumentList $comfyArgs -WorkingDirectory $comfy -PassThru -RedirectStandardOutput (Join-Path $logs 'comfy.stdout.log') -RedirectStandardError (Join-Path $logs 'comfy.stderr.log')
    $deadline = (Get-Date).AddMinutes(5)
    $nodes = $null
    while (!$nodes -and (Get-Date) -lt $deadline) {
        if ($proc.HasExited) { throw 'ComfyUI exited unexpectedly; inspect Logs/comfy.stderr.log' }
        Start-Sleep 3
        try { $nodes = Invoke-RestMethod -Uri 'http://127.0.0.1:8218/object_info' -TimeoutSec 3 }
        catch { }
    }
}
if (!$nodes) { throw 'Independent ComfyUI did not start; see Logs.' }
foreach ($node in @('MiniMaxH3AudioConditioningT8','CLIPLoader','UNETLoader','ModelAttentionBackend')) {
    if (!$nodes.PSObject.Properties[$node]) { throw "H3 node unavailable: $node. Inspect Logs/comfy.stderr.log; do not redownload H3 models." }
}
Write-Host 'Shared original 5070 ComfyUI code, 12B listener: http://127.0.0.1:8218'
Write-Host '12B Director: owned process on port 8217, launched on demand.'
Write-Host 'BANANAMV 12B: http://127.0.0.1:8193'
if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8193' }
# Restore known-working 12B startup (same as first successful director shot).
# Do not supervise, terminate, or restart this server from a second process.
Write-Host '12B startup: direct backend (restart supervisor disabled for stability test).'
Push-Location $app
try { & $python -u -m banana_mv.server }
finally { Pop-Location }
