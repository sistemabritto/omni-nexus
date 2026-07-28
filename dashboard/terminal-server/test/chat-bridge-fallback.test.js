const assert = require('assert/strict');
const test = require('node:test');

const {
  buildProviderFallbackChain,
  isRetryableProviderError,
  isFatalProviderError,
  SDK_COMPATIBLE_CLI,
} = require('../src/chat-bridge');

// Fixture no formato retornado por loadProviderConfig()
function makeConfig() {
  const nvidiaEnv = {
    CLAUDE_CODE_USE_OPENAI: '1',
    OPENAI_BASE_URL: 'https://integrate.api.nvidia.com/v1',
    OPENAI_API_KEY: 'nvapi-XXX',
    OPENAI_MODEL: 'stepfun-ai/step-3.7-flash',
    NVIDIA_API_KEY: 'nvapi-XXX',
  };
  const omniEnv = {
    CLAUDE_CODE_USE_OPENAI: '1',
    OPENAI_BASE_URL: 'http://omniroute:20128/v1',
    OPENAI_API_KEY: 'omni-key',
    OPENAI_MODEL: 'auto',
  };
  return {
    cli_command: 'openclaude',
    env_vars: { ...nvidiaEnv },
    active: 'nvidia',
    mode: 'code',
    fallback_models: ['deepseek-ai/deepseek-v4-flash'],
    fallback_providers: ['omnirouter', 'anthropic'],
    providers: {
      nvidia: {
        cli_command: 'openclaude',
        env_vars: { ...nvidiaEnv },
        active: 'nvidia',
        mode: 'code',
        fallback_models: ['deepseek-ai/deepseek-v4-flash'],
        fallback_providers: ['omnirouter', 'anthropic'],
        model_tiers: {},
      },
      omnirouter: {
        cli_command: 'openclaude',
        env_vars: { ...omniEnv },
        active: 'omnirouter',
        mode: 'code',
        fallback_models: [],
        fallback_providers: [],
        model_tiers: {},
      },
      anthropic: {
        cli_command: 'claude',
        env_vars: {},
        active: 'anthropic',
        mode: null,
        fallback_models: [],
        fallback_providers: [],
        model_tiers: {},
      },
    },
    model_tiers: {},
  };
}

test('chain: primário → fallback_models → fallback_providers → anthropic', () => {
  const chain = buildProviderFallbackChain(makeConfig());
  const labels = chain.map((c) => `${c.providerId}:${c.model || 'native'}`);
  assert.deepEqual(labels, [
    'nvidia:stepfun-ai/step-3.7-flash',
    'nvidia:deepseek-ai/deepseek-v4-flash',
    'omnirouter:auto',
    'anthropic:native',
  ]);
});

test('attempt de fallback usa o env do PRÓPRIO provider, não do ativo', () => {
  const chain = buildProviderFallbackChain(makeConfig());
  const omni = chain.find((c) => c.providerId === 'omnirouter');
  assert.ok(omni, 'omnirouter deve estar na cadeia');
  assert.equal(omni.baseUrl, 'http://omniroute:20128/v1');
  assert.equal(omni.envVars.OPENAI_BASE_URL, 'http://omniroute:20128/v1');
  assert.equal(omni.envVars.OPENAI_API_KEY, 'omni-key');
  // A chave NVIDIA não pode vazar pro attempt do gateway — sequestra a chamada.
  assert.equal(omni.envVars.NVIDIA_API_KEY, undefined);
});

test('attempt final anthropic é claude nativo com env limpo', () => {
  const chain = buildProviderFallbackChain(makeConfig());
  const last = chain[chain.length - 1];
  assert.equal(last.providerId, 'anthropic');
  assert.equal(last.cliCommand, 'claude');
  assert.deepEqual(last.envVars, {});
  assert.equal(last.model, null);
});

