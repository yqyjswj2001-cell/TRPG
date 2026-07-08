# split_data.ps1 — 将超大数据文件按品阶(+类别)拆分为小文件
# 输出到 data/techniques/ 和 data/items/ 子目录

$ErrorActionPreference = "Stop"
$base = "E:\AIproject\ArstBot\astrbot_plugin_donghuang\data"

# ===== 1. 拆分 techniques_100k.json =====
Write-Host "=== Splitting techniques_100k.json ==="
$src = "$base\techniques_100k.json"
$outDir = "$base\techniques"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

# 先按 tier+category 建立写句柄
$writers = @{}
$total = 0
$reader = [System.IO.StreamReader]::new($src, [System.Text.Encoding]::UTF8)
while (($line = $reader.ReadLine()) -ne $null) {
    $s = $line.Trim()
    if ($s.Length -eq 0) { continue }
    try {
        $t = $s | ConvertFrom-Json
        $tier = $t.tier; $cat = $t.category
        $key = "${tier}_${cat}"
        if (-not $writers.ContainsKey($key)) {
            $fpath = "$outDir\${key}.jsonl"
            $writers[$key] = [System.IO.StreamWriter]::new($fpath, $false, [System.Text.Encoding]::UTF8)
        }
        $writers[$key].WriteLine($s)
        $total++
    } catch { }
}
$reader.Close()
# 关闭所有写句柄
foreach ($w in $writers.Values) { $w.Close() }
Write-Host "  Total techniques split: $total entries -> $($writers.Count) files"
$writers.Keys | Sort-Object | ForEach-Object { 
    $f = Get-Item "$outDir\$_.jsonl"
    Write-Host "    $_ : $($f.Length / 1KB -as [int]) KB"
}

# ===== 2. 拆分 materials_200k.jsonl =====
Write-Host "`n=== Splitting materials_200k.jsonl ==="
$src = "$base\materials_200k.jsonl"
$outDir = "$base\items"
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$writers = @{}
$total = 0
$reader = [System.IO.StreamReader]::new($src, [System.Text.Encoding]::UTF8)
while (($line = $reader.ReadLine()) -ne $null) {
    $s = $line.Trim()
    if ($s.Length -eq 0) { continue }
    try {
        $t = $s | ConvertFrom-Json
        $tier = $t.tier
        if (-not $writers.ContainsKey($tier)) {
            $fpath = "$outDir\materials_${tier}.jsonl"
            $writers[$tier] = [System.IO.StreamWriter]::new($fpath, $false, [System.Text.Encoding]::UTF8)
        }
        $writers[$tier].WriteLine($s)
        $total++
    } catch { }
}
$reader.Close()
foreach ($w in $writers.Values) { $w.Close() }
Write-Host "  Total materials split: $total entries -> $($writers.Count) files"
$writers.Keys | Sort-Object | ForEach-Object { 
    $f = Get-Item "$outDir\materials_$_.jsonl"
    Write-Host "    $_ : $($f.Length / 1KB -as [int]) KB"
}

# ===== 3. 拆分 weapons_tier.jsonl =====
Write-Host "`n=== Splitting weapons_tier.jsonl ==="
$src = "$base\weapons_tier.jsonl"
$writers = @{}; $total = 0
$reader = [System.IO.StreamReader]::new($src, [System.Text.Encoding]::UTF8)
while (($line = $reader.ReadLine()) -ne $null) {
    $s = $line.Trim()
    if ($s.Length -eq 0) { continue }
    try {
        $t = $s | ConvertFrom-Json
        $tier = $t.power_tier
        if (-not $writers.ContainsKey($tier)) {
            $fpath = "$outDir\weapons_${tier}.jsonl"
            $writers[$tier] = [System.IO.StreamWriter]::new($fpath, $false, [System.Text.Encoding]::UTF8)
        }
        $writers[$tier].WriteLine($s)
        $total++
    } catch { }
}
$reader.Close()
foreach ($w in $writers.Values) { $w.Close() }
Write-Host "  Total weapons split: $total entries -> $($writers.Count) files"
$writers.Keys | Sort-Object | ForEach-Object { 
    $f = Get-Item "$outDir\weapons_$_.jsonl"
    Write-Host "    $_ : $($f.Length / 1KB -as [int]) KB"
}

# ===== 4. 拆分 pills_tier.jsonl =====
Write-Host "`n=== Splitting pills_tier.jsonl ==="
$src = "$base\pills_tier.jsonl"
$writers = @{}; $total = 0
$reader = [System.IO.StreamReader]::new($src, [System.Text.Encoding]::UTF8)
while (($line = $reader.ReadLine()) -ne $null) {
    $s = $line.Trim()
    if ($s.Length -eq 0) { continue }
    try {
        $t = $s | ConvertFrom-Json
        $tier = $t.power_tier
        if (-not $writers.ContainsKey($tier)) {
            $fpath = "$outDir\pills_${tier}.jsonl"
            $writers[$tier] = [System.IO.StreamWriter]::new($fpath, $false, [System.Text.Encoding]::UTF8)
        }
        $writers[$tier].WriteLine($s)
        $total++
    } catch { }
}
$reader.Close()
foreach ($w in $writers.Values) { $w.Close() }
Write-Host "  Total pills split: $total entries -> $($writers.Count) files"
$writers.Keys | Sort-Object | ForEach-Object { 
    $f = Get-Item "$outDir\pills_$_.jsonl"
    Write-Host "    $_ : $($f.Length / 1KB -as [int]) KB"
}

# ===== 5. 拆分 artifacts_tier.jsonl =====
Write-Host "`n=== Splitting artifacts_tier.jsonl ==="
$src = "$base\artifacts_tier.jsonl"
$writers = @{}; $total = 0
$reader = [System.IO.StreamReader]::new($src, [System.Text.Encoding]::UTF8)
while (($line = $reader.ReadLine()) -ne $null) {
    $s = $line.Trim()
    if ($s.Length -eq 0) { continue }
    try {
        $t = $s | ConvertFrom-Json
        $tier = $t.power_tier
        if (-not $writers.ContainsKey($tier)) {
            $fpath = "$outDir\artifacts_${tier}.jsonl"
            $writers[$tier] = [System.IO.StreamWriter]::new($fpath, $false, [System.Text.Encoding]::UTF8)
        }
        $writers[$tier].WriteLine($s)
        $total++
    } catch { }
}
$reader.Close()
foreach ($w in $writers.Values) { $w.Close() }
Write-Host "  Total artifacts split: $total entries -> $($writers.Count) files"
$writers.Keys | Sort-Object | ForEach-Object { 
    $f = Get-Item "$outDir\artifacts_$_.jsonl"
    Write-Host "    $_ : $($f.Length / 1KB -as [int]) KB"
}

Write-Host "`n===== All splits complete ====="
