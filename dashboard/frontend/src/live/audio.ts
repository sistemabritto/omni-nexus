export function encodePCM(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.length * 2);
  const view = new DataView(bytes.buffer);
  samples.forEach((sample, i) => view.setInt16(i * 2, Math.round(Math.max(-1, Math.min(1, sample)) * (sample < 0 ? 32768 : 32767)), true));
  return btoa(String.fromCharCode(...bytes));
}
export class Playback {
  private nodes = new Set<AudioBufferSourceNode>();
  private next = 0;
  private context: AudioContext;
  private sampleRate:number;
  constructor(context: AudioContext, sampleRate = 24000) { this.context = context; this.sampleRate=sampleRate; }
  play(data: string) {
    const bytes = Uint8Array.from(atob(data), c => c.charCodeAt(0));
    if (!bytes.length || bytes.length % 2) return;
    // Bound latency and memory if a tab stalls.
    if (this.next - this.context.currentTime > 5) this.stop();
    const view = new DataView(bytes.buffer);
    const buffer = this.context.createBuffer(1, bytes.length / 2, this.sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < channel.length; i++) channel[i] = view.getInt16(i * 2, true) / 32768;
    const source = this.context.createBufferSource();
    source.buffer = buffer; source.connect(this.context.destination);
    this.nodes.add(source); source.onended = () => { this.nodes.delete(source); source.disconnect(); };
    const start = Math.max(this.next, this.context.currentTime);
    source.start(start); this.next = start + buffer.duration;
  }
  stop() { for (const node of this.nodes) { node.stop(); node.disconnect(); } this.nodes.clear(); this.next = 0; }
}
