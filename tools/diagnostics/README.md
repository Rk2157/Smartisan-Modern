# 定位回调观察与离线汇总

这些工具用于解释定位路径与核对快照，独立于 APK 构建；不会打包进模块。适用范围是已授权测试设备及本次核对过的钉钉版本，混淆类名和方法签名不保证跨版本通用。

`callback_statistics.js` 只观察下游 `i71.d(String, boolean, DtLocation)`，按 `ServiceType` 分类，不同时统计工厂、listener 或其他业务入口。因此结果是该观察点的自然回调次数，不是 `fromLocation` / `fromAMapLocation` 的直接调用次数，也不是所有页面实际消费位置的次数。脚本不主动请求定位、不调用 Probe、不写配置、不修改风险检测。它仍会注入 Frida 运行时、替换一个方法并增加解码开销，可能改变目标进程的运行特征。本轮曾出现风险提示，不能把它视为完全无侵入的验收手段。

观察器原参数调用原方法一次，保留返回值及异常，再读取当前快照作比较。它不修改 DTO。`match` 同时要求：

- 纬度、经度分别换算为米后，每个轴的偏差不超过 5.001 米，覆盖模块既有位置扰动；这不是径向 5 米的判定。
- 高度与精度分别相等。
- 15 项地址 getter 的值分别相等。

记录不输出实际坐标、地址、快照标识、SSID 或 BSSID，但 JSONL/详细汇总仍含 PID、运行标识和时间等诊断元数据，应保存在本机，公开报告仅放去标识聚合结果。

## 依赖与采集

离线汇总只需 Python 标准库。在线观察还需 Python 环境中的 `requirements.txt`、ADB、匹配版本的 Frida 服务及已授权的本机端口转发。采集器不会自行部署服务、启动或停止应用；准备与清理须由测试负责人完成。`--serial` 必须显式指定，默认 Frida 地址只监听本机转发。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/diagnostics/requirements.txt
mkdir -p diagnostics-output
python3 - <<'PY'
import json
from pathlib import Path
Path('diagnostics-output/control.json').write_text(json.dumps({
    'stage': 'unclassified', 'stop': False, 'summary_token': 0
}))
PY
.venv/bin/python tools/diagnostics/collect_callbacks.py \
  --serial AUTHORIZED_DEVICE_SERIAL \
  --control diagnostics-output/control.json \
  --output diagnostics-output/callbacks.jsonl --max-seconds 900
```

采集器将每条消息追加、flush、fsync 后才确认阶段和汇总已收到。先等待 `ready`，再原子替换控制 JSON 的 `stage`，并等待对应 `stage` 确认，之后才执行该阶段的页面操作。允许值为 `unclassified`、`first_entry`、`refresh`、`reentry`、`after_restart`；这些只是测试人员指定的窗口名，不能自行证明冷启动或首次进入。递增 `summary_token` 请求持久化检查点；将 `stop` 设为 `true` 请求最终汇总及卸载。采集结束后仍须移除临时服务和转发、恢复测试前设置。

## 统计与完整性

```sh
python3 tools/diagnostics/summarize_callbacks.py \
  diagnostics-output/callbacks.jsonl \
  --json diagnostics-output/summary.json \
  --csv diagnostics-output/summary.csv --require-closed
python3 -m unittest discover -s tools/diagnostics -p 'test_*.py'
```

汇总器只累加 `callback.delta`；heartbeat、stage 和 summary 是前缀累计核对，绝不重复计数。每行按阶段、来源、PID、run_id 分组，检查脚本及主机序列、计数等式、累计值与最终汇总。`calls = match + mismatch + uncomparable`，原方法异常、观察异常及空值另列。

阶段需有明确起点，并由后续阶段检查点或有效最终汇总关闭；最终汇总还须已持久化、计数一致且 `in_flight=0`。停止后尾部仍有回调、序列缺失、汇总失败等情况会报告未闭环或无效。`--require-closed` 在未闭环时返回非零状态；默认模式也会在数据损坏时失败。

启动前、重连与停止缺口的未观察次数是未知值，不能记为零。即使所有已观察窗口闭环，也不能声称覆盖进程全生命周期。本轮结论见 [统计报告](../../docs/callback-statistics-report.md)。
