# 高校教师个人成果管理系统

这是一个面向高校教师的个人成果与支撑材料管理系统项目。

项目目标是帮助教师平时沉淀个人成果、过程性工作和支撑材料，在年度绩效统计、成果评优、部门汇总等场景中，一键导出业绩清单和按类目整理好的材料包。

## 当前阶段

当前仓库已经进入 MVP 开发阶段，已完成基础的本机/局域网试用版功能。

需求文档：

- `docs/superpowers/specs/2026-06-03-teacher-achievement-system-requirements.md`

实施计划：

- `docs/superpowers/plans/2026-06-03-teacher-achievement-system-implementation.md`

## 第一版方向

- 多人登录
- 本机/局域网试用部署
- 教师成果记录
- 支撑材料上传
- 过程性工作与成果性工作管理
- 绩效规则提示
- 手动填写申报分
- 年度清单导出
- 支撑材料 ZIP 打包
- 管理员账号、规则和汇总管理

## 本地运行

```powershell
cd C:\Users\lenovo\Desktop\jixiao\.worktrees\mvp-implementation
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
.\run.ps1
```

如果 pip 因本机代理报错，可先执行：

```powershell
$env:NO_PROXY="*"
$env:no_proxy="*"
pip install -r requirements.txt
```

本机访问：

```text
http://127.0.0.1:8001
```

局域网访问：

```powershell
ipconfig
```

找到主机 IPv4 地址后，同一局域网内访问：

```text
http://主机IPv4:8001
```

默认管理员：

```text
账号：admin
密码：admin123456
```

首次试用后请修改管理员密码。

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

