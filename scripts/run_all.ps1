# 一条命令跑完离线流程（不含 API）
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

python -m ib_lab analyze
python -m ib_lab diagnose
python -m ib_lab baseline offline
python -m ib_lab table
