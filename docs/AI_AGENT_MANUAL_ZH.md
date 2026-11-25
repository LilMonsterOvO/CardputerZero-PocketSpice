# PocketSpice 本地 AI 模型与 CLI 开发手册 (中文版)

## 1. 核心路径与工程规范
本手册用于指导 CardputerZero 本地小模型或终端脚本按规范选型、生成并验证任意 NGSPICE 工程（严格适配 512 MB 内存）：
- 安装目录: /usr/share/cp0-ngspice/
- 公共器件库: /usr/share/cp0-ngspice/lib/power_devices.lib
- 参考电路: /usr/share/cp0-ngspice/circuits/
- 配方索引: /usr/share/cp0-ngspice/docs/recipes.json
- 用户工程: $HOME/.config/cp0-ngspice/projects/<slug>/main.cir
- ZClaw 沙盒可用工程目录: $HOME/.zeroclaw/agents/zclaw/workspace/pocketspice/<slug>/main.cir（若沙盒禁止写入 `$HOME/.config`，保存至此目录亦可被 PocketSpice 自动识别）

## 2. CLI 无头 JSON 命令（本地 AI 直接调用）
1. 读取手册与配方:
   cp0-ngspice manual --topic ai --lang zh
   cp0-ngspice manual --topic recipes
2. 列出内置模板与用户工程:
   cp0-ngspice list --json
3. 克隆或从标准输入创建工程:
   cp0-ngspice new my_inv --from 04_5level_sc_inverter
   cat custom.cir | cp0-ngspice new my_custom --stdin
4. 语法与内存裁剪校验:
   cp0-ngspice validate my_custom
5. 运行仿真并读取 JSON 统计指标:
   cp0-ngspice run my_custom --json

## 3. NGSPICE v41 语法红线
1. 第 1 行必须是注释标题（如 `* My Circuit`），严禁将 `.param` 放在第 1 行。
2. `.param` 右侧表达式禁止带外层大括号:
   正确: `.param Tsw = '1.0 / 50000'`
   错误: `.param Tsw = {1.0 / 50000}`
3. 器件取值、PULSE/PWL 与 `.tran` 中才使用 `{param}` 引用。
4. 网表末尾必须以 `.end` 结束。
5. 电流采样请串联零电压源 `V_sns a b 0` 后读取 `i(V_sns)`。
6. 推荐复用 `.include power_devices.lib`：
   `IGBT_DIODE(c,e,g)`、`BIDIR_IGBT(a,b,g)`、`MOSFET_SW(d,s,g)`、`POWER_DIODE(a,k)`。

## 4. 强非线性开关拓扑收敛建议
- 开关模型设置平滑过渡 `Vh=-0.2`、有限 `Ron >= 1mΩ` 与并联缓冲 `100kΩ`。
- 多电平/开关电容拓扑推荐加 `.options method=gear reltol=2e-3`。
- 悬浮节点对地加 `1e7 Ω` 泄放电阻防止奇异矩阵。
- SPWM 载波优先使用 `PWL(...) r=0` 确保拐点对齐。
