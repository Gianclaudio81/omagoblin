const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../Main.qml`, 'utf8');
const functions = source.match(/^  function [^\n]*\{\n[\s\S]*?^  }/gm).join('\n');
function context(agents = []) {
  const timer = {running: false, starts: 0, start() {this.running = true; this.starts++;}, stop() {this.running = false;}};
  const ctx = vm.createContext({agents, settings: {}, limitsRetry: timer, limitsRetryDelayMs: 30000});
  ctx.root = ctx;
  vm.runInContext(functions, ctx);
  return ctx;
}
const agent = (id, record) => ({agentId: id, record});
test('missing limits recover without a collector retry flag', () => {
  const ctx = context();
  for (const limits of [undefined, [], [{percent: -1}], [{percent: null}], [{percent: 'bad'}]]) {
    assert.equal(ctx.needsLimitsRetry(agent('codex', {ready: true, limits})), true);
  }
  assert.equal(ctx.needsLimitsRetry(agent('codex', null)), true);
  for (const percent of [0, 0.97, 1]) {
    assert.equal(ctx.needsLimitsRetry(agent('codex', {ready: true, limits: [{percent}]})), false);
  }
});
test('disabled, prepaid, unavailable and unknown providers are excluded', () => {
  const ctx = context();
  for (const item of [agent('fireworks', {ready: true}), agent('other', {ready: true}), agent('claude', {ready: false}), agent('codex', {ready: true, balance: {remaining: 2}})]) {
    assert.equal(ctx.needsLimitsRetry(item), false);
  }
  assert.equal(ctx.needsLimitsRetry(agent('claude', {retryAdvised: true})), true);
  ctx.settings = {providers: {codex: {enabled: false}}};
  assert.equal(ctx.needsLimitsRetry(agent('codex', {retryAdvised: true})), false);
});
test('repeated reads do not postpone retries; recovery clears backoff', () => {
  const ctx = context([agent('codex', {ready: true, limits: []})]);
  ctx.scheduleLimitsRetry();
  ctx.scheduleLimitsRetry();
  assert.equal(ctx.limitsRetry.starts, 1);
  assert.equal(JSON.stringify(ctx.retryAgentIds), '["codex"]');
  ctx.limitsRetry.running = false;
  ctx.limitsRetryDelayMs = 60000;
  ctx.scheduleLimitsRetry();
  assert.equal(ctx.limitsRetry.starts, 2);
  assert.equal(ctx.limitsRetryDelayMs, 60000);
  ctx.agents[0].record.limits = [{percent: 0}];
  ctx.scheduleLimitsRetry();
  assert.equal(ctx.limitsRetry.running, false);
  assert.equal(ctx.limitsRetryDelayMs, 30000);
});
test('watchdog reloads all existing local records', () => {
  let reads = 0;
  const ctx = context([null, {reload() {reads++;}}, {reload() {reads++;}}]);
  ctx.reloadAgents();
  assert.equal(reads, 2);
});
