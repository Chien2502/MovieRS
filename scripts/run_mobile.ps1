# Chạy từ bất kỳ thư mục nào; Flutter không đọc .env của backend.
[CmdletBinding()]
param(
    [string]$ApiUrl,
    [string]$DeviceId,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
if (-not $ApiUrl) {
    try {
        $tunnels = Invoke-RestMethod -Uri 'http://127.0.0.1:4040/api/tunnels' -TimeoutSec 5
        $tunnel = $tunnels.tunnels | Where-Object {
            $_.public_url -like 'https://*' -and
            $_.config.addr -match '^(https?://)?(localhost|127\.0\.0\.1|\[::1\]):8000/?$'
        } | Select-Object -First 1
        $ApiUrl = $tunnel.public_url
    } catch {
        throw 'Không tìm được Ngrok. Chạy ngrok http 8000 trước, hoặc truyền -ApiUrl https://dia-chi-api.'
    }
}
if (-not $ApiUrl) {
    throw 'Không có đường hầm HTTPS tới cổng 8000. Kiểm tra Ngrok hoặc truyền -ApiUrl.'
}
$ApiUrl = $ApiUrl.Trim().TrimEnd('/') -replace '/api$', ''
$parsedUrl = $null
if (-not [Uri]::TryCreate($ApiUrl, [UriKind]::Absolute, [ref]$parsedUrl) -or
    $parsedUrl.Scheme -notin @('http', 'https') -or
    $parsedUrl.UserInfo -or $parsedUrl.Query -or $parsedUrl.Fragment -or
    $parsedUrl.AbsolutePath -ne '/') {
    throw 'ApiUrl phải là URL gốc HTTP/HTTPS, không chứa mật khẩu, query hoặc đường dẫn khác /api.'
}
$headers = @{ 'ngrok-skip-browser-warning' = 'true' }
try {
    $health = Invoke-RestMethod -Uri "$ApiUrl/api/health/database" -Headers $headers -TimeoutSec 25
} catch {
    throw "Không gọi được API qua $ApiUrl. Kiểm tra python api/main.py và ngrok http 8000."
}
if ($health.status -ne 'connected' -or $health.schema_ready -ne $true) {
    throw 'API đã phản hồi nhưng PostgreSQL hoặc schema chưa sẵn sàng.'
}
Write-Host "API: $ApiUrl/api; PostgreSQL: connected"
if ($CheckOnly) { return }

$flutterArguments = @('run', "--dart-define=API_URL=$ApiUrl", '--no-resident')
if ($DeviceId) { $flutterArguments += @('-d', $DeviceId) }
$python = Join-Path $PSScriptRoot '../.venv-refactor/Scripts/python.exe'
if (-not (Test-Path $python)) { $python = 'python' }
$verifyScript = Join-Path $PSScriptRoot 'check_mobile_runtime.py'
$verifyArguments = @($verifyScript, $ApiUrl)
if ($DeviceId) { $verifyArguments += @('--device', $DeviceId) }
Push-Location (Join-Path $PSScriptRoot '../mobile_app')
try {
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        & flutter @flutterArguments
        if ($LASTEXITCODE -ne 0) { throw "Flutter kết thúc với mã lỗi $LASTEXITCODE." }
        & $python @verifyArguments
        if ($LASTEXITCODE -eq 0) { break }
        if ($LASTEXITCODE -ne 1) {
            throw 'Không xác minh được URL trong ứng dụng. Kiểm tra kết nối ADB và bản Flutter debug.'
        }
        if ($attempt -eq 2) {
            throw 'Ứng dụng vẫn dùng sai URL API sau khi build lại. Kiểm tra cấu hình Flutter.'
        }
        Write-Warning 'Flutter đã cài bản dùng URL cũ; xóa cache build rồi cài lại.'
        & flutter clean
        if ($LASTEXITCODE -ne 0) { throw 'Flutter clean thất bại.' }
        & flutter pub get
        if ($LASTEXITCODE -ne 0) { throw 'Flutter pub get thất bại.' }
    }
} finally {
    Pop-Location
}