// 2026-07-28 — o Claude nativo ativo era o único provider SEM plano B.
//
// A cadeia só era montada para provider externo, então a configuração padrão
// (anthropic ativo) rodava sem fallback nenhum: estourar a cota mensal
// derrubava a sessão do agente no meio da conversa, com o erro cru na tela.
// É o caso mais provável de todos — a cota acaba sozinha, sem ninguém mexer
// em nada.
test('anthropic ativo abre a cadeia com o nativo e segue para os outros providers', () => {
  const config = makeConfig();
  config.active = 'anthropic';
  config.cli_command = 'claude';
  config.env_vars = {};
  const labels = buildProviderFallbackChain(config).map((c) => `${c.providerId}:${c.model || 'native'}`);
  assert.equal(labels[0], 'anthropic:native', 'o provider ativo tem de ser o primeiro attempt');
  assert.ok(labels.length > 1, 'anthropic ativo precisa ter para onde cair');
  assert.ok(labels.includes('omnirouter:auto'), 'o gateway é o primeiro socorro');
});

test('anthropic não se repete no fim da cadeia que já começou nele', () => {
  const config = makeConfig();
  config.active = 'anthropic';
  config.env_vars = {};
  const labels = buildProviderFallbackChain(config).map((c) => `${c.providerId}:${c.model || 'native'}`);
  assert.equal(labels.filter((l) => l === 'anthropic:native').length, 1);
});

test('provider sem chave fica fora da cadeia derivada', () => {
  // Attempt sem credencial só rende 401 — e 401 é fatal, o que ENCERRARIA a
  // rotação em vez de continuar. Um provider vazio na cadeia é pior do que
  // não ter cadeia.
  const config = makeConfig();
  config.active = 'anthropic';
  config.env_vars = {};
  config.providers.omnirouter.env_vars = { OPENAI_BASE_URL: 'http://omniroute:20128/v1' };
  const labels = buildProviderFallbackChain(config).map((c) => c.providerId);
  assert.ok(!labels.includes('omnirouter'));
});

test('fallback_providers declarado vence a derivação automática', () => {
  const config = makeConfig();
  config.active = 'anthropic';
  config.env_vars = {};
  config.providers.anthropic.fallback_providers = ['nvidia'];
  const labels = buildProviderFallbackChain(config).map((c) => c.providerId);
  assert.deepEqual([...new Set(labels)], ['anthropic', 'nvidia']);
});

// 2026-07-28 — na VPS, active_provider era "opencode", cujo cli_command não
// fala o protocolo do Agent SDK. O attempt dele é filtrado, e como o
// fallback_providers do opencode lista ["nvidia","anthropic","openrouter"]
// (nvidia sequer existe no arquivo), o chat começava direto no Claude nativo
// — a cota paga — com o gateway atrás dele na fila. O badge dizia
// "anthropic/native" e parecia que o fallback não estava funcionando.
test('anthropic é o último recurso, mesmo declarado no meio da lista', () => {
  const config = makeConfig();
  config.active = 'opencode';
  config.providers.opencode = {
    cli_command: 'opencode',
    env_vars: { OPENAI_BASE_URL: 'https://omni.example/v1', OPENAI_API_KEY: 'k', OPENAI_MODEL: 'auto' },
    active: 'opencode',
    mode: 'code',
    fallback_models: [],
    fallback_providers: ['anthropic', 'omnirouter'],
    model_tiers: {},
  };
  const chain = buildProviderFallbackChain(config)
    .filter((a) => SDK_COMPATIBLE_CLI.has(a.cliCommand));
  const labels = chain.map((c) => `${c.providerId}:${c.model || 'native'}`);
  assert.deepEqual(labels, ['omnirouter:auto', 'anthropic:native'],
    'o gateway vem antes da cota paga e finita');
});

test('anthropic aparece uma vez só, mesmo declarado e reanexado no fim', () => {
  const config = makeConfig();
  config.providers.nvidia.fallback_providers = ['anthropic', 'omnirouter', 'anthropic'];
  const labels = buildProviderFallbackChain(config).map((c) => c.providerId);
  assert.equal(labels.filter((p) => p === 'anthropic').length, 1);
  assert.equal(labels[labels.length - 1], 'anthropic');
});

