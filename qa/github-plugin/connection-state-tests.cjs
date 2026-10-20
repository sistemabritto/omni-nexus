// Actual page handlers/React element tree with synthetic hooks and HTTP only.
// No browser, credential, backend, GitHub request or production login is used.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const frontend = path.resolve('dashboard/frontend');
const React = require(frontend + '/node_modules/react');
const ts = require(frontend + '/node_modules/typescript');
const hooks = [];
let cursor = 0, effects = [], dirty = false, tree;
const equal = (a, b) => a && b && a.length === b.length && a.every((x, i) => Object.is(x, b[i]));
const react = {
  ...React,
  useState(initial) {
    const i = cursor++;
    if (!hooks[i]) hooks[i] = { value: typeof initial === 'function' ? initial() : initial };
    return [hooks[i].value, next => {
      hooks[i].value = typeof next === 'function' ? next(hooks[i].value) : next;
      dirty = true;
    }];
  },
  useRef(initial) {
    const i = cursor++;
    return (hooks[i] ||= { current: initial });
  },
  useCallback(fn, deps) {
    const i = cursor++;
    if (!hooks[i] || !equal(hooks[i].deps, deps)) hooks[i] = { fn, deps };
    return hooks[i].fn;
  },
  useEffect(fn, deps) {
    const i = cursor++;
    if (!hooks[i] || !equal(hooks[i].deps, deps)) {
      hooks[i] = { deps };
      effects.push(fn);
    }
  },
};
const translations = {
  'integrations.configuredPending': 'Configurado — teste pendente',
  'integrations.credentialsSaved': 'Credencial salva no servidor. Campos secretos ficam vazios; preencha apenas para substituir.',
};
const requests = [];
let configured = false, status = 'not_configured', healthy = true;
let delayNextEnv = false, releaseEnv;
const fixture = () => ({ integrations: [
  { name: 'Core fixture', category: 'other', kind: 'core', status: 'ok', configured: true },
  { name: 'GitHub', category: 'productivity', kind: 'plugin', slug: 'plugin-github-github',
    source_plugin: 'github', integration_slug: 'github', status, configured,
    health_check: { type: 'http', url: 'https://synthetic.invalid/user' },
    env_specs: [{ name: 'GITHUB_PLUGIN_TOKEN', secret: true, required: true }] },
] });
const api = {
  async get(url) {
    requests.push({ method: 'GET', url });
    if (url === '/integrations') return structuredClone(fixture());
    if (url === '/social-accounts') return { platforms: [] };
    if (url === '/config/env') {
      if (delayNextEnv) {
        delayNextEnv = false;
        await new Promise(resolve => { releaseEnv = resolve; });
      }
      return { entries: [] };
    }
    if (url === '/integrations/databases') return { flavors: [] };
    if (url === '/brain-repo/status') return {};
    throw Error('unexpected fixture route ' + url);
  },
  async post(url, body) {
    requests.push({ method: 'POST', url });
    if (url === '/integrations/plugin/plugin-github-github') {
      assert.equal(body.env_vars.GITHUB_PLUGIN_TOKEN, 'fixture-only');
      configured = true; status = 'pending';
      return { ok: true };
    }
    assert.equal(url, '/integrations/plugin/plugin-github-github/test');
    status = healthy ? 'connected' : 'error';
    return { ok: healthy, status_code: healthy ? 200 : 401, duration_ms: 12, error: healthy ? null : 'expected 200, got 401' };
  },
};
const moduleValue = { exports: {} };
const source = fs.readFileSync(frontend + '/src/pages/Integrations.tsx', 'utf8');
const output = ts.transpileModule(source, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022,
} }).outputText;
function load(name) {
  if (name === 'react') return react;
  if (name === 'react/jsx-runtime') return require(frontend + '/node_modules/react/jsx-runtime');
  if (name === 'react-i18next') return { useTranslation: () => ({ t: key => translations[key] || key }) };
  if (name === 'lucide-react') return new Proxy({}, { get: () => () => null });
  if (name === '../lib/api') return { api };
  if (name === '../lib/integrationMeta') return { getIntegrationMeta: () => null };
  if (name.startsWith('../components/')) return { __esModule: true, default: () => null };
  throw Error('unexpected component dependency ' + name);
}
vm.runInNewContext(output, { require: load, module: moduleValue, exports: moduleValue.exports, console, setTimeout, clearTimeout, URL });
const Page = moduleValue.exports.default;
function render() {
  cursor = 0; dirty = false; tree = Page();
  const next = effects; effects = []; next.forEach(fn => fn());
}
async function settle() {
  for (let i = 0; i < 8; i++) {
    await new Promise(resolve => setImmediate(resolve));
    if (dirty) render();
  }
}
function nodes(node, found = []) {
  if (arguments.length === 0) node = tree;
  if (Array.isArray(node)) node.forEach(x => nodes(x, found));
  else if (React.isValidElement(node)) { found.push(node); nodes(node.props.children, found); }
  return found;
}
function text(node) {
  if (Array.isArray(node)) return node.map(text).join('');
  if (React.isValidElement(node)) return text(node.props.children);
  return typeof node === 'string' || typeof node === 'number' ? String(node) : '';
}
function button(label) {
  const result = nodes().find(x => x.type === 'button' && text(x).trim() === label);
  assert(result, 'button should be present: ' + label);
  return result;
}
const badge = label => nodes().some(x => x.type === 'span' && text(x) === label);
function connectedCount() {
  return nodes().find(x => typeof x.type === 'function' && x.type.name === 'StatCard' && x.props.label === 'Connected').props.value;
}
function form() {
  return nodes().find(x => typeof x.type === 'function' && x.type.name === 'PluginIntegrationForm');
}
async function open() { button('Configure').props.onClick(); await settle(); }
async function enter() { form().props.onChange({ GITHUB_PLUGIN_TOKEN: 'fixture-only' }); await settle(); }

