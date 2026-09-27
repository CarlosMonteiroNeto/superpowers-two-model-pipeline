[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Plan,
    [Parameter(Mandatory = $true)][string]$Config,
    [int]$MaxParallel,
    [ValidateSet('local', 'pull_request')][string]$Publication,
    [switch]$NewRun,
    [switch]$ConfirmHooksTrusted,
    [switch]$ConfirmPolicyClean
)
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw 'Python 3 is required to run the Codex pipeline.' }
$argsList = @((Join-Path $scriptDir 'codex_launcher.py'), $Plan, '--config', $Config)
if ($MaxParallel -gt 0) { $argsList += @('--max-parallel', "$MaxParallel") }
if ($Publication) { $argsList += @('--publication', $Publication) }
if ($NewRun) { $argsList += '--new-run' }
if ($ConfirmHooksTrusted) { $argsList += '--confirm-hooks-trusted' }
if ($ConfirmPolicyClean) { $argsList += '--confirm-policy-clean' }
& $python.Source @argsList
exit $LASTEXITCODE
