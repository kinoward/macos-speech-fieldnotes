const targetRate = 16_000;
const batchSamples = 1_440;

class PCMCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / targetRate;
    this.remaining = this.ratio;
    this.sum = 0;
    this.count = 0;
    this.batch = new DataView(new ArrayBuffer(batchSamples * 2));
    this.stopped = false;

    this.port.onmessage = ({ data }) => {
      if (data?.type !== "flush" || this.stopped) return;
      this.stopped = true;
      this.sendBatch();
      this.port.postMessage({ type: "flushed" });
    };
  }

  sendBatch() {
    if (!this.count) return;
    const data = this.count === batchSamples
      ? this.batch.buffer
      : this.batch.buffer.slice(0, this.count * 2);
    this.port.postMessage(data, [data]);
    this.batch = new DataView(new ArrayBuffer(batchSamples * 2));
    this.count = 0;
  }

  push(value) {
    const level = Math.max(-1, Math.min(1, value));
    const pcm = Math.round(level * (level < 0 ? 0x8000 : 0x7fff));
    this.batch.setInt16(this.count * 2, pcm, true);
    this.count += 1;
    if (this.count === batchSamples) this.sendBatch();
  }

  process(inputs) {
    if (this.stopped) return false;
    const mono = inputs[0]?.[0];
    if (!mono) return true;

    // Average each output interval, carrying fractional sample weights across quanta.
    for (const sample of mono) {
      let available = 1;
      while (available >= this.remaining - 1e-9) {
        this.sum += sample * this.remaining;
        this.push(this.sum / this.ratio);
        available = Math.max(0, available - this.remaining);
        this.remaining = this.ratio;
        this.sum = 0;
      }
      this.sum += sample * available;
      this.remaining -= available;
    }

    return true;
  }
}

registerProcessor("pcm-capture", PCMCapture);
