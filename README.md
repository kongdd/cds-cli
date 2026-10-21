<h1>cds-cli</h1>

Copernicus CDS 任务提交、查询与下载的命令行工具。

## 安装

其他用户安装（无需克隆仓库）：

```bash
uv pip install git+https://github.com/kongdd/cds-cli
# 或发布到 PyPI 后
uv pip install cds-cli
```

安装后命令为 `cds`，需系统已安装 `aria2`（提供 `aria2c`）。

开发者本地开发：

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
