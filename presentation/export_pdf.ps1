$ErrorActionPreference = "Stop"

$deckPath = Join-Path $PSScriptRoot "PeopleOps_HR_Pipeline_Results.pptx"
$pdfPath = Join-Path $PSScriptRoot "slides.pdf"
if (-not (Test-Path -LiteralPath $deckPath -PathType Leaf)) {
    throw "PowerPoint deck not found: $deckPath"
}

$powerPoint = $null
$presentation = $null
try {
    $powerPoint = New-Object -ComObject PowerPoint.Application
    $presentation = $powerPoint.Presentations.Open($deckPath, $true, $false, $false)
    if (Test-Path -LiteralPath $pdfPath) {
        Remove-Item -LiteralPath $pdfPath -Force
    }
    $presentation.SaveAs($pdfPath, 32)
    $presentation.Close()
    $presentation = $null
    if (-not (Test-Path -LiteralPath $pdfPath -PathType Leaf)) {
        throw "PowerPoint did not create the PDF: $pdfPath"
    }
    Write-Output "Exported presentation PDF: $pdfPath"
}
finally {
    if ($null -ne $presentation) {
        $presentation.Close()
    }
    if ($null -ne $powerPoint) {
        $powerPoint.Quit()
    }
}
