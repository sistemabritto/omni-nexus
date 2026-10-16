'use strict';

// Modalities are controller facts, not statements inferred from model prose.
const HTTP_TEXT_NOTICE = 'Esta conversa está em modo de texto sem ferramentas. Posso trabalhar com o texto fornecido; não consigo consultar arquivos, APIs ou executar ações nesta modalidade.\n\n';
function httpTextCapability() {
  return { schema: 'chat-tools-v1', mode: 'http_text_only', tools_list: [],
    toolExecution: 'unavailable', modelToolUse: 'not_provided', externalMcp: 'not_activated' };
}
function requireCompatibleCodeTransport(mode, cli, available) {
  if (mode !== 'code') return;
  if (!['claude', 'openclaude'].includes(cli) || !available) {
    const error = new Error('chat_code_transport_unavailable: o adaptador selecionado não fornece ferramentas neste Chat. Use somente uma rota com capacidades comprovadas; não houve fallback para texto nem execução.');
    error.code = 'chat_code_transport_unavailable';
    error.capabilities = { ...httpTextCapability(), mode: 'blocked_code_transport', httpFallbackAttempted: false };
    throw error;
  }
}
function rejectUnexpectedToolCall(delta) {
  if ((Array.isArray(delta?.tool_calls) && delta.tool_calls.length) || delta?.function_call) {
    const error = new Error('http_tool_call_not_executed: o transporte recebeu uma chamada de ferramenta sem executor; nenhuma ação foi realizada.');
    error.code = 'http_tool_call_not_executed';
    throw error;
  }
}
module.exports = { HTTP_TEXT_NOTICE, httpTextCapability, requireCompatibleCodeTransport, rejectUnexpectedToolCall };
