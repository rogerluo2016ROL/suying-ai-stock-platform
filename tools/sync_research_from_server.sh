#!/bin/bash
# 从生产服务器(8.134.71.3 docker bind-mount)拉取最新 pipeline_runs,再镜像到妙搭内容仪表盘 DB。
# cron 每 10min 跑一次。服务器无 rsync,故用 tar-over-ssh。
set -e
cd "/Users/rogerluo/程序目录/K线大模型"
mkdir -p outputs/pipeline_runs
# 1. 拉取服务器最新 result.json(流式 tar,不删本地额外文件)
ssh -o StrictHostKeyChecking=accept-new root@8.134.71.3 \
  'tar czf - -C /root/kline-platform/outputs/pipeline_runs .' 2>/dev/null \
  | tar xzf - -C "outputs/pipeline_runs/"
# 2. 镜像每个模型最新 run → 妙搭应用 DB(online)
/opt/homebrew/bin/python3 tools/sync_research_run_to_dashboard.py --scan-latest --environment online
