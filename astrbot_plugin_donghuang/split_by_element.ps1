# split_by_element.ps1 — 将已按品阶/类别拆分的文件进一步按元素(金木水火土等)拆分
# 保留源文件作为 fallback（element=None 时不走元素级路径）

$ErrorActionPreference = "Stop"
$base = "E:\AIproject\ArstBot\astrbot_plugin_donghuang\data"

function Split-JsonlByElement($dir, $label) {
    $done = 0; $newFiles = 0
    Get-ChildItem "$dir\*.jsonl" | ForEach-Object {
        $fpath = $_.FullName; $fname = $_.Name
        Write-Host "  $fname ($($_.Length/1KB -as [int]) KB)..."
        $writers = @{}; $total = 0; $err = 0
        $reader = [System.IO.StreamReader]::new($fpath, [System.Text.Encoding]::UTF8)
        while (($line = $reader.ReadLine()) -ne $null) {
            $s = $line.Trim()
            if ($s.Length -eq 0) { continue }
            try {
                $t = $s | ConvertFrom-Json
                $elem = $t.element
                if ([string]::IsNullOrEmpty($elem)) { $elem = "无" }
                if (-not $writers.ContainsKey($elem)) {
                    $bn = [System.IO.Path]::GetFileNameWithoutExtension($fname)
                    $writers[$elem] = [System.IO.StreamWriter]::new(
                        "$dir\${bn}_${elem}.jsonl", $false, [System.Text.Encoding]::UTF8)
                }
                $writers[$elem].WriteLine($s); $total++
            } catch { $err++ }
        }
        $reader.Close()
        foreach ($w in $writers.Values) { $w.Close() }
        Write-Host "    -> $total / $err err -> $($writers.Count) element files (source kept)"
        $done += $total; $newFiles += $writers.Count
    }
    Write-Host "  [$label] $done entries -> $newFiles new element-files"
    return $newFiles
}

Write-Host "=== 1. Splitting items/ by element ==="
$fItems = Split-JsonlByElement "$base\items" "items"
Write-Host "=== 2. Splitting techniques/ by element ==="
$fTech = Split-JsonlByElement "$base\techniques" "techniques"
Write-Host "=== Done: $fItems item-files + $fTech technique-files added ==="
