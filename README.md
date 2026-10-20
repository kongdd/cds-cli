<h1>cds-cli<\h1>

## Install
Install via `pip` with:: `pip install cdsapi`

## Configure

get your api <https://cds.climate.copernicus.eu/profile>

```bash
cat ~/.cdsapirc
url: https://cds.climate.copernicus.eu/api
key: <PERSONAL-ACCESS-TOKEN>
```

## 使用
- `sublimt.py`提交任务

```bash
cds status --status accepted,running,successful
cds fetch    # 拉取下载的url
cds monitor  # 开始下载文件
```
