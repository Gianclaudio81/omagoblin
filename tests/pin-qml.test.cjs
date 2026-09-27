const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/../Panel.qml`, 'utf8');
const functions = source.match(/^  function [^\n]*\{\n[\s\S]*?^  }/gm).join('\n');

function context() {
  const writes = [];
  const ctx = vm.createContext({
    settings: {refreshIntervalSec: 120, barProviders: 'codex'},
    moduleName: 'tod.omagoblin',
    bar: {shell: {updateEntryInline(id, entry) {writes.push({id, entry});}}},
    usage: {formatTokenCount(n) {return `${n} tokens`;}},
    activeModelText: 'GPT-5',
    clamp(n, lo, hi) {return Math.max(lo, Math.min(hi, n));},
    writes,
  });
  ctx.root = ctx;
  vm.runInContext(functions, ctx);
  return ctx;
}

test('pins arbitrary providers and saves other widget settings', () => {
  const ctx = context();
  ctx.pinnedProviderIds = ctx.parsePinnedProviders(ctx.settings.barProviders);
  ctx.pinProvider('gemini');
  assert.equal(ctx.settings.barProviders, 'codex,gemini');
  assert.equal(ctx.settings.refreshIntervalSec, 120);
  assert.equal(ctx.writes[0].id, 'tod.omagoblin');
  assert.equal(ctx.writes[0].entry.barProviders, 'codex,gemini');

  ctx.pinnedProviderIds = ctx.parsePinnedProviders(ctx.settings.barProviders);
  ctx.pinProvider('codex');
  assert.equal(ctx.settings.barProviders, 'gemini');
  ctx.pinnedProviderIds = ctx.parsePinnedProviders(ctx.settings.barProviders);
  ctx.pinProvider('gemini');
  assert.equal(ctx.settings.barProviders, 'gemini');
  assert.equal(ctx.writes.length, 2);
});

test('normalizes duplicate IDs and summarizes quotas, balances and tokens', () => {
  const ctx = context();
  assert.equal(JSON.stringify(ctx.parsePinnedProviders(' codex, claude, codex, grok ')),
    '["codex","claude","grok"]');
  assert.equal(ctx.providerBarText({providerId: 'claude', providerName: 'Claude',
    limits: [{label: 'Session', percent: 0.25}]}), '75%');
  assert.equal(ctx.providerBarText({providerId: 'grok', providerName: 'Grok', limits: [],
    balance: {remaining: 3.5, currency: 'USD'}}), '—');
  assert.equal(ctx.providerBarText({providerId: 'gemini', providerName: 'Gemini', limits: [],
    todayTotalTokens: 500}), '—');
});

test('keeps pin order and falls back when saved providers have no data', () => {
  const ctx = context();
  const available = [{providerId: 'claude'}, {providerId: 'codex'}, {providerId: 'gemini'}];
  assert.equal(JSON.stringify(ctx.availableBarProviders(available, ['gemini', 'claude'])),
    JSON.stringify([available[2], available[0]]));
  assert.equal(JSON.stringify(ctx.availableBarProviders(available, ['grok'])),
    JSON.stringify([available[0]]));
  assert.equal(ctx.availableBarProviders([], ['codex']).length, 0);
});


test('bar always uses current session even when weekly consumption is higher', () => {
  const ctx = context();
  const p = {providerId: 'claude', providerName: 'Claude', limits: [
    {label: 'Weekly (7-day)', percent: 0.95},
    {label: 'Session (5-hour)', percent: 0.2},
  ]};
  assert.equal(ctx.bindingWindow(p).title, 'Session');
  assert.equal(ctx.providerBarText(p), '80%');
  p.limits = [{label: 'Weekly (7-day)', percent: 0.95}];
  assert.equal(ctx.bindingWindow(p), null);
  assert.equal(ctx.providerBarText(p), '—');
  p.limits.push({label: 'Session', percent: null});
  assert.equal(ctx.bindingWindow(p), null);
});
