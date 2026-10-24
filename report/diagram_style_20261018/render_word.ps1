param([string]$InputDocx,[string]$PdfPath)
$InputDocx=(Resolve-Path -LiteralPath $InputDocx).Path
$PdfPath=[IO.Path]::GetFullPath($PdfPath).Replace('/', '\')
$diagramWord=New-Object -ComObject Word.Application
$diagramWord.Visible=$false
$diagramWord.DisplayAlerts=0
try {
    $diagramDoc=$diagramWord.Documents.Open($InputDocx,$false,$true)
    $diagramDoc.Repaginate()
    $diagramDoc.ExportAsFixedFormat($PdfPath,17)
    Write-Output ('Pages: '+$diagramDoc.ComputeStatistics(2))
    $diagramDoc.Close(0)
} finally {
    $diagramWord.Quit()
    [Runtime.InteropServices.Marshal]::ReleaseComObject($diagramWord) | Out-Null
}
