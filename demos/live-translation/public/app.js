import { applyRevision } from "./revisions.js";

const micButton = document.querySelector("#mic-button");
const buttonText = document.querySelector("#button-text");
const statusText = document.querySelector("#status-text");
const errorBanner = document.querySelector("#error");
const captionBody = document.querySelector("#caption-body");
const captionPlaceholder = document.querySelector("#caption-placeholder");
const captionRows = document.querySelector("#caption-rows");

const states = {
  idle: { status: "麦克风未开启", button: "开始收听" },
  starting: { status: "正在连接", button: "取消" },
  recording: { status: "正在收听", button: "停止收听" },
  stopping: { status: "正在定稿", button: "正在停止" },
  stopped: { status: "已停止", button: "开始收听" },
};
const connectionTimeout = 15_000;
const stopTimeout = 17_000;
const maxQueuedAudio = 96 * 1024;
let phase = "idle";
let active;
let latestSegmentId = -1;
const segments = new Map();

function createCell(label, language) {
  const cell = document.createElement("p");
  cell.className = "caption-cell";
  cell.dataset.label = label;
  cell.dataset.final = "false";
  if (language) cell.lang = language;
  return cell;
}

function createSegment(segmentId) {
  if (segmentId <= latestSegmentId) return undefined;

  const row = document.createElement("div");
  row.className = "caption-row";
  row.dataset.segmentId = String(segmentId);
  const source = createCell("中文原文");
  const translation = createCell("English Translation", "en");
  row.append(source, translation);
  captionRows.append(row);

  const segment = {
    row,
    source,
    translation,
    sourceRevision: -1,
    translationRevision: -1,
    sourceFinal: false,
    translationFinal: false,
  };
  segments.set(segmentId, segment);
  latestSegmentId = segmentId;
  return segment;
}

function setPhase(next) {
  phase = next;
  document.documentElement.dataset.phase = next;
  const { status, button } = states[next];
  if (statusText.textContent !== status) {
    statusText.textContent = status;
  }
  buttonText.textContent = button;
  micButton.disabled = next === "stopping";
}

function showError(message = "") {
  errorBanner.textContent = message;
  errorBanner.hidden = !message;
}

function clearCaptions() {
  segments.clear();
  latestSegmentId = -1;
  captionRows.replaceChildren();
  captionPlaceholder.hidden = false;
  captionBody.scrollTop = 0;
}

function updateCaption(message) {
  const { type, segmentId, revision } = message;
  if (!Number.isInteger(segmentId) || segmentId < 0 || !Number.isInteger(revision) || revision < 0) return;
  const follow = captionBody.scrollHeight - captionBody.scrollTop - captionBody.clientHeight < 48;

  let segment = segments.get(segmentId);
  if (!segment) {
    if (type !== "source") return;
    segment = createSegment(segmentId);
    if (!segment) return;
  }

  if (!applyRevision(segment, message)) return;
  if (message.text.trim()) captionPlaceholder.hidden = true;
  if (follow) captionBody.scrollTop = captionBody.scrollHeight;
}

function finish(session, message) {
  if (active !== session) return;
  session.finishing = true;
  active = undefined;
  clearTimeout(session.stopTimer);
  session.source?.disconnect();
  session.processor?.disconnect();
  session.processor?.port.close();
  session.stream?.getTracks().forEach((track) => track.stop());
  if (session.context && session.context.state !== "closed") {
    session.context.close().catch(() => {});
  }
  if (session.socket?.readyState < WebSocket.CLOSING) session.socket.close();
  setPhase("stopped");
  showError(message);
}

function microphoneError(error) {
  switch (error.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "麦克风权限未开启，请在浏览器中允许使用麦克风后重试。";
    case "NotFoundError":
    case "NotReadableError":
      return "无法使用麦克风，请检查音频输入设备后重试。";
    default:
      return error.message || "无法开始收听，请重试。";
  }
}

