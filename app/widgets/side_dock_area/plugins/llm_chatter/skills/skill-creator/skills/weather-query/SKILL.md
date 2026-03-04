---
name: weather-query
description: 查询全球任意城市的当前天气、3 日天气预报和空气质量指数。支持 OpenWeatherMap API，提供结构化的天气数据输出。
license: MIT
---

# 天气查询技能

使用 OpenWeatherMap API 查询全球任意城市的天气信息。

## 功能支持

- 🌤️ **当前天气**：温度、体感温度、湿度、风速、天气状况
- 📅 **3 日预报**：每日中午 12 点的天气预测
- 🍃 **空气质量**：AQI 指数、PM2.5、PM10、O3、NO2 浓度

## 配置要求

### API Key 配置

在使用前，需要配置 OpenWeatherMap API Key：

1. 访问 https://home.openweathermap.org/users/sign_up 注册账号
2. 登录后进入 https://home.openweathermap.org/api_keys 获取 API Key
3. 将 API Key 存储在环境变量 `OPENWEATHER_API_KEY` 中，或在调用时传入

**注意**：新注册的 API Key 可能需要 10-30 分钟才能激活。

### 依赖安装

```bash
pip install requests
```

## 使用方法

### 命令行调用

```bash
# 查询当前天气
python scripts/weather_query.py <城市名> <API Key> weather

# 查询 3 日预报
python scripts/weather_query.py <城市名> <API Key> forecast

# 查询空气质量
python scripts/weather_query.py <城市名> <API Key> air
```

### 示例

```bash
# 查询北京当前天气
python scripts/weather_query.py 北京 dfewfwf weather

# 查询上海 3 日预报
python scripts/weather_query.py 上海 dfewfwf forecast

# 查询广州空气质量
python scripts/weather_query.py 广州 dfewfwf air
```

## 技能触发条件

当用户请求包含以下关键词时，应触发此技能：

- "天气"、"气温"、"下雨"、"晴天"、"多云"
- "预报"、"未来几天天气"
- "空气质量"、"AQI"、"PM2.5"
- "今天/明天天气怎么样"

## 输出格式

技能会返回结构化的天气信息，包括：

1. **当前天气**：城市名、天气状况、温度、体感温度、湿度、风速
2. **3 日预报**：日期、天气状况、温度、湿度
3. **空气质量**：AQI 指数、等级描述、主要污染物浓度

## 错误处理

- API Key 无效：返回认证错误提示
- 城市名无法识别：返回城市未找到提示
- 网络超时：返回网络错误提示
- API 配额超限：返回配额限制提示

## 参考资料

- **API 文档**：详见 `references/api_reference.md`
- **OpenWeatherMap 官方文档**：https://openweathermap.org/api

## 注意事项

1. 免费 API Key 每分钟最多调用 60 次
2. 空气质量数据可能需要 One Call API 3.0 订阅
3. 城市名支持中文和英文，建议使用英文城市名以提高准确率
4. 如需查询历史天气，需要升级到付费计划
