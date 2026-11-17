param(
    [string]$Root = 'F:\AI\BANANAMV_27B_STUDIO',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$Root = [System.IO.Path]::GetFullPath($Root)
$app = Join-Path $Root 'App'
$runtime = Join-Path $Root 'Runtime'
$comfy = Join-Path $runtime 'ComfyUI'
$python = Join-Path $runtime 'venv\Scripts\python.exe'
$models = Join-Path $Root 'Models'
$data = Join-Path $Root 'Data'
$logs = Join-Path $Root 'Logs'
$out = Join-Path $Root 'Output'
$yaml = Join-Path $runtime 'extra_model_paths.yaml'
if (!(Test-Path -LiteralPath $python)) { throw "27B Python missing: $python. Run Install_BANANAMV_27B.cmd." }
if (!(Test-Path -LiteralPath (Join-Path $comfy 'main.py'))) { throw 'Independent ComfyUI missing; run installer.' }
# Safe one-click startup update. Never reset local edits or switch branches.
if (Get-Command git -ErrorAction SilentlyContinue) {
    $current = (& git -C $app branch --show-current 2>$null).Trim()
    $dirty = & git -C $app status --porcelain
    if ($current -eq 'experiment/rtx5070-latest-27b-lab' -and !$dirty) {
        & git -C $app pull --ff-only origin experiment/rtx5070-latest-27b-lab
        if ($LASTEXITCODE -ne 0) { Write-Warning '27B auto-update skipped: network/divergence; keeping existing working source.' }
    } else {
        Write-Warning '27B local source edits / different branch detected; no update or reset.'
    }
}
foreach ($dir in @($data,$logs,$out)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
$env:BANANA_DATA = $data
$env:BANANA_PORT = '8195'
$env:BANANA_FINISHED_VIDEOS = $out
$env:BANANA_27B_ROOT = $Root
$env:BANANA_27B_SERVER = (Join-Path $runtime 'llama.cpp\llama-server.exe')
$env:BANANA_27B_MODEL = (Join-Path $models '27B\Qwen3.5-27B-Q4_K_M.gguf')
$env:BANANA_27B_MMPROJ = (Join-Path $models '27B\mmproj-BF16.gguf')
$env:BANANA_27B_PORT = '8217'
$env:BANANA_MUSIC_PYTHON = (Join-Path $runtime 'music-venv\Scripts\python.exe')
$env:HF_HOME = (Join-Path $Root 'Cache\huggingface')
$mustHave = @(
  '27B\Qwen3.5-27B-Q4_K_M.gguf',
  '27B\mmproj-BF16.gguf',
  'H3\diffusion_models\Minimax-h3_Singularity_x_10Eros-Max_PRISM_int8.safetensors',
  'H3\text_encoders\qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors',
  'H3\vae\minimax_h3_video_vae_int8_convrot.safetensors',
  'H3\vae\minimax_h3_audio_vae_fp32.safetensors',
  'H3\loras\H3_Combat_V2.safetensors',
  'H3\loras\Motion_Repair.safetensors'
)
if (@($mustHave | Where-Object { !(Test-Path -LiteralPath (Join-Path $models $_)) }).Count -gt 0) {
    Write-Host 'Missing model file detected; downloading and repairing model inventory...'
    & $python (Join-Path $app 'tools\install_27b_models.py') --models-root $models
    if ($LASTEXITCODE -ne 0) { throw 'Model repair failed; rerun installer.' }
}
$configFile = Join-Path $data 'config.json'
$config = @{ comfy_url='http://127.0.0.1:8218'; comfy_input_dir=(Join-Path $comfy 'input');
             free_after_rewrite=$true;
             rewriter=@{ model=$env:BANANA_27B_MODEL; mmproj=$env:BANANA_27B_MMPROJ;
                         server=$env:BANANA_27B_SERVER; port=8217; gpu_layers=12;
                         context=8192; max_length=4096; temperature=0.4; top_p=0.8 } }
if (Test-Path $configFile) {
    $old = Get-Content -Raw -LiteralPath $configFile | ConvertFrom-Json
    if ($old.rewriter) {
        foreach ($key in @('gpu_layers','context','max_length','temperature','top_p')) {
            if ($null -ne $old.rewriter.$key) { $config.rewriter[$key] = $old.rewriter.$key }
        }
    }
}
[System.IO.File]::WriteAllText($configFile, ($config | ConvertTo-Json -Depth 16), (New-Object System.Text.UTF8Encoding($false)))
try {
    $nodes = Invoke-RestMethod -Uri 'http://127.0.0.1:8218/object_info' -TimeoutSec 4
} catch {
    Write-Host 'Starting independent H3 ComfyUI on 8218 ...'
    $comfyArgs = @('-u', ('"' + (Join-Path $comfy 'main.py') + '"'),
                   '--base-directory', ('"' + $comfy + '"'),
                   '--extra-model-paths-config', ('"' + $yaml + '"'),
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
    if (!$nodes.PSObject.Properties[$node]) { throw "H3 missing required node: $node. Run installer." }
}
Write-Host 'Independent H3 ComfyUI: http://127.0.0.1:8218'
Write-Host '27B Director: owned process on port 8217, launched on demand.'
Write-Host 'BANANAMV 27B: http://127.0.0.1:8195'
if (!$NoBrowser) { Start-Process 'http://127.0.0.1:8195' }
Push-Location $app
try { & $python -u -m banana_mv.server }
finally { Pop-Location }