(async () => {
  render(); await settle();
  assert(badge('Not configured')); assert.equal(connectedCount(), 1);
  await open(); await enter();
  await button('Save').props.onClick(); await settle();
  assert(badge('Configurado — teste pendente'), 'saved credentials must not look absent while awaiting the test');
  assert.equal(connectedCount(), 1, 'saving alone is not a successful connection test');
  await open();
  assert.deepEqual(Object.keys(form().props.values), [], 'saved token is never repopulated');
  assert(text(tree).includes(translations['integrations.credentialsSaved']));
  const readsBeforeTest = requests.filter(x => x.url === '/integrations').length;
  await button('Test').props.onClick(); await settle();
  assert(badge('Connected'), 'successful test must refresh the card without a page reload');
  assert.equal(connectedCount(), 2, 'connected plugins must be included in the connected counter');
  assert(requests.filter(x => x.url === '/integrations').length > readsBeforeTest);
  healthy = false;
  await button('Test').props.onClick(); await settle();
  assert(badge('Error')); assert.equal(connectedCount(), 1);

  // A delayed pending response from Save must not overwrite the newer Test result.
  healthy = true; await enter(); delayNextEnv = true;
  const saving = button('Save').props.onClick(); await settle();
  assert(releaseEnv); await open();
  await button('Test').props.onClick(); await settle();
  assert(badge('Connected')); assert.equal(connectedCount(), 2);
  releaseEnv(); await saving; await settle();
  assert(badge('Connected'), 'old pending fetch must not revert the successful test');
  assert.equal(connectedCount(), 2);
  assert(!text(tree).includes('fixture-only'), 'no token appears in the page feedback');
  console.log('PASS actual integration page handlers: saved/pending, secret stays blank, test refreshes card and counter, failed test, out-of-order response; synthetic hooks/HTTP, no browser or provider call');
})().catch(error => { console.error(error); process.exitCode = 1; });
