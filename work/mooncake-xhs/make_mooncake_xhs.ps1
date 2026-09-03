$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$srcDir = "C:\Users\yiliu\Desktop\刘炎"
$outDir = Join-Path $srcDir "小红书教程图"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$files = Get-ChildItem -LiteralPath $srcDir -File -Filter "*.jpg" |
  Where-Object { $_.Name -ne "contact_sheet.jpg" } |
  Sort-Object Name

function New-RectF($x, $y, $w, $h) {
  return [System.Drawing.RectangleF]::new([float]$x, [float]$y, [float]$w, [float]$h)
}

function New-RoundRectPath($rect, $radius) {
  $path = [System.Drawing.Drawing2D.GraphicsPath]::new()
  $d = [float]($radius * 2)
  $path.AddArc($rect.X, $rect.Y, $d, $d, 180, 90)
  $path.AddArc($rect.Right - $d, $rect.Y, $d, $d, 270, 90)
  $path.AddArc($rect.Right - $d, $rect.Bottom - $d, $d, $d, 0, 90)
  $path.AddArc($rect.X, $rect.Bottom - $d, $d, $d, 90, 90)
  $path.CloseFigure()
  return $path
}

function Draw-CoverImage($g, $path, $rect, $radius) {
  $img = [System.Drawing.Image]::FromFile($path)
  try {
    $ratio = [Math]::Max($rect.Width / $img.Width, $rect.Height / $img.Height)
    $sw = [int]($rect.Width / $ratio)
    $sh = [int]($rect.Height / $ratio)
    $sx = [int](($img.Width - $sw) / 2)
    $sy = [int](($img.Height - $sh) / 2)
    $src = [System.Drawing.Rectangle]::new($sx, $sy, $sw, $sh)
    $dst = [System.Drawing.Rectangle]::new([int]$rect.X, [int]$rect.Y, [int]$rect.Width, [int]$rect.Height)
    $state = $g.Save()
    $clip = New-RoundRectPath $rect $radius
    $g.SetClip($clip)
    $attrs = [System.Drawing.Imaging.ImageAttributes]::new()
    $matrix = [System.Drawing.Imaging.ColorMatrix]::new(@(
      [single[]](1.09, 0, 0, 0, 0),
      [single[]](0, 1.06, 0, 0, 0),
      [single[]](0, 0, 0.96, 0, 0),
      [single[]](0, 0, 0, 1, 0),
      [single[]](0.035, 0.025, 0.005, 0, 1)
    ))
    $attrs.SetColorMatrix($matrix)
    $g.DrawImage($img, $dst, $src.X, $src.Y, $src.Width, $src.Height, [System.Drawing.GraphicsUnit]::Pixel, $attrs)
    $g.Restore($state)
    $clip.Dispose()
  }
  finally {
    $img.Dispose()
  }
}

function Draw-TextCentered($g, $text, $font, $brush, $rect) {
  $sf = [System.Drawing.StringFormat]::new()
  $sf.Alignment = [System.Drawing.StringAlignment]::Center
  $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
  $g.DrawString($text, $font, $brush, $rect, $sf)
  $sf.Dispose()
}

function Draw-Label($g, $text, $x, $y, $font, $fill, $fg) {
  $padX = 18
  $padY = 8
  $size = $g.MeasureString($text, $font)
  $rect = New-RectF $x $y ($size.Width + $padX * 2) ($size.Height + $padY * 2)
  $path = New-RoundRectPath $rect 14
  $g.FillPath($fill, $path)
  $g.DrawString($text, $font, $fg, ($x + $padX), ($y + $padY))
  $path.Dispose()
}

$W = 1440
$H = 1920
$bmp = [System.Drawing.Bitmap]::new($W, $H)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

$bg = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 248, 230))
$cream = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 241, 190))
$yellow = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 242, 181, 36))
$orange = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 215, 112, 36))
$brown = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 75, 55, 35))
$white = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
$muted = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 132, 98, 58))
$linePen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 255, 255, 255), 8)

$g.FillRectangle($bg, 0, 0, $W, $H)

$fontTitle = [System.Drawing.Font]::new("Microsoft YaHei UI", 78, [System.Drawing.FontStyle]::Bold)
$fontSub = [System.Drawing.Font]::new("Microsoft YaHei UI", 36, [System.Drawing.FontStyle]::Regular)
$fontTag = [System.Drawing.Font]::new("Microsoft YaHei UI", 30, [System.Drawing.FontStyle]::Bold)
$fontSmall = [System.Drawing.Font]::new("Microsoft YaHei UI", 26, [System.Drawing.FontStyle]::Regular)
$fontMini = [System.Drawing.Font]::new("Microsoft YaHei UI", 22, [System.Drawing.FontStyle]::Regular)

$hero = New-RectF 70 70 1300 760
Draw-CoverImage $g $files[11].FullName $hero 34
$shade = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(95, 80, 42, 10))
$g.FillRectangle($shade, 70, 570, 1300, 260)
$g.DrawString("广式奶香月饼", $fontTitle, $white, 105, 605)
$g.DrawString("12个 x 50g｜新手友好教程", $fontSub, $white, 112, 715)
Draw-Label $g "皮薄馅足 · 回油更香" 970 96 $fontTag $yellow $brown

$recipeRect = New-RectF 70 875 1300 230
$recipePath = New-RoundRectPath $recipeRect 24
$g.FillPath($cream, $recipePath)
$recipePath.Dispose()
$g.DrawString("月饼皮配方（12个50g）", $fontTag, $brown, 108, 905)
$items = @(
  "转化糖浆 107g", "枧水 3g", "花生油 40g",
  "中筋面粉 156g", "奶粉 8g", "馅料按每个约35g"
)
for ($i=0; $i -lt $items.Count; $i++) {
  $x = 110 + ($i % 3) * 410
  $y = 972 + [Math]::Floor($i / 3) * 58
  $g.FillEllipse($orange, $x, ($y + 11), 14, 14)
  $g.DrawString($items[$i], $fontSmall, $brown, ($x + 25), $y)
}

$labels = @("备料", "糖浆+枧水", "加油乳化", "揉成团", "分馅", "压模", "入炉", "刷蛋液", "出炉晾凉")
$pick = @(0,1,3,6,8,9,10,11,11)
$gridX = 70
$gridY = 1130
$gap = 18
$cellW = [int](($W - 140 - $gap * 2) / 3)
$cellH = 188
for ($i=0; $i -lt 9; $i++) {
  $col = $i % 3
  $row = [Math]::Floor($i / 3)
  $x = $gridX + $col * ($cellW + $gap)
  $y = $gridY + $row * ($cellH + 56)
  $rect = New-RectF $x $y $cellW $cellH
  Draw-CoverImage $g $files[$pick[$i]].FullName $rect 22
  $numBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(232, 242, 181, 36))
  Draw-Label $g ("{0:D2} {1}" -f ($i+1), $labels[$i]) ($x + 16) ($y + 16) $fontMini $numBrush $brown
  $numBrush.Dispose()
}

$footerY = 1850
$g.DrawString("小贴士：先喷水烤定型，再薄刷蛋液；完全放凉后密封回油。", $fontSmall, $muted, 80, $footerY)

$out = Join-Path $outDir "广式奶香月饼_小红书教程拼图.jpg"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Jpeg)

$g.Dispose()
$bmp.Dispose()
Write-Output $out