test('isRetryableProviderError reconhece o 503 do OmniRoute', () => {
  assert.ok(isRetryableProviderError(new Error('API Error: 503 Maximum combo retry limit reached')));
  assert.ok(isRetryableProviderError(new Error('429 Too Many Requests')));
  assert.ok(isRetryableProviderError(new Error('Service Unavailable')));
  assert.ok(!isRetryableProviderError(new Error('SyntaxError: unexpected token')));
});

// O texto exato que o CLI devolve quando a cota mensal acaba. Nenhum dos
// padrões clássicos (429, "rate limit", "quota") aparece nele — era por isso
// que o erro chegava inteiro ao chat em vez de rotacionar o provider.
test('isRetryableProviderError reconhece a cota do Claude Code esgotada', () => {
  const real = "Claude Code returned an error result: You've hit your monthly spend limit · " +
    'raise it at claude.ai/settings/usage?from=cc_cli_limit_message';
  assert.ok(isRetryableProviderError(new Error(real)));
  assert.ok(!isFatalProviderError(real), 'cota esgotada não é erro de credencial');
  assert.ok(isRetryableProviderError(new Error('Claude AI usage limit reached')));
  assert.ok(isRetryableProviderError(new Error('Your credit balance is too low')));
});

test('isFatalProviderError reconhece erros de auth', () => {
  assert.ok(isFatalProviderError(new Error('401 Unauthorized')));
  assert.ok(isFatalProviderError(new Error('invalid api key')));
  assert.ok(!isFatalProviderError(new Error('503 Service Unavailable')));
});

// opencode não implementa o protocolo de subprocesso do Agent SDK
// (--input-format stream-json / control_request-response) — só claude e
// openclaude falam esse protocolo. Um attempt com cli_command "opencode" na
// cadeia (ex.: se o provider ativo algum dia ganhar um OPENAI_MODEL) tem que
// ser filtrado pelo chamador antes de spawnar via SDK, senão é o crash
// "exit code 1 / chat não responde" que motivou esse teste.
function makeOpencodeConfig() {
  const opencodeEnv = { OPENAI_MODEL: 'auto' };
  const anthropicEnv = {};
  return {
    cli_command: 'opencode',
    env_vars: { ...opencodeEnv },
    active: 'opencode',
    mode: 'code',
    fallback_models: [],
    fallback_providers: ['anthropic'],
    providers: {
      opencode: {
        cli_command: 'opencode',
        env_vars: { ...opencodeEnv },
        active: 'opencode',
        mode: 'code',
        fallback_models: [],
        fallback_providers: ['anthropic'],
        model_tiers: {},
      },
      anthropic: {
        cli_command: 'claude',
        env_vars: { ...anthropicEnv },
        active: 'anthropic',
        mode: null,
        fallback_models: [],
        fallback_providers: [],
        model_tiers: {},
      },
    },
    model_tiers: {},
  };
}

test('cadeia crua inclui o attempt opencode (documenta o que precisa ser filtrado)', () => {
  const chain = buildProviderFallbackChain(makeOpencodeConfig());
  const labels = chain.map((c) => `${c.providerId}:${c.cliCommand}`);
  assert.deepEqual(labels, ['opencode:opencode', 'anthropic:claude']);
});

test('filtro por SDK_COMPATIBLE_CLI remove o attempt opencode e mantém o anthropic nativo', () => {
  const chain = buildProviderFallbackChain(makeOpencodeConfig())
    .filter((attempt) => SDK_COMPATIBLE_CLI.has(attempt.cliCommand));
  assert.equal(chain.length, 1);
  assert.equal(chain[0].providerId, 'anthropic');
  assert.equal(chain[0].cliCommand, 'claude');
});

test('SDK_COMPATIBLE_CLI aceita claude e openclaude, rejeita opencode', () => {
  assert.ok(SDK_COMPATIBLE_CLI.has('claude'));
  assert.ok(SDK_COMPATIBLE_CLI.has('openclaude'));
  assert.ok(!SDK_COMPATIBLE_CLI.has('opencode'));
});
