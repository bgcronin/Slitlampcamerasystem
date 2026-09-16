# Read-only diagnostic. No patient folders or images are inspected.
$ErrorActionPreference = "Stop"
$devices = Get-CimInstance Win32_PnPEntity | Where-Object {
    $_.PNPClass -in @("Camera", "Image") -or $_.Name -match "Mizar|CSO|Canon|EOS"
}
$drivers = Get-CimInstance Win32_PnPSignedDriver
$report = [ordered]@{
    CollectedAt = (Get-Date).ToString("o")
    Windows = (Get-CimInstance Win32_OperatingSystem).Caption
    Architecture = $env:PROCESSOR_ARCHITECTURE
    Devices = @($devices | ForEach-Object {
        $device = $_
        $driver = $drivers | Where-Object { $_.DeviceID -eq $device.PNPDeviceID } | Select-Object -First 1
        [ordered]@{
            Name = $device.Name
            Class = $device.PNPClass
            Manufacturer = $device.Manufacturer
            Status = $device.Status
            HardwareIds = $device.HardwareID
            DriverProvider = $driver.DriverProviderName
            DriverVersion = $driver.DriverVersion
            InfName = $driver.InfName
        }
    })
}
$outputPath = Join-Path (Get-Location) "camera-diagnostic.json"
$report | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $outputPath
Write-Host "Saved read-only device diagnostic to $outputPath"
