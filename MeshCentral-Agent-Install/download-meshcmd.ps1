# Скачать MeshCmd с сервера MeshCentral
# Запускать из PowerShell

$ErrorActionPreference = "Stop"

# Обойти проверку SSL для самоподписанного сертификата
if (-not ([System.Management.Automation.PsTypeSerializer]::GetType("TrustAllCertsPolicy"))) {
    $code = @"
    using System;
    using System.Net;
    using System.Security.Cryptography.X509Certificates;
    public class TrustAllCertsPolicy : ICertificatePolicy {
        public bool CheckValidationResult(ServicePoint srvPoint, X509Certificate certificate, WebRequest request, int certificateProblem) {
            return true;
        }
    }
"@
    Add-Type -TypeDefinition $code -Language CSharp
    [System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy
}
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]'Tls,Tls11,Tls12'

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  MeshCmd Downloader" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$SERVER = "https://103.85.115.227"
$URL = "$SERVER/meshcmd?id=1"
$OUTPUT = "$PSScriptRoot\MeshCmd.exe"

Write-Host "Сервер: $SERVER"
Write-Host "URL: $URL"
Write-Host "Куда: $OUTPUT"
Write-Host ""

Write-Host "Скачивание MeshCmd..." -NoNewline

try {
    Invoke-WebRequest -Uri $URL -OutFile $OUTPUT -UseBasicParsing

    if (Test-Path $OUTPUT) {
        Write-Host " [OK]" -ForegroundColor Green
        Write-Host ""
        Write-Host "Файл скачан: $OUTPUT" -ForegroundColor Green
        Write-Host "Размер: $((Get-Item $OUTPUT).Length / 1MB -as [int]) MB"
        Write-Host ""
        Write-Host "Пример использования:" -ForegroundColor Cyan
        Write-Host "  .\MeshCmd.exe ConnectServer --url wss://103.85.115.227 --loginuser `"user@example.com`" --loginpass `"PASSWORD`""
        Write-Host ""
    } else {
        Write-Host " [FAIL]" -ForegroundColor Red
        Write-Host "Файл не скачан!"
        exit 1
    }
} catch {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host "Ошибка: $($_.Exception.Message)"
    exit 1
}
