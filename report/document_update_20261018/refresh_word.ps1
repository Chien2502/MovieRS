param([string]$InputDocx,[string]$WorkingDocx,[string]$PdfPath)
$taskWord=New-Object -ComObject Word.Application
$taskWord.Visible=$false
$taskWord.DisplayAlerts=0
try {
    Copy-Item -LiteralPath $InputDocx -Destination $WorkingDocx -Force
    $taskDoc=$taskWord.Documents.Open($WorkingDocx)
    $taskDoc.Fields.Update() | Out-Null
    foreach ($taskToc in $taskDoc.TablesOfContents) { $taskToc.Update() }
    foreach ($taskFig in $taskDoc.TablesOfFigures) { $taskFig.Update() }
    $taskDoc.Repaginate()
    $taskDoc.Save()
    $taskDoc.ExportAsFixedFormat($PdfPath,17)
    Write-Output ('Pages: '+$taskDoc.ComputeStatistics(2))
    $taskDoc.Close(0)
} finally {
    $taskWord.Quit()
    [Runtime.InteropServices.Marshal]::ReleaseComObject($taskWord) | Out-Null
}