function connect(session) {
  const url = new URL("/stream", window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(url);
  session.socket = socket;

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const message = "连接本机翻译服务超时，请重试。";
      reject(new Error(message));
      finish(session, message);
    }, connectionTimeout);

    socket.addEventListener("close", () => {
      clearTimeout(timer);
      const message = "与本机翻译服务的连接已断开。";
      reject(new Error(message));
      finish(session, message);
    });

    socket.addEventListener("error", () => {
      clearTimeout(timer);
      const message = "无法连接本机翻译服务，请确认服务已启动。";
      reject(new Error(message));
      finish(session, message);
    });

    socket.addEventListener("message", ({ data }) => {
      if (active !== session || typeof data !== "string") return;
      let message;
      try {
        message = JSON.parse(data);
      } catch {
        finish(session, "本机服务返回了无法读取的消息。");
        return;
      }

      if (message?.type === "ready") {
        clearTimeout(timer);
        resolve();
      } else if (message?.type === "error") {
        const reason = typeof message.message === "string" ? message.message : "本机翻译服务出错。";
        reject(new Error(reason));
        finish(session, reason);
      } else if (message?.type === "done") {
        finish(session, session.stopReason);
      } else if (message?.type === "source" || message?.type === "translation") {
        if (typeof message.text === "string") {
          updateCaption(message);
        }
      }
    });
  });
}

function handleAudio(session, data) {
  if (active !== session) return;
  const { socket } = session;
  if (socket.readyState !== WebSocket.OPEN) return;

  if (data?.type === "flushed") {
    if (phase === "stopping") socket.send(JSON.stringify({ type: "stop" }));
    return;
  }
  if (!(data instanceof ArrayBuffer)) return;

  if (socket.bufferedAmount + data.byteLength > maxQueuedAudio) {
    finish(session, "音频传输跟不上收听速度，请重新开始。");
    return;
  }
  socket.send(data);
}

async function start() {
  const session = {};
  active = session;
  showError();
  setPhase("starting");

  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext || !window.AudioWorkletNode) {
      throw new Error("当前浏览器或地址无法使用麦克风，请在支持音频录制的浏览器中打开本机网页。");
    }

    const context = new AudioContext({ latencyHint: "interactive" });
    session.context = context;
    const audioReady = context.resume().then(() => context.audioWorklet.addModule("/pcm-worklet.js"));
    const microphone = navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
      },
    }).then((stream) => {
      if (active !== session) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      session.stream = stream;
    });
    await Promise.all([audioReady, microphone, connect(session)]);
    if (active !== session) return;

    const processor = new AudioWorkletNode(context, "pcm-capture", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      channelCount: 1,
      channelCountMode: "explicit",
    });
    session.processor = processor;
    session.source = context.createMediaStreamSource(session.stream);

    processor.port.onmessage = ({ data }) => handleAudio(session, data);
    processor.addEventListener("processorerror", () => finish(session, "音频处理已中断，请重新开始。"));
    for (const track of session.stream.getAudioTracks()) {
      track.addEventListener("ended", () => {
        if (!session.stopRequested && !session.finishing) {
          stop(session, "麦克风已断开。");
        }
      }, { once: true });
    }

    clearCaptions();
    session.source.connect(processor);
    processor.connect(context.destination);
    setPhase("recording");
  } catch (error) {
    finish(session, microphoneError(error));
  }
}

function stop(session, reason) {
  if (active !== session || session.stopRequested) return;
  session.stopRequested = true;
  session.stopReason = reason;
  if (reason) showError(reason);
  setPhase("stopping");
  session.stopTimer = setTimeout(() => {
    finish(session, "本机翻译服务未完成最后一句的处理。");
  }, stopTimeout);
  session.processor.port.postMessage({ type: "flush" });
  session.stream.getTracks().forEach((track) => track.stop());
}

micButton.addEventListener("click", () => {
  if (phase === "starting") {
    finish(active);
  } else if (phase === "recording") {
    stop(active);
  } else if (phase !== "stopping") {
    void start();
  }
});

window.addEventListener("pagehide", () => {
  if (active) finish(active);
});
