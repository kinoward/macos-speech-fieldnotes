import { spawn } from "node:child_process";
import { readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { WebSocket, WebSocketServer } from "ws";

const port = Number(process.env.PORT || 8765);
const host = `127.0.0.1:${port}`;
const origin = `http://${host}`;
const bridgePath = process.env.SPEECH_BRIDGE ||
  fileURLToPath(new URL("../../.build/live", import.meta.url));
const files = new Map([
  ["/", ["index.html", "text/html; charset=utf-8"]],
  ["/styles.css", ["styles.css", "text/css; charset=utf-8"]],
  ["/app.js", ["app.js", "text/javascript; charset=utf-8"]],
  ["/revisions.js", ["revisions.js", "text/javascript; charset=utf-8"]],
  ["/pcm-worklet.js", ["pcm-worklet.js", "text/javascript; charset=utf-8"]]
]);

const server = createServer(async (request, response) => {
  if (request.headers.host !== host) {
    response.writeHead(403).end();
    return;
  }
  const path = request.url?.split("?", 1)[0];
  const asset = files.get(path);
  if (!asset || !["GET", "HEAD"].includes(request.method)) {
    response.writeHead(404).end();
    return;
  }
  try {
    const [filename, mimeType] = asset;
    const data = await readFile(new URL(`./public/${filename}`, import.meta.url));
    response.writeHead(200, {
      "Cache-Control": "no-cache",
      "Content-Type": mimeType,
      "Content-Length": data.length,
      "Content-Security-Policy": `default-src 'self'; connect-src 'self' ws://${host}; object-src 'none'; frame-ancestors 'none'`,
      "Permissions-Policy": "microphone=(self)",
      "X-Content-Type-Options": "nosniff"
    }).end(request.method === "HEAD" ? undefined : data);
  } catch (error) {
    console.error(error);
    response.writeHead(500).end();
  }
});

const sockets = new WebSocketServer({ noServer: true, maxPayload: 8192 });
server.on("upgrade", (request, socket, head) => {
  if (request.url !== "/stream" ||
      request.headers.host !== host ||
      request.headers.origin !== origin) {
    socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
    return;
  }
  sockets.handleUpgrade(request, socket, head, (ws) => sockets.emit("connection", ws));
});

let activeSocket;
sockets.on("connection", (ws) => {
  const send = (packet) => {
    if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(packet));
  };
  if (activeSocket) {
    send({ type: "error", message: "已有翻译正在运行。请先在原页面结束录音。" });
    ws.close(1008);
    return;
  }
  activeSocket = ws;

  const bridge = spawn(bridgePath, [], { stdio: ["pipe", "pipe", "inherit"] });
  const lines = createInterface({ input: bridge.stdout });
  let state = "starting";

  const fail = (message) => {
    if (state === "finished") return;
    state = "finished";
    send({ type: "error", message });
    ws.close(1011);
  };

  let deadline = setTimeout(() => fail("语音服务启动超时，请重新开始。"), 30000);
  ws.on("message", (data, binary) => {
    if (state !== "streaming") return;
    if (binary) {
      if (data.length === 0 || data.length % 2 !== 0) {
        fail("收到的麦克风音频格式有误。请重新开始。");
      } else if (bridge.stdin.writableLength > 128 * 1024) {
        fail("语音服务来不及处理音频。请重新开始。");
      } else {
        bridge.stdin.write(data);
      }
      return;
    }

    let packet;
    try {
      packet = JSON.parse(data.toString());
    } catch {
      fail("收到无法识别的控制消息。");
      return;
    }
    if (packet?.type === "stop") {
      state = "stopping";
      bridge.stdin.end();
      deadline = setTimeout(() => fail("语音服务结束超时。"), 12000);
    }
  });

  lines.on("line", (line) => {
    if (state === "finished") return;
    let packet;
    try {
      packet = JSON.parse(line);
    } catch {
      fail("语音服务返回了无法识别的数据。");
      return;
    }
    if (packet.type === "ready" && state === "starting") {
      clearTimeout(deadline);
      state = "streaming";
      send(packet);
    } else if (packet.type === "done") {
      state = "finished";
      send(packet);
      ws.close(1000);
    } else if (packet.type === "error") {
      fail(packet.message);
    } else if (["source", "translation"].includes(packet.type)) {
      send(packet);
    }
  });

  bridge.on("error", (error) => {
    console.error(error.message);
    fail("本机语音服务无法启动，请重新运行 demos/live-translation/run。");
  });
  bridge.stdin.on("error", () => {
    if (state === "streaming") fail("音频流已中断。请重新开始。");
  });
  bridge.on("close", () => {
    if (state !== "finished") fail("本机语音服务意外结束。请重新开始。");
  });
  ws.on("error", () => ws.terminate());
  ws.on("close", () => {
    clearTimeout(deadline);
    state = "finished";
    lines.close();
    bridge.stdin.destroy();
    if (bridge.exitCode === null && bridge.signalCode === null) bridge.kill();
    if (activeSocket === ws) activeSocket = undefined;
  });
});

function shutdown() {
  for (const ws of sockets.clients) ws.terminate();
  server.close();
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
server.on("error", (error) => {
  console.error(error.code === "EADDRINUSE" ? `本地端口 ${port} 已被使用。` : error.message);
  process.exitCode = 1;
});
server.listen(port, "127.0.0.1", () => {
  console.log(`实时翻译已启动：${origin}/`);
  if (process.env.OPEN_BROWSER === "1") {
    const opener = spawn("/usr/bin/open", [`${origin}/`], { stdio: "ignore" });
    opener.unref();
  }
});
