<h1>cds-cli</h1>

Copernicus CDS 任务提交、查询与下载的命令行工具。

## 安装

其他用户安装（无需克隆仓库）：
```bash
uv pip install git+https://github.com/kongdd/cds-cli
# uv pip install cds-cli
```

安装后命令为 `cds`。

## 下载依赖：aria2c

`cds download` 与 `cds monitor` 依赖 `aria2c`。

- **Linux / Windows**：安装本工具时自动安装第三方 `aria2` 包（内置 `aria2c`，目前为预发布版本）。
- **macOS**：该包暂无预编译版本，需提前安装：
```bash
brew install aria2
```

linux也可通过系统包管理器安装：
```bash
sudo apt install aria2              # Debian/Ubuntu
```

在安装环境中确认可用：
```bash
aria2c --version
```

若未安装，执行 `cds download` 会提示 `未找到 aria2c，请先安装 aria2`。

## 本地开发

```bash
uv sync        # SMB 挂载盘上的项目应将虚拟环境放在本地磁盘
uv run cds --help
```

## Configure
get your api <https://cds.climate.copernicus.eu/profile>

```bash
cat ~/.cdsapirc
url: https://cds.climate.copernicus.eu/api
key: <PERSONAL-ACCESS-TOKEN>
```

## 使用
```bash
cds status --status accepted,running,successful # 查看任务状态
cds fetch    # 拉取下载的url
cds download # 按清单下载（断点续传）
cds monitor  # 监听清单变化，自动下载
```

提交任务的示例脚本见 `submit.py`。
