# DrayEasy Market Radar 前端

产品经理候选人作品集概念的 React 19 + vinext + Recharts 可视化网站；非 DrayEasy 官方产品。浏览器只访问同源的 `/api/*`，服务端代理再连接 Python 推荐 API，大模型密钥不会进入前端代码。

## Docker 一键启动

在仓库根目录运行：

```bash
docker compose up --build
```

Compose 会等待真实模型 API healthy 后再启动 production standalone 前端，默认访问 `http://localhost:3000`。

## 本地启动

先在项目根目录启动模型 API：

```bash
crossborder serve --host 127.0.0.1 --port 8000
```

再启动网站：

```bash
npm install
npm run dev
```

默认打开 `http://localhost:3000/`。如模型 API 不在默认地址，在网站进程中设置：

```bash
RECOMMENDER_API_URL=https://your-protected-api.example.com npm run dev
```

## 检查

```bash
npm test
```

线上发布前必须提供受保护的 HTTPS 模型 API；不能把 `127.0.0.1:8000` 或 DeepSeek 密钥写进线上前端。
