# Apilot 插件

Apilot是一个多功能信息服务插件，通过识别特定关键词为用户提供各类实用信息和服务。

## 安装依赖

本插件依赖以下Python库:
```
requests
urllib
datetime
uuid
imghdr
io
```

大多数依赖在Python标准库中已包含，只需安装requests库:
```bash
pip install requests
```

## 功能介绍

### 资讯类服务
- **早报**: 发送"早报"获取每日新闻早报(图片或文字形式)
- **摸鱼日历**: 发送"摸鱼"获取摸鱼人日历图片
- **摸鱼视频**: 发送"摸鱼视频"获取摸鱼相关视频
- **热榜查询**: 发送"xx热榜"查询各平台热门话题(支持微博、知乎、哔哩哔哩等多个平台)
- **明星八卦**: 发送"八卦"获取最新娱乐圈八卦

### 实用工具
- **天气查询**: 发送"城市+天气"查询指定城市天气，支持查询今天、明天、后天及未来7天天气
  - 格式: `北京天气`、`上海明天天气`、`广州7天天气`
- **快递查询**: 发送"快递+单号"查询快递状态
  - 格式: `快递112345655`
  - 顺丰快递需提供收件人手机尾号: `快递SF123456:1234`
- **星座运势**: 发送星座名称查询今日运势
  - 支持的星座: 白羊座、金牛座、双子座、巨蟹座、狮子座、处女座、天秤座、天蝎座、射手座、摩羯座、水瓶座、双鱼座
- **字典查询**: 发送"查字典 汉字"查询汉字信息
  - 格式: `查字典 你`
- **黄金价格**: 发送"黄金"查询最新黄金价格
- **油价查询**: 发送"xx油价"查询各省油价信息
  - 格式: `广东油价`

## 配置说明

插件支持两种API来源:
1. **免费API**(vvhan): 无需配置，默认使用
2. **ALAPI**(功能更全面): 需配置token

### 配置步骤
1. 在插件目录下创建`config.json`文件或复制`config.json.template`
2. 填写配置内容:
```json
{
  "alapi_token": "你的ALAPI令牌",
  "morning_news_text_enabled": false
}
```

### 配置项说明
- `alapi_token`: ALAPI服务的令牌，可从[ALAPI官网](https://alapi.cn)获取
- `morning_news_text_enabled`: 
  - `false`: 早报以图片形式显示(默认)
  - `true`: 早报以文字形式显示

## 使用说明

发送对应的关键词即可触发相应功能，例如:
- 发送"早报"获取今日早报
- 发送"北京天气"查询北京市天气
- 发送"快递123456789"查询快递信息
- 发送"微博热榜"查看微博热门话题

## 支持的热榜平台

- 微博热榜: `微博热榜`
- 知乎热榜: `知乎热榜`
- 哔哩哔哩热榜: `哔哩哔哩热榜`
- 抖音热榜: `抖音热榜`
- 百度热榜: `百度热榜`
- 豆瓣热榜: `豆瓣热榜`
- 虎扑热榜: `虎扑热榜`
- 36氪热榜: `36氪热榜`
- 虎嗅热榜: `虎嗅热榜`
- IT资讯热榜: `IT热榜`
- 头条热榜: `头条热榜`
- 知乎日报: `知乎日报热榜`
- 产品经理: `产品经理热榜` 