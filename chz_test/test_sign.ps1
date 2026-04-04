# Тест подписи с разными параметрами
$CSP = "C:\Program Files\Crypto Pro\CSP\csptest.exe"
$DATA = "TOCJVINHPFCLMSGKRLQGRSWGJAPKUY"
$CERT = "2297e52c1066bcaab8a9708a66935e56d9761fc2"
$CONT = "2508151514-781421365746"

# Сохраняем данные
Set-Content -Path "$env:TEMP\chz_data.txt" -Value $DATA -NoNewline -Encoding UTF8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ВАРИАНТ 1: -my с отпечатком" -ForegroundColor Yellow
Write-Host "========================================"
& $CSP -sign -my $CERT -in "$env:TEMP\chz_data.txt" -out "$env:TEMP\sig1.txt" -base64
if ($LASTEXITCODE -eq 0) {
    Write-Host "УСПЕХ!" -ForegroundColor Green
    Get-Content "$env:TEMP\sig1.txt"
} else {
    Write-Host "ОШИБКА $LASTEXITCODE" -ForegroundColor Red
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ВАРИАНТ 2: -cont с полным именем" -ForegroundColor Yellow
Write-Host "========================================"
& $CSP -sign -cont "SCARD\pkcs11_rutoken_ecp_46c444f8\$CONT" -in "$env:TEMP\chz_data.txt" -out "$env:TEMP\sig2.txt" -base64
if ($LASTEXITCODE -eq 0) {
    Write-Host "УСПЕХ!" -ForegroundColor Green
    Get-Content "$env:TEMP\sig2.txt"
} else {
    Write-Host "ОШИБКА $LASTEXITCODE" -ForegroundColor Red
}
Write-Host ""

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ВАРИАНТ 3: -provtype 80 -cont" -ForegroundColor Yellow
Write-Host "========================================"
& $CSP -sign -provtype 80 -cont $CONT -in "$env:TEMP\chz_data.txt" -out "$env:TEMP\sig3.txt" -base64
if ($LASTEXITCODE -eq 0) {
    Write-Host "УСПЕХ!" -ForegroundColor Green
    Get-Content "$env:TEMP\sig3.txt"
} else {
    Write-Host "ОШИБКА $LASTEXITCODE" -ForegroundColor Red
}
Write-Host ""
