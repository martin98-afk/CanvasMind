#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""天气查询脚本 - 支持当前天气、3 日预报、空气质量查询"""

import requests
import json
from datetime import datetime

# OpenWeatherMap API 配置
BASE_URL = 'https://api.openweathermap.org/data/2.5'
AIR_URL = 'http://api.openweathermap.org/data/2.5/air_pollution'

def get_weather(city, api_key, units='metric', lang='zh_cn'):
    """获取当前天气"""
    url = f'{BASE_URL}/weather'
    params = {
        'q': city,
        'appid': api_key,
        'units': units,
        'lang': lang
    }
    response = requests.get(url, params=params, timeout=10)
    if response.status_code == 200:
        return response.json()
    else:
        return {'error': f'请求失败：{response.status_code}', 'message': response.json().get('message', '')}

def get_forecast(city, api_key, units='metric', lang='zh_cn'):
    """获取 3 日天气预报（每 3 小时一次）"""
    url = f'{BASE_URL}/forecast'
    params = {
        'q': city,
        'appid': api_key,
        'units': units,
        'lang': lang
    }
    response = requests.get(url, params=params, timeout=10)
    if response.status_code == 200:
        data = response.json()
        # 筛选每天中午 12 点的数据作为代表
        forecast_list = []
        seen_dates = set()
        for item in data.get('list', []):
            dt = datetime.fromtimestamp(item['dt'])
            date_str = dt.strftime('%Y-%m-%d')
            if date_str not in seen_dates and dt.hour == 12:
                seen_dates.add(date_str)
                forecast_list.append({
                    'date': date_str,
                    'temp': item['main']['temp'],
                    'feels_like': item['main']['feels_like'],
                    'weather': item['weather'][0]['description'],
                    'icon': item['weather'][0]['icon'],
                    'humidity': item['main']['humidity'],
                    'wind_speed': item['wind']['speed']
                })
            if len(forecast_list) >= 3:
                break
        return {'city': data['city']['name'], 'forecast': forecast_list}
    else:
        return {'error': f'请求失败：{response.status_code}', 'message': response.json().get('message', '')}

def get_air_quality(city, api_key):
    """获取空气质量"""
    # 先获取城市坐标
    geo_url = 'http://api.openweathermap.org/geo/1.0/direct'
    geo_params = {'q': city, 'limit': 1, 'appid': api_key}
    geo_response = requests.get(geo_url, params=geo_params, timeout=10)
    if geo_response.status_code != 200 or not geo_response.json():
        return {'error': '无法获取城市坐标'}
    
    lat = geo_response.json()[0]['lat']
    lon = geo_response.json()[0]['lon']
    
    # 查询空气质量
    air_params = {'lat': lat, 'lon': lon, 'appid': api_key}
    response = requests.get(AIR_URL, params=air_params, timeout=10)
    if response.status_code == 200:
        data = response.json()
        aqi = data['list'][0]['main']['aqi']
        aqi_desc = {1: '优', 2: '良', 3: '轻度污染', 4: '中度污染', 5: '重度污染'}
        components = data['list'][0]['components']
        return {
            'aqi': aqi,
            'description': aqi_desc.get(aqi, '未知'),
            'pm2_5': components['pm2_5'],
            'pm10': components['pm10'],
            'o3': components['o3'],
            'no2': components['no2']
        }
    else:
        return {'error': f'请求失败：{response.status_code}'}

def format_weather_result(data):
    """格式化当前天气输出"""
    if 'error' in data:
        return f"❌ 错误：{data['error']} {data.get('message', '')}"
    
    weather = data['weather'][0]['description']
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    humidity = data['main']['humidity']
    wind_speed = data['wind']['speed']
    city = data['name']
    
    return f"""🌤️ {city} 当前天气
━━━━━━━━━━━━━━━━
📊 天气状况：{weather}
🌡️ 温度：{temp}°C（体感 {feels_like}°C）
💧 湿度：{humidity}%
💨 风速：{wind_speed} m/s"""

def format_forecast_result(data):
    """格式化天气预报输出"""
    if 'error' in data:
        return f"❌ 错误：{data['error']} {data.get('message', '')}"
    
    result = f"📅 {data['city']} 3 日预报\n━━━━━━━━━━━━━━━━\n"
    for day in data['forecast']:
        result += f"{day['date']} | {day['weather']} | {day['temp']}°C | 湿度{day['humidity']}%\n"
    return result

def format_air_result(data):
    """格式化空气质量输出"""
    if 'error' in data:
        return f"❌ 错误：{data['error']}"
    
    return f"""🍃 空气质量
━━━━━━━━━━━━━━━━
📊 AQI 指数：{data['aqi']} - {data['description']}
🔴 PM2.5: {data['pm2_5']} μg/m³
🟤 PM10: {data['pm10']} μg/m³
🟢 O3: {data['o3']} μg/m³
🔵 NO2: {data['no2']} μg/m³"""

if __name__ == '__main__':
    import sys
    
    # 从命令行参数或环境变量获取配置
    if len(sys.argv) < 3:
        print('用法：python weather_query.py <city> <api_key> [weather|forecast|air]')
        sys.exit(1)
    
    city = sys.argv[1]
    api_key = sys.argv[2]
    query_type = sys.argv[3] if len(sys.argv) > 3 else 'weather'
    
    if query_type == 'weather':
        result = get_weather(city, api_key)
        print(format_weather_result(result))
    elif query_type == 'forecast':
        result = get_forecast(city, api_key)
        print(format_forecast_result(result))
    elif query_type == 'air':
        result = get_air_quality(city, api_key)
        print(format_air_result(result))
    else:
        print('未知查询类型，支持：weather, forecast, air')
