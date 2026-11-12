// Integration adapter: authentication and provider construction belong to the host.
// Never pass a raw provider URL/error to the client or application logs.
const MAX_FRAME = 32000;
function attachLiveBridge(client, { authenticated, originAllowed, freeTierVerified, openProvider, model }) {
  let provider, ready = false, closed = false;
  const send = value => { if (client.readyState === 1) client.send(JSON.stringify(value)); };
  const stop = () => { if (closed) return; closed = true; clearTimeout(deadline); provider?.close(); client.close(); };
  const deadline = setTimeout(stop, 120000);
  if (authenticated !== true || originAllowed !== true) { send({ error: 'unauthorized' }); stop(); return; }
  if (freeTierVerified !== true || typeof model !== 'string' || !/^[a-zA-Z0-9._-]+$/.test(model)) { send({ error: 'free_tier_unverified' }); stop(); return; }
  try { provider = openProvider(); } catch { send({ error: 'provider_unavailable' }); stop(); return; }
  provider.on('open', () => { if (closed) return; provider.send(JSON.stringify({ setup: {
    model: `models/${model}`, responseModalities: ['AUDIO'],
    systemInstruction: { parts: [{ text: 'Converse exclusivamente em português brasileiro. Seja breve. Você não tem acesso a ferramentas ou dados de produção.' }] },
    inputAudioTranscription: {}, outputAudioTranscription: {},
  } })); });
  provider.on('message', raw => {
    try {
      if (closed) return;
      const msg = JSON.parse(raw.toString());
      if (msg.setupComplete) { ready = true; send({ status: 'ready' }); }
      const content = msg.serverContent;
      if (content?.interrupted) send({ interrupted: true });
      for (const part of content?.modelTurn?.parts || []) {
        if (part.inlineData?.mimeType?.startsWith('audio/pcm')) send({ audio: part.inlineData.data });
      }
      if (content?.inputTranscription?.text) send({ transcript: content.inputTranscription.text, role: 'user' });
      if (content?.outputTranscription?.text) send({ transcript: content.outputTranscription.text, role: 'model' });
      if (msg.goAway) { send({ status: 'reconnect_required' }); stop(); }
      if (msg.error || msg.toolCall) { send({ error: 'provider_unavailable' }); stop(); }
    } catch { send({ error: 'provider_protocol' }); stop(); }
  });
  client.on('message', raw => {
    try {
      if (raw.length > MAX_FRAME || !ready || closed) throw Error();
      const msg = JSON.parse(raw.toString());
      if (typeof msg.audio !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(msg.audio) || msg.audio.length % 4) throw Error();
      const bytes = Buffer.from(msg.audio, 'base64');
      if (!bytes.length || bytes.length % 2 || bytes.length > 16000) throw Error();
      if (provider.bufferedAmount > 64000) throw Error();
      provider.send(JSON.stringify({ realtimeInput: { audio: { data: msg.audio, mimeType: 'audio/pcm;rate=16000' } } }));
    } catch { send({ error: 'invalid_audio' }); stop(); }
  });
  provider.on('error', () => { send({ error: 'provider_unavailable' }); stop(); });
  provider.on('close', stop);
  client.on('close', stop);
  client.on('error', stop);
  return stop;
}
module.exports = { attachLiveBridge };
