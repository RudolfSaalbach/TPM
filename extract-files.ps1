<#
.SYNOPSIS
    Extract files from Chronos Engine code artifacts
    
.DESCRIPTION
    This script extracts individual files from the multi-file artifacts
    created by Claude, organizing them into the proper directory structure.
    
.EXAMPLE
    .\extract-files.ps1
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$SourceFile = "chronos-complete-code.txt",
    
    [Parameter(Mandatory = $false)]
    [string]$OutputDir = "extracted"
)

function Extract-FilesFromArtifact {
    param(
        [string]$FilePath,
        [string]$OutputDirectory
    )
    
    if (!(Test-Path $FilePath)) {
        Write-Error "Source file not found: $FilePath"
        return
    }
    
    $content = Get-Content -Path $FilePath -Raw -Encoding UTF8
    
    # Pattern to match file sections
    $filePattern = '# === FILE: (.+?) ===(.*?)# === END FILE: .+? ==='
    
    $matches = [regex]::Matches($content, $filePattern, [System.Text.RegularExpressions.RegexOptions]::Singleline)
    
    Write-Host "Found $($matches.Count) files to extract" -ForegroundColor Green
    
    foreach ($match in $matches) {
        $filePath = $match.Groups[1].Value.Trim()
        $fileContent = $match.Groups[2].Value.Trim()
        
        # Remove leading "./" if present
        $filePath = $filePath -replace '^\./', ''
        
        # Create full output path
        $outputPath = Join-Path $OutputDirectory $filePath
        $outputDir = Split-Path $outputPath -Parent
        
        # Create directory if it doesn't exist
        if (!(Test-Path $outputDir)) {
            New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
        }
        
        # Write file content
        Set-Content -Path $outputPath -Value $fileContent -Encoding UTF8
        Write-Host "✅ Extracted: $filePath" -ForegroundColor Cyan
    }
    
    Write-Host ""
    Write-Host "Extraction completed!" -ForegroundColor Green
    Write-Host "Files extracted to: $OutputDirectory" -ForegroundColor Yellow
}

# Create output directory
if (!(Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Extract files
Extract-FilesFromArtifact -FilePath $SourceFile -OutputDirectory $OutputDir
