$path = "C:\Program Files\EA Games\Mass Effect 2\BioGame\CookedPC"
$output = "C:\Users\juan\Documents\Playground\tali-pcc-results.txt"

$results = Get-ChildItem -Path $path -Recurse -Filter "*Tali*.pcc" -ErrorAction SilentlyContinue |
Select-Object -ExpandProperty FullName

$results | Set-Content -Path $output

$results
