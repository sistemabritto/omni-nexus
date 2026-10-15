'use strict';
// Dormant provider-neutral boundary. No HTTP route, SDK, credentials or provider activation.
const { randomUUID } = require('node:crypto');
class VoiceBoundaryError extends Error {
  constructor(code) { super(code); this.name = 'VoiceBoundaryError'; this.code = code; }
}
const fail = code => { throw new VoiceBoundaryError(code); };
const identifier = value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(value);
// Reject identity overrides in structured tool arguments, including nested payloads.
function checkScope(input, context, depth = 0) {
  if (depth > 16) fail('invalid_tool_input');
  if (!input || typeof input !== 'object') return;
  for (const [key, value] of Object.entries(input)) {
    const expected = { userId:context.userId, user_id:context.userId, companyId:context.companyId, company_id:context.companyId, agentName:context.agentName, agent_name:context.agentName, sessionId:context.sessionId, session_id:context.sessionId };
    if (Object.hasOwn(expected, key) && value !== expected[key]) fail('scope_override_denied');
    checkScope(value, context, depth + 1);
  }
}
class VoiceRuntimeBoundary {
  #bindings = new Map();
  #sessions = new Map();
  constructor({ resolveSession, authorize, runTurn, executeTool, stopAudio = () => {}, clock = Date.now, ttlMs = 120000 }) {
    if (typeof resolveSession !== 'function' || typeof authorize !== 'function') fail('authority_required');
    if (!Number.isInteger(ttlMs) || ttlMs < 1 || ttlMs > 120000) fail('invalid_lease');
    this.resolveSession = resolveSession; this.authorize = authorize;
    // No implicit bridge to startSession: the integration must supply a turn-only port.
    this.runTurn = runTurn; this.executeTool = executeTool; this.stopAudio = stopAudio; this.clock = clock; this.ttlMs = ttlMs;
  }
  async #authority(actor, context, operation) {
    if (!actor || actor.authenticated !== true || actor.authMethod !== 'cookie' || actor.userId !== context.userId) fail('unauthorized');
    const session = await this.resolveSession(context.sessionId);
    // Current legacy sessions lacking owner/company cannot be adopted by the browser.
    if (!session || session.ownerUserId !== context.userId || session.companyId !== context.companyId || session.agentName !== context.agentName) fail('session_scope_denied');
    if (await this.authorize({ actor, context, operation }) !== true) fail('permission_denied');
    if (session.ownerUserId !== context.userId || session.companyId !== context.companyId || session.agentName !== context.agentName) fail('session_scope_denied');
    return session;
  }
  async open(actor, selection) {
    if (!actor || !identifier(actor.userId) || !selection || !Number.isSafeInteger(selection.companyId) || selection.companyId < 1 || !identifier(selection.agentName) || !identifier(selection.sessionId)) fail('invalid_binding');
    const context = Object.freeze({ userId:actor.userId, companyId:selection.companyId, agentName:selection.agentName, sessionId:selection.sessionId });
    const session = await this.#authority(actor, context, 'bind');
    if (session.active || this.#sessions.has(context.sessionId)) fail('session_busy');
    const id = randomUUID();
    this.#bindings.set(id, { context, expiresAt:this.clock() + this.ttlMs, turn:null, epoch:0 });
    this.#sessions.set(context.sessionId, id);
    return Object.freeze({ bindingId:id, context });
  }
  async #get(actor, id, operation) {
    const binding = this.#bindings.get(id);
    if (!binding) fail('binding_not_found');
    if (this.clock() >= binding.expiresAt) { this.#release(id, binding); fail('binding_expired'); }
    try { await this.#authority(actor, binding.context, operation); } catch (error) {
      if (actor?.authenticated === true && actor.authMethod === 'cookie' && actor.userId === binding.context.userId) this.#release(id,binding);
      throw error;
    }
    return binding;
  }
  #cancel(binding) {
    const turn = binding.turn;
    if (!turn) return false;
    binding.turn = null; binding.epoch++;
    turn.controller.abort();
    try { this.stopAudio(binding.context, turn.id); } catch { /* Abort still succeeds if playback is already closed. */ }
    return true;
  }
  #release(id, binding) {
    this.#cancel(binding); this.#bindings.delete(id); this.#sessions.delete(binding.context.sessionId);
  }
  async startTurn(actor, id, text, onEvent = () => {}) {
    const binding = await this.#get(actor, id, 'turn');
    if (typeof text !== 'string' || !text.trim() || text.length > 16000 || typeof onEvent !== 'function') fail('invalid_turn');
    if (typeof this.runTurn !== 'function') fail('runtime_port_unavailable');
    if (binding.turn || (await this.resolveSession(binding.context.sessionId))?.active) fail('session_busy');
    // Recheck after asynchronous lookup so concurrent turns cannot both acquire the lease.
    if (binding.turn || this.#bindings.get(id) !== binding) fail('session_busy');
    const turn = { id:randomUUID(), controller:new AbortController(), epoch:++binding.epoch };
    binding.turn = turn;
    const current = () => this.#bindings.get(id) === binding && binding.turn === turn && !turn.controller.signal.aborted && this.clock() < binding.expiresAt;
    const tools = Object.freeze({ call:async (name, input) => {
      if (!current()) fail('turn_cancelled');
      await this.#get(actor, id, 'tool');
      if (typeof name !== 'string' || !name || typeof this.executeTool !== 'function') fail('tool_denied');
      let safeInput;
      try { const serialized = JSON.stringify(input ?? {}); if (serialized.length > 128000) fail('invalid_tool_input'); safeInput = JSON.parse(serialized); } catch { fail('invalid_tool_input'); }
      checkScope(safeInput, binding.context);
      if (await this.authorize({ actor, context:binding.context, operation:'tool_call', toolName:name, input:safeInput }) !== true) fail('tool_denied');
      if (!current()) fail('turn_cancelled');
      // The executor receives canonical scope separately, never a model-chosen identity.
      return this.executeTool({ context:binding.context, toolName:name, input:safeInput, signal:turn.controller.signal });
    } });
    // The trusted runtime port owns LLM/history/approvals. The provider supplies only text.
    const completion = Promise.resolve().then(async () => {
      await this.#get(actor, id, 'turn');
      if (!current()) fail('turn_cancelled');
      return this.runTurn({ context:binding.context, text, signal:turn.controller.signal, tools,
        onEvent:event => { if (current()) onEvent(event); } });
    }).catch(error => { throw new VoiceBoundaryError(error instanceof VoiceBoundaryError ? error.code : 'runtime_turn_failed'); })
      .finally(() => { if (binding.turn === turn) binding.turn = null; });
    // Prevent an unhandled rejection when a consumer only handles transport cancellation.
    void completion.catch(() => {});
    return Object.freeze({ turnId:turn.id, completion });
  }
  // Minimal managed-agent read capability. No prompts, history, credentials or SDK IDs.
  async readSession(actor, id) {
    const binding = await this.#get(actor,id,'read_session');
    const session = await this.#authority(actor,binding.context,'read_session');
    return Object.freeze({ companyId:binding.context.companyId, agentName:binding.context.agentName,
      sessionId:binding.context.sessionId, name:typeof session.name === 'string' ? session.name.slice(0,200) : null,
      active:session.active === true });
  }
  async interrupt(actor, id, turnId) { const binding = await this.#get(actor, id, 'interrupt'); if (turnId && binding.turn?.id !== turnId) return false; return this.#cancel(binding); }
  async close(actor, id) { const binding = await this.#get(actor, id, 'close'); this.#release(id, binding); }
  // Called by the server's lease sweep; no provider/browser identity arguments.
  sweepExpired() { for (const [id,binding] of this.#bindings) if (this.clock() >= binding.expiresAt) this.#release(id,binding); }
}
module.exports = { VoiceRuntimeBoundary, VoiceBoundaryError };
